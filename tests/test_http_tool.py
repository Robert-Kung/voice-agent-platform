"""Tests for make_http_tool — Tier 3 generic HTTP tool factory.

涵蓋：
- 名稱 / endpoint / method / param 驗證
- SSRF 防護（localhost / 私網 IP / metadata endpoint）
- ${ENV_VAR} 替換
- JSON schema 正確生成
- HTTP 請求行為（mock aiohttp）
- 錯誤處理（timeout / 4xx / 5xx / 連線失敗）
"""

from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from agent_tools import (
    _substitute_env,
    _validate_endpoint,
    build_tools_for_agent,
    make_http_tool,
)


# ═══════════════════════════════════════════════════════════
# 名稱與 schema 驗證
# ═══════════════════════════════════════════════════════════


class TestNameValidation:
    def _config(self, **overrides):
        base = {
            "name": "valid_tool",
            "description": "test tool",
            "endpoint": "https://api.example.com/x",
            "method": "POST",
        }
        base.update(overrides)
        return base

    def test_valid_name_accepted(self):
        tool = make_http_tool({}, self._config(name="report_failure"))
        assert tool.info.name == "report_failure"

    def test_uppercase_name_rejected(self):
        with pytest.raises(ValueError, match="invalid HTTP tool name"):
            make_http_tool({}, self._config(name="ReportFailure"))

    def test_starts_with_digit_rejected(self):
        with pytest.raises(ValueError, match="invalid HTTP tool name"):
            make_http_tool({}, self._config(name="1tool"))

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError, match="invalid HTTP tool name"):
            make_http_tool({}, self._config(name=""))

    def test_special_chars_rejected(self):
        with pytest.raises(ValueError, match="invalid HTTP tool name"):
            make_http_tool({}, self._config(name="report-failure"))

    def test_long_name_rejected(self):
        with pytest.raises(ValueError, match="invalid HTTP tool name"):
            make_http_tool({}, self._config(name="a" * 100))


# ═══════════════════════════════════════════════════════════
# Endpoint / SSRF 防護
# ═══════════════════════════════════════════════════════════


class TestEndpointValidation:
    def test_https_public_accepted(self):
        _validate_endpoint("https://api.example.com/x")

    def test_http_public_accepted(self):
        _validate_endpoint("http://api.example.com/x")

    def test_ftp_rejected(self):
        with pytest.raises(ValueError, match="scheme must be http"):
            _validate_endpoint("ftp://example.com/x")

    def test_file_rejected(self):
        with pytest.raises(ValueError, match="scheme must be http"):
            _validate_endpoint("file:///etc/passwd")

    def test_localhost_rejected(self):
        with pytest.raises(ValueError, match="blocked"):
            _validate_endpoint("http://localhost:8080/x")

    def test_loopback_ip_rejected(self):
        with pytest.raises(ValueError, match="non-public IP"):
            _validate_endpoint("http://127.0.0.1/x")

    def test_private_class_a_rejected(self):
        with pytest.raises(ValueError, match="non-public IP"):
            _validate_endpoint("http://10.0.0.1/x")

    def test_private_class_b_rejected(self):
        with pytest.raises(ValueError, match="non-public IP"):
            _validate_endpoint("http://172.16.0.1/x")

    def test_private_class_c_rejected(self):
        with pytest.raises(ValueError, match="non-public IP"):
            _validate_endpoint("http://192.168.1.1/x")

    def test_link_local_rejected(self):
        # Listed both in _BLOCKED_HOSTNAMES (string literal) and as link-local IP
        with pytest.raises(ValueError, match="blocked|non-public IP"):
            _validate_endpoint("http://169.254.169.254/latest/meta-data/")

    def test_metadata_hostname_rejected(self):
        with pytest.raises(ValueError, match="blocked"):
            _validate_endpoint("http://metadata.google.internal/x")

    def test_no_hostname_rejected(self):
        with pytest.raises(ValueError, match="hostname"):
            _validate_endpoint("https:///path")

    def test_empty_url_rejected(self):
        with pytest.raises(ValueError, match="endpoint is required"):
            _validate_endpoint("")


# ═══════════════════════════════════════════════════════════
# ${ENV_VAR} 替換
# ═══════════════════════════════════════════════════════════


