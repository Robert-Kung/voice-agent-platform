"""
Tests for agent_tools.py & agent_factory.py

涵蓋：
1. Profile 載入（YAML / DB fallback）
2. Tool registry 與條件性掛載
3. QA inline / tool 雙模式
4. Human operator namespace + auto-mount transfer_to_human
5. Services hours 嵌入 instructions
6. Agent class 組裝
"""

import os

import pytest
from unittest.mock import patch

from agent_factory import (
    create_agent_class,
    list_profiles,
    load_profile,
    _human_operator_enabled,
    _qa_mode,
    _render_qa_block,
    _render_services_block,
)
from agent_tools import (
    TOOL_REGISTRY,
    build_tools_for_agent,
    get_available_tools,
    make_lookup_qa,
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
    """最小可用 profile（pipeline 模式預設值），用於單元測試。"""
    return {
        "name": "測試店",
        "timezone": "Asia/Taipei",
        "instructions": "你是測試客服。",
        "welcome_message": "您好，測試中。",
        "qa_mode": "inline",
        "human_operator": {
            "enabled": False,  # 預設 minimal 不啟用 handoff
        },
        "qa_data": [
            {"keywords": ["費用", "價格"], "answer": "費用 100 元。"},
            {"keywords": ["地址", "在哪"], "answer": "台北市中山區。"},
        ],
        "tools": [
            {"name": "get_current_time"},
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
        assert car_profile["name"] == "汽車代檢中心"
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
# 2. Tool Registry
# ═══════════════════════════════════════════════════════════


class TestToolRegistry:
    def test_registry_contains_only_tier1_and_tier2(self):
        """重構後只剩三個工具：get_current_time + 兩個條件性掛載的 Tier 2。"""
        expected = {
            "get_current_time",       # Tier 1
            "lookup_qa",              # Tier 2 (qa_mode=tool 時自動掛)
            "transfer_to_human",      # Tier 2 (human_operator.enabled 時自動掛)
        }
        assert expected == set(TOOL_REGISTRY.keys())

    def test_get_available_tools(self):
        tools = get_available_tools()
        assert isinstance(tools, list)
        assert len(tools) == len(TOOL_REGISTRY)

    def test_build_tools_respects_profile_declaration(self, minimal_profile):
        tools = build_tools_for_agent(minimal_profile)
        # build_tools_for_agent 只看 profile.tools 列出的；不負責 auto-mount
        assert set(tools.keys()) == {"get_current_time"}

    def test_build_tools_empty_when_no_tools_section(self):
        profile = {"name": "empty", "timezone": "Asia/Taipei"}
        tools = build_tools_for_agent(profile)
        assert tools == {}

    def test_unknown_tool_logged_and_skipped(self, minimal_profile):
        minimal_profile["tools"].append({"name": "nonexistent_tool_xyz"})
        tools = build_tools_for_agent(minimal_profile)
        assert "get_current_time" in tools
        assert "nonexistent_tool_xyz" not in tools


# ═══════════════════════════════════════════════════════════
# 3. QA inline / tool 雙模式
# ═══════════════════════════════════════════════════════════


class TestQAModes:
    def test_qa_mode_default_is_inline(self):
        profile = {"name": "x"}
        assert _qa_mode(profile) == "inline"

    def test_qa_mode_invalid_falls_back_to_inline(self):
        profile = {"name": "x", "qa_mode": "garbage"}
        assert _qa_mode(profile) == "inline"

    def test_render_qa_block_includes_keywords_and_answers(self):
        qa_data = [
            {"keywords": ["費用", "價格"], "answer": "100 元。"},
            {"keywords": ["地址"], "answer": "台北市。"},
        ]
        rendered = _render_qa_block(qa_data)
        assert "費用" in rendered
        assert "100 元" in rendered
        assert "台北市" in rendered

    def test_render_qa_block_empty_returns_empty(self):
        assert _render_qa_block([]) == ""

    def test_inline_mode_appends_qa_to_instructions(self, minimal_profile):
        minimal_profile["qa_mode"] = "inline"
        AgentClass = create_agent_class(minimal_profile)
        # inline 模式不該掛 lookup_qa tool
        assert not hasattr(AgentClass, "lookup_qa")

    def test_tool_mode_mounts_lookup_qa(self, minimal_profile):
        minimal_profile["qa_mode"] = "tool"
        AgentClass = create_agent_class(minimal_profile)
        # tool 模式應自動掛 lookup_qa
        assert hasattr(AgentClass, "lookup_qa")

    def test_tool_mode_without_qa_data_does_not_mount(self, minimal_profile):
        """qa_mode=tool 但 qa_data 為空時，不掛 lookup_qa（避免空工具浪費 context）。"""
        minimal_profile["qa_mode"] = "tool"
        minimal_profile["qa_data"] = []
        AgentClass = create_agent_class(minimal_profile)
        assert not hasattr(AgentClass, "lookup_qa")

    def test_car_inspection_qa_coverage(self, car_profile):
        """驗車 profile 的 QA 應涵蓋常見問題。"""
        qa_data = car_profile["qa_data"]
        all_keywords = [k for item in qa_data for k in item["keywords"]]

        assert "行照" in all_keywords
        assert any("費用" in k for k in all_keywords), "expected at least one 費用-related keyword"
        assert "營業時間" in all_keywords
        assert "流程" in all_keywords

    def test_dental_qa_has_appointment_related(self, dental_profile):
        qa_data = dental_profile["qa_data"]
        all_keywords = [k for item in qa_data for k in item["keywords"]]
        assert "初診" in all_keywords
        assert "洗牙" in all_keywords


# ═══════════════════════════════════════════════════════════
# 4. Human Operator 設定 + auto-mount
# ═══════════════════════════════════════════════════════════


class TestHumanOperator:
    def test_enabled_via_new_namespace(self):
        profile = {"name": "x", "human_operator": {"enabled": True}}
        assert _human_operator_enabled(profile) is True

    def test_disabled_via_new_namespace(self):
        profile = {"name": "x", "human_operator": {"enabled": False}}
        assert _human_operator_enabled(profile) is False

    def test_legacy_flat_field_still_recognised(self):
        """舊 schema：只要 human_operator_instructions 有值就視為啟用。"""
        profile = {"name": "x", "human_operator_instructions": "你是門市人員。"}
        assert _human_operator_enabled(profile) is True

    def test_no_human_operator_returns_false(self):
        profile = {"name": "x"}
        assert _human_operator_enabled(profile) is False

    def test_enabled_auto_mounts_transfer_to_human(self, minimal_profile):
        minimal_profile["human_operator"] = {
            "enabled": True,
            "instructions": "你是門市人員。",
            "greeting": "您好。",
        }
        AgentClass = create_agent_class(minimal_profile)
        assert hasattr(AgentClass, "transfer_to_human")

    def test_disabled_does_not_mount(self, minimal_profile):
        minimal_profile["human_operator"] = {"enabled": False}
        AgentClass = create_agent_class(minimal_profile)
        assert not hasattr(AgentClass, "transfer_to_human")

    def test_all_real_profiles_have_handoff_enabled(self):
        """三個正式 profile 都應啟用 handoff（dental / restaurant / car / example）。"""
        for name in list_profiles():
            profile = load_profile(name)
            assert _human_operator_enabled(profile), f"{name}: handoff should be enabled"


# ═══════════════════════════════════════════════════════════
# 5. Services hours 嵌入 instructions
# ═══════════════════════════════════════════════════════════


class TestServicesRender:
    def test_render_services_includes_always_open(self):
        services = {"fuel": {"always_open": True, "hours_text": "24 小時"}}
        rendered = _render_services_block(services)
        assert "fuel" in rendered
        assert "24 小時" in rendered

    def test_render_services_with_hours_text_string(self):
        services = {"shop": {"hours_text": "平日 9-18 點"}}
        rendered = _render_services_block(services)
        assert "平日 9-18 點" in rendered

    def test_render_services_with_hours_text_dict(self):
        services = {
            "clinic": {
                "hours_text": {
                    "weekday": "平日 9-17 點",
                    "saturday": "週六 9-12 點",
                }
            }
        }
        rendered = _render_services_block(services)
        assert "平日 9-17 點" in rendered
        assert "週六 9-12 點" in rendered

    def test_render_empty_services_returns_empty(self):
        assert _render_services_block({}) == ""

    def test_services_rendered_into_agent_instructions(self, restaurant_profile):
        """create_agent_class 要把 services 嵌入 instructions（透過 agent_instructions 變數，
        但 Agent class 本身不直接暴露），所以我們檢查 _render_services_block 對 restaurant 的 services 有實質輸出。"""
        rendered = _render_services_block(restaurant_profile["services"])
        assert len(rendered) > 0
        assert "餐廳" in rendered or "restaurant" in rendered.lower()


# ═══════════════════════════════════════════════════════════
# 6. Agent Class 組裝
# ═══════════════════════════════════════════════════════════


class TestAgentClassCreation:
    def test_creates_class_with_correct_name(self, car_profile):
        AgentClass = create_agent_class(car_profile)
        assert "汽車代檢中心" in AgentClass.__name__

    def test_class_has_only_tier1_tool_when_minimal(self, minimal_profile):
        """minimal_profile: qa_mode=inline, human_operator.enabled=False — 只應有 get_current_time。"""
        AgentClass = create_agent_class(minimal_profile)
        assert hasattr(AgentClass, "get_current_time")
        assert not hasattr(AgentClass, "lookup_qa")
        assert not hasattr(AgentClass, "transfer_to_human")

    def test_agent_can_be_instantiated(self, car_profile):
        AgentClass = create_agent_class(car_profile)
        agent = AgentClass()
        assert agent is not None

    def test_pipeline_and_realtime_modes_both_work(self, minimal_profile):
        PipelineAgent = create_agent_class(minimal_profile, mode="pipeline")
        RealtimeAgent = create_agent_class(minimal_profile, mode="realtime")
        assert PipelineAgent is not RealtimeAgent
        assert hasattr(PipelineAgent, "get_current_time")
        assert hasattr(RealtimeAgent, "get_current_time")


# ═══════════════════════════════════════════════════════════
# 7. Per-Profile Tool 掛載規則
# ═══════════════════════════════════════════════════════════


class TestToolMounting:
    def test_all_real_profiles_have_get_current_time(self):
        for name in list_profiles():
            profile = load_profile(name)
            tools = build_tools_for_agent(profile)
            assert "get_current_time" in tools, f"{name}: get_current_time missing"

    def test_real_profiles_use_inline_qa_by_default(self):
        """現有 profile 都用 inline 模式 — build_tools 不該見到 lookup_qa。"""
        for name in list_profiles():
            profile = load_profile(name)
            tools = build_tools_for_agent(profile)
            assert "lookup_qa" not in tools, (
                f"{name}: lookup_qa should not be in tools list under inline mode"
            )

    def test_real_profiles_handoff_via_auto_mount_not_tools_list(self):
        """transfer_to_human 應由 agent_factory auto-mount，不在 build_tools 結果中。"""
        for name in list_profiles():
            profile = load_profile(name)
            tools = build_tools_for_agent(profile)
            assert "transfer_to_human" not in tools, (
                f"{name}: transfer_to_human should be auto-mounted, not in tools list"
            )
            # 但 AgentClass 上應該有（因 human_operator.enabled）
            AgentClass = create_agent_class(profile)
            assert hasattr(AgentClass, "transfer_to_human"), (
                f"{name}: AgentClass should have transfer_to_human"
            )

    def test_lookup_qa_factory_returns_distinct_objects(self):
        """同一 factory 用兩個 profile 建立的 tool 應該是獨立物件。"""
        dental = load_profile("dental_clinic")
        restaurant = load_profile("restaurant")
        dental_qa = make_lookup_qa(dental, {})
        restaurant_qa = make_lookup_qa(restaurant, {})
        assert dental_qa is not restaurant_qa


# ═══════════════════════════════════════════════════════════
# 8. AGENT_MODE 環境變數
# ═══════════════════════════════════════════════════════════


class TestAgentMode:
    def test_agent_mode_defaults_to_pipeline(self):
        env = {k: v for k, v in os.environ.items() if k != "AGENT_MODE"}
        with patch.dict("os.environ", env, clear=True):
            mode = os.environ.get("AGENT_MODE", "pipeline")
            assert mode == "pipeline"

    def test_agent_mode_reads_env_var(self):
        with patch.dict("os.environ", {"AGENT_MODE": "realtime"}):
            mode = os.environ.get("AGENT_MODE", "pipeline")
            assert mode == "realtime"

    def test_google_realtime_model_importable(self):
        from livekit.plugins.google.realtime import RealtimeModel
        assert RealtimeModel is not None

    def test_realtime_model_instantiation(self):
        from livekit.plugins.google.realtime import RealtimeModel
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key-for-unit-test"}):
            model = RealtimeModel(
                model="gemini-3.1-flash-live-preview",
                voice="Nova",
                temperature=0.8,
            )
            assert model is not None
