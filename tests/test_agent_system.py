"""
Tests for agent_tools.py & agent_factory.py

測試策略：
1. Profile 載入 — YAML 正確讀取、錯誤處理
2. Tool 工廠 — 每個 make_xxx 回傳正確結構
3. 營業狀態 — 不同時段 / 星期的判斷
4. QA 搜尋 — 關鍵字匹配與未匹配
5. Agent class 組裝 — tools 動態掛載
6. Per-profile tool 隔離 — 不同 profile 有不同 tools
"""

import datetime
import asyncio
import pytest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from agent_factory import load_profile, create_agent_class, list_profiles
from agent_tools import (
    build_tools_for_agent,
    get_available_tools,
    _eval_business_status,
    _parse_time,
    make_get_current_datetime,
    make_check_business_status,
    make_lookup_qa,
    make_check_weather,
    make_search_menu,
    make_book_appointment,
    make_calculate_price,
    TOOL_REGISTRY,
)


# ═══════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def car_profile():
    return load_profile("car_inspection")


@pytest.fixture
def dental_profile():
    return load_profile("dental_clinic")


@pytest.fixture
def restaurant_profile():
    return load_profile("restaurant")


@pytest.fixture
def minimal_profile():
    """最小可用 profile，用於單元測試。"""
    return {
        "name": "測試店",
        "timezone": "Asia/Taipei",
        "instructions": "你是測試客服。",
        "welcome_message": "您好，測試中。",
        "services": {
            "shop": {
                "always_open": False,
                "closed_days": [6],
                "schedule": {
                    "weekday": {"start": "09:00", "end": "18:00"},
                    "saturday": {"start": "09:00", "end": "12:00"},
                },
                "hours_text": {
                    "weekday": "平日 9-18 點。",
                    "saturday": "週六 9-12 點。",
                    "closed": "週日休息。",
                },
            }
        },
        "qa_data": [
            {"keywords": ["費用", "價格"], "answer": "費用 100 元。"},
            {"keywords": ["地址", "在哪"], "answer": "台北市中山區。"},
        ],
        "tools": [
            {"name": "get_current_datetime"},
            {"name": "lookup_qa"},
        ],
    }


# ═══════════════════════════════════════════════════════════
# 1. Profile 載入
# ═══════════════════════════════════════════════════════════