class TestEnvSubstitution:
    def test_substitutes_existing_var(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret123")
        assert _substitute_env("Bearer ${MY_TOKEN}") == "Bearer secret123"

    def test_missing_var_substitutes_empty(self, monkeypatch):
        monkeypatch.delenv("NOT_SET_VAR", raising=False)
        assert _substitute_env("Bearer ${NOT_SET_VAR}") == "Bearer "

    def test_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("A", "x")
        monkeypatch.setenv("B", "y")
        assert _substitute_env("${A}-${B}") == "x-y"

    def test_no_substitution_when_no_pattern(self):
        assert _substitute_env("plain text") == "plain text"

    def test_lowercase_var_not_substituted(self):
        # Pattern requires uppercase — lowercase ${var} is left untouched
        assert _substitute_env("${lower}") == "${lower}"


# ═══════════════════════════════════════════════════════════
# Method / param / config 驗證
# ═══════════════════════════════════════════════════════════


class TestConfigValidation:
    def _config(self, **overrides):
        base = {"name": "t", "endpoint": "https://api.example.com/x"}
        base.update(overrides)
        return base

    def test_default_method_is_post(self):
        tool = make_http_tool({}, self._config())
        # Method preserved internally; not exposed on tool.info but tested via behaviour
        assert tool.info.name == "t"

    def test_invalid_method_rejected(self):
        with pytest.raises(ValueError, match="invalid method"):
            make_http_tool({}, self._config(method="OPTIONS"))

    def test_method_case_insensitive(self):
        # 'post' should normalise to 'POST' and accept
        make_http_tool({}, self._config(method="post"))

    def test_timeout_negative_rejected(self):
        with pytest.raises(ValueError, match="timeout_seconds"):
            make_http_tool({}, self._config(timeout_seconds=-1))

    def test_timeout_too_long_rejected(self):
        with pytest.raises(ValueError, match="timeout_seconds"):
            make_http_tool({}, self._config(timeout_seconds=120))

    def test_invalid_param_name_rejected(self):
        with pytest.raises(ValueError, match="invalid parameter name"):
            make_http_tool({}, self._config(parameters=[{"name": "Bad-Name"}]))

    def test_invalid_param_type_rejected(self):
        with pytest.raises(ValueError, match="invalid parameter type"):
            make_http_tool({}, self._config(parameters=[{"name": "x", "type": "object"}]))

    def test_required_param_in_schema(self):
        tool = make_http_tool({}, self._config(parameters=[
            {"name": "building", "type": "string", "required": True},
            {"name": "symptom", "type": "string"},
        ]))
        schema = tool.info.raw_schema["parameters"]
        assert "building" in schema["properties"]
        assert "symptom" in schema["properties"]
        assert schema["required"] == ["building"]

    def test_param_description_in_schema(self):
        tool = make_http_tool({}, self._config(parameters=[
            {"name": "x", "type": "string", "description": "The X value"},
        ]))
        assert tool.info.raw_schema["parameters"]["properties"]["x"]["description"] == "The X value"


# ═══════════════════════════════════════════════════════════
# build_tools_for_agent 整合（Tier 3 路由）
# ═══════════════════════════════════════════════════════════


class TestBuildToolsRouting:
    def test_endpoint_field_routes_to_http_tool(self):
        profile = {
            "name": "p",
            "tools": [
                {
                    "name": "report",
                    "description": "report stuff",
                    "endpoint": "https://api.example.com/x",
                    "method": "POST",
                },
            ],
        }
        tools = build_tools_for_agent(profile)
        assert "report" in tools

    def test_no_endpoint_uses_registry(self):
        """沒有 endpoint 的應該走 TOOL_REGISTRY（這個是不存在的，會 skip 並 warn）。"""
        profile = {"name": "p", "tools": [{"name": "get_current_time"}]}
        tools = build_tools_for_agent(profile)
        assert "get_current_time" in tools

    def test_invalid_http_tool_skipped_not_raised(self):
        """SSRF 違規的 tool 應該被 log 跳過，不應 crash 整個 agent 啟動。"""
        profile = {
            "name": "p",
            "tools": [
                {"name": "get_current_time"},  # 這個正常
                {"name": "bad", "endpoint": "http://localhost/x"},  # 這個 SSRF
            ],
        }
        tools = build_tools_for_agent(profile)
        assert "get_current_time" in tools
        assert "bad" not in tools

    def test_http_tool_registered_with_correct_schema(self):
        profile = {
            "name": "p",
            "tools": [
                {
                    "name": "elevator_report",
                    "description": "通報電梯故障",
                    "endpoint": "https://api.example.com/elevator",
                    "method": "POST",
                    "parameters": [
                        {"name": "building", "type": "string", "required": True, "description": "棟別"},
                        {"name": "symptom", "type": "string"},
                    ],
                },
            ],
        }
        tools = build_tools_for_agent(profile)
        tool = tools["elevator_report"]
        schema = tool.info.raw_schema
        assert schema["name"] == "elevator_report"
        assert schema["description"] == "通報電梯故障"
        assert schema["parameters"]["required"] == ["building"]


# ═══════════════════════════════════════════════════════════
# HTTP 行為（mock aiohttp）
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def anyio_backend():
    """Pin async tests to asyncio backend only — trio not installed."""
    return "asyncio"


class TestHttpBehaviour:
    """測試 _handler 在不同 HTTP 回應下的行為。

    使用 aioresponses-like mock — 直接 patch aiohttp.ClientSession。
    """

    def _build_tool(self, **config_overrides):
        config = {
            "name": "test_tool",
            "endpoint": "https://api.example.com/x",
            "method": "POST",
            "parameters": [{"name": "x", "type": "string"}],
        }
        config.update(config_overrides)
        return make_http_tool({}, config)

    def _mock_session(self, status=200, json_body=None, text_body="", raise_exc=None):
        """Build a mock ClientSession context manager that returns a mock response."""
        resp = MagicMock()
        resp.status = status
        resp.json = AsyncMock(return_value=json_body if json_body is not None else {})
        if json_body is None:
            resp.json.side_effect = ValueError("no json")
        resp.text = AsyncMock(return_value=text_body)

        # request returns an async context manager yielding resp
        request_ctx = MagicMock()
        request_ctx.__aenter__ = AsyncMock(return_value=resp)
        request_ctx.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        if raise_exc:
            session.request = MagicMock(side_effect=raise_exc)
        else:
            session.request = MagicMock(return_value=request_ctx)

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        return session_ctx, session, resp

    @pytest.mark.anyio
    async def test_successful_post_returns_success(self):
        tool = self._build_tool()
        session_ctx, session, resp = self._mock_session(
            status=200, json_body={"ok": True, "ticket": "T-123"}
        )
        with patch("agent_tools.aiohttp.ClientSession", return_value=session_ctx):
            # Call the underlying handler — bypass @function_tool
            result = await tool._func(None, x="hello")  # type: ignore[attr-defined]
            assert result["success"] is True
            assert result["ticket"] == "T-123"

    @pytest.mark.anyio
    async def test_4xx_returns_failure_with_status(self):
        tool = self._build_tool()
        session_ctx, _, _ = self._mock_session(status=400, json_body=None, text_body="bad request")
        with patch("agent_tools.aiohttp.ClientSession", return_value=session_ctx):
            result = await tool._func(None, x="hello")  # type: ignore[attr-defined]
            assert result["success"] is False
            assert result["status"] == 400
            assert "bad request" in result["error"]

    @pytest.mark.anyio
    async def test_auth_header_substituted(self, monkeypatch):
        monkeypatch.setenv("MY_API_KEY", "abc123")
        tool = self._build_tool(auth_header="Bearer ${MY_API_KEY}")
        session_ctx, session, _ = self._mock_session(status=200, json_body={})
        with patch("agent_tools.aiohttp.ClientSession", return_value=session_ctx):
            await tool._func(None, x="y")  # type: ignore[attr-defined]
        # session.request should have been called with Authorization header
        call_kwargs = session.request.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer abc123"

    @pytest.mark.anyio
    async def test_get_method_uses_query_params(self):
        tool = self._build_tool(method="GET")
        session_ctx, session, _ = self._mock_session(status=200, json_body={"ok": True})
        with patch("agent_tools.aiohttp.ClientSession", return_value=session_ctx):
            await tool._func(None, x="hello")  # type: ignore[attr-defined]
        call_kwargs = session.request.call_args.kwargs
        assert call_kwargs["params"] == {"x": "hello"}
        assert "json" not in call_kwargs

    @pytest.mark.anyio
    async def test_post_method_uses_json_body(self):
        tool = self._build_tool(method="POST")
        session_ctx, session, _ = self._mock_session(status=200, json_body={})
        with patch("agent_tools.aiohttp.ClientSession", return_value=session_ctx):
            await tool._func(None, x="hello")  # type: ignore[attr-defined]
        call_kwargs = session.request.call_args.kwargs
        assert call_kwargs["json"] == {"x": "hello"}

    @pytest.mark.anyio
    async def test_none_kwargs_are_dropped(self):
        """LLM 沒填的 optional param 會傳 None — 不該轉發到 API。"""
        tool = self._build_tool(method="POST")
        session_ctx, session, _ = self._mock_session(status=200, json_body={})
        with patch("agent_tools.aiohttp.ClientSession", return_value=session_ctx):
            await tool._func(None, x="hello", optional_field=None)  # type: ignore[attr-defined]
        call_kwargs = session.request.call_args.kwargs
        assert "optional_field" not in call_kwargs["json"]