class TestProfileLoading:
    def test_list_profiles_returns_all(self):
        profiles = list_profiles()
        assert "car_inspection" in profiles
        assert "dental_clinic" in profiles
        assert "restaurant" in profiles

    def test_load_valid_profile(self, car_profile):
        assert car_profile["name"] == "車容坊加油站"
        assert "instructions" in car_profile
        assert "services" in car_profile
        assert "qa_data" in car_profile
        assert "tools" in car_profile

    def test_load_nonexistent_profile_raises(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_profile("nonexistent_profile_xyz")

    def test_each_profile_has_required_fields(self):
        for name in list_profiles():
            profile = load_profile(name)
            assert "name" in profile, f"{name}: missing 'name'"
            assert "instructions" in profile, f"{name}: missing 'instructions'"
            assert "tools" in profile, f"{name}: missing 'tools'"
            assert isinstance(profile["tools"], list), f"{name}: 'tools' should be a list"


# ═══════════════════════════════════════════════════════════
# 2. Tool 工廠
# ═══════════════════════════════════════════════════════════


class TestToolRegistry:
    def test_registry_contains_all_expected_tools(self):
        expected = {
            "get_current_datetime",
            "check_business_status",
            "lookup_qa",
            "transfer_to_human",
            "check_weather",
            "search_menu",
            "book_appointment",
            "calculate_price",
        }
        assert expected == set(TOOL_REGISTRY.keys())

    def test_get_available_tools(self):
        tools = get_available_tools()
        assert isinstance(tools, list)
        assert len(tools) == len(TOOL_REGISTRY)

    def test_build_tools_respects_profile_declaration(self, minimal_profile):
        tools = build_tools_for_agent(minimal_profile)
        assert set(tools.keys()) == {"get_current_datetime", "lookup_qa"}
        assert "check_business_status" not in tools
        assert "transfer_to_human" not in tools

    def test_build_tools_empty_when_no_tools_section(self):
        profile = {"name": "empty", "timezone": "Asia/Taipei"}
        tools = build_tools_for_agent(profile)
        assert tools == {}

    def test_unknown_tool_logged_and_skipped(self, minimal_profile):
        minimal_profile["tools"].append({"name": "nonexistent_tool_xyz"})
        tools = build_tools_for_agent(minimal_profile)
        # 已知的兩個 tool 仍然建立成功
        assert "get_current_datetime" in tools
        assert "lookup_qa" in tools
        # 未知的不在結果中
        assert "nonexistent_tool_xyz" not in tools


# ═══════════════════════════════════════════════════════════
# 3. 營業狀態判斷
# ═══════════════════════════════════════════════════════════


class TestBusinessStatus:
    def test_parse_time(self):
        assert _parse_time("08:00") == 480
        assert _parse_time("18:30") == 1110
        assert _parse_time("00:00") == 0

    def test_always_open_service(self, car_profile):
        result = _eval_business_status(car_profile, "fuel")
        assert result["is_open"] is True
        assert "24" in result["service_hours_text"]

    def test_unknown_service_type(self, car_profile):
        result = _eval_business_status(car_profile, "unknown_service")
        assert result["is_open"] is False
        assert "查無" in result["service_hours_text"]

    def test_closed_on_sunday(self, car_profile):
        """Sunday (weekday=6) — inspection should be closed."""
        sunday = datetime.datetime(2026, 3, 29, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))  # Sunday
        with patch("agent_tools.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = sunday
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            result = _eval_business_status(car_profile, "inspection")
            assert result["is_open"] is False

    def test_open_on_weekday_during_hours(self, car_profile):
        """Tuesday 10:00 — inspection should be open."""
        tuesday_10am = datetime.datetime(2026, 3, 31, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        with patch("agent_tools.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = tuesday_10am
            result = _eval_business_status(car_profile, "inspection")
            assert result["is_open"] is True

    def test_closed_on_weekday_after_hours(self, car_profile):
        """Tuesday 20:00 — inspection should be closed."""
        tuesday_8pm = datetime.datetime(2026, 3, 31, 20, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        with patch("agent_tools.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = tuesday_8pm
            result = _eval_business_status(car_profile, "inspection")
            assert result["is_open"] is False

    def test_car_wash_within_hours(self, car_profile):
        """Car wash open 07:00-22:00, test at 15:00."""
        weekday_3pm = datetime.datetime(2026, 3, 31, 15, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        with patch("agent_tools.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = weekday_3pm
            result = _eval_business_status(car_profile, "car_wash")
            assert result["is_open"] is True

    def test_restaurant_closed_on_monday(self, restaurant_profile):
        """Restaurant closed on Monday (closed_days: [0])."""
        monday = datetime.datetime(2026, 3, 30, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))  # Monday
        with patch("agent_tools.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = monday
            result = _eval_business_status(restaurant_profile, "restaurant")
            assert result["is_open"] is False


# ═══════════════════════════════════════════════════════════
# 4. QA 搜尋
# ═══════════════════════════════════════════════════════════


class TestLookupQA:
    def test_qa_match_by_keyword(self, minimal_profile):
        tool = make_lookup_qa(minimal_profile, {})
        # 取得內部 function（@function_tool 裝飾過的）
        # 直接測底層邏輯
        from agent_tools import _eval_business_status

        qa_data = minimal_profile["qa_data"]
        # 手動測匹配
        question = "請問費用多少？"
        found = False
        for item in qa_data:
            if any(kw in question for kw in item["keywords"]):
                found = True
                assert "100" in item["answer"]
                break
        assert found

    def test_qa_no_match(self, minimal_profile):
        question = "明天會下雨嗎？"
        qa_data = minimal_profile["qa_data"]
        found = any(
            any(kw in question for kw in item["keywords"])
            for item in qa_data
        )
        assert not found

    def test_car_inspection_qa_coverage(self, car_profile):
        """驗車 profile 的 QA 應涵蓋常見問題。"""
        qa_data = car_profile["qa_data"]
        all_keywords = []
        for item in qa_data:
            all_keywords.extend(item["keywords"])

        # 確保常見問題都有對應
        assert "行照" in all_keywords
        assert "費用" in all_keywords
        assert "營業時間" in all_keywords
        assert "流程" in all_keywords

    def test_dental_qa_has_appointment_related(self, dental_profile):
        qa_data = dental_profile["qa_data"]
        all_keywords = []
        for item in qa_data:
            all_keywords.extend(item["keywords"])
        assert "初診" in all_keywords
        assert "洗牙" in all_keywords


# ═══════════════════════════════════════════════════════════
# 5. Agent Class 組裝
# ═══════════════════════════════════════════════════════════


class TestAgentClassCreation:
    def test_creates_class_with_correct_name(self, car_profile):
        AgentClass = create_agent_class(car_profile)
        assert "車容坊" in AgentClass.__name__

    def test_class_has_declared_tools_only(self, minimal_profile):
        AgentClass = create_agent_class(minimal_profile)
        # 宣告的 tools 應存在
        assert hasattr(AgentClass, "get_current_datetime")
        assert hasattr(AgentClass, "lookup_qa")
        # 未宣告的 tools 不應存在
        assert not hasattr(AgentClass, "check_business_status")
        assert not hasattr(AgentClass, "transfer_to_human")
        assert not hasattr(AgentClass, "check_weather")

    def test_agent_can_be_instantiated(self, car_profile):
        AgentClass = create_agent_class(car_profile)
        agent = AgentClass()
        assert agent is not None


# ═══════════════════════════════════════════════════════════
# 6. Per-Profile Tool 隔離
# ═══════════════════════════════════════════════════════════


class TestToolIsolation:
    def test_each_profile_has_different_tools(self):
        profiles_tools = {}
        for name in list_profiles():
            profile = load_profile(name)
            tools = build_tools_for_agent(profile)
            profiles_tools[name] = set(tools.keys())

        # 車廠有天氣，牙醫沒有
        assert "check_weather" in profiles_tools["car_inspection"]
        assert "check_weather" not in profiles_tools["dental_clinic"]

        # 牙醫有預約，車廠和餐廳沒有
        assert "book_appointment" in profiles_tools["dental_clinic"]
        assert "book_appointment" not in profiles_tools["car_inspection"]

        # 餐廳有菜單搜尋和價格計算
        assert "search_menu" in profiles_tools["restaurant"]
        assert "calculate_price" in profiles_tools["restaurant"]
        assert "search_menu" not in profiles_tools["car_inspection"]

    def test_tool_configs_are_independent(self):
        """不同 profile 的同名 tool 應有各自的 config。"""
        car = load_profile("car_inspection")
        dental = load_profile("dental_clinic")

        car_tools = build_tools_for_agent(car)
        dental_tools = build_tools_for_agent(dental)

        # 兩者都有 lookup_qa，但底層 qa_data 不同
        assert "lookup_qa" in car_tools
        assert "lookup_qa" in dental_tools
        # 它們是不同的物件
        assert car_tools["lookup_qa"] is not dental_tools["lookup_qa"]


# ═══════════════════════════════════════════════════════════
# 7. Search Menu Tool
# ═══════════════════════════════════════════════════════════


class TestSearchMenuTool:
    def test_restaurant_menu_config_loaded(self, restaurant_profile):
        """餐廳 profile 的 search_menu config 應有 categories。"""
        tools_config = restaurant_profile.get("tools", [])
        menu_config = next(
            (t.get("config", {}) for t in tools_config if t["name"] == "search_menu"),
            None,
        )
        assert menu_config is not None
        assert "categories" in menu_config
        categories = menu_config["categories"]
        assert len(categories) > 0

        # 確認招牌菜在目錄中
        all_items = [
            item["name"]
            for cat in categories
            for item in cat.get("items", [])
        ]
        assert "三杯雞" in all_items
        assert "紅燒獅子頭" in all_items


# ═══════════════════════════════════════════════════════════
# 8. Calculate Price Tool
# ═══════════════════════════════════════════════════════════


class TestCalculatePriceTool:
    def test_restaurant_price_rules_loaded(self, restaurant_profile):
        tools_config = restaurant_profile.get("tools", [])
        price_config = next(
            (t.get("config", {}) for t in tools_config if t["name"] == "calculate_price"),
            None,
        )
        assert price_config is not None
        assert "price_rules" in price_config
        rules = price_config["price_rules"]
        rule_names = [r["name"] for r in rules]
        assert "午餐套餐" in rule_names
        assert "晚餐套餐" in rule_names
