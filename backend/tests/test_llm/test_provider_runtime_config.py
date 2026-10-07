"""
tests/test_llm/test_provider_runtime_config.py
provider 使用运行时有效配置：界面保存的 Key/服务商无需重启即时生效；
"测试连接"诊断不写回执、不触碰熔断计数。
"""
import json

import httpx
import pytest

from app.core import config
from app.llm.config import LLM_SETTING_KEYS
from app.llm.provider import llm_provider
from app.repositories.settings_repo import app_settings_repo


def _ok_response(text: str = "模型回复") -> httpx.Response:
    return httpx.Response(200, json={
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
    })


def _capture_transport(first_response: httpx.Response):
    """返回第一个响应并记录请求（URL/headers/body 供断言）"""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return first_response

    return httpx.MockTransport(handler), calls


@pytest.fixture(autouse=True)
def _clean():
    """隔离共享测试库与单例状态"""
    for key in LLM_SETTING_KEYS:
        app_settings_repo.delete(key)
    with llm_provider._failure_lock:
        llm_provider._consecutive_failures = 0
    llm_provider.set_test_transport(None)
    yield
    for key in LLM_SETTING_KEYS:
        app_settings_repo.delete(key)
    with llm_provider._failure_lock:
        llm_provider._consecutive_failures = 0
    llm_provider.set_test_transport(None)


class TestRuntimeConfig:

    def test_db_key_used_without_restart(self, monkeypatch):
        """环境变量未配置 → 界面保存 Key 后立即可用，无需重启"""
        monkeypatch.setattr(config.settings, "llm_api_key", "")
        transport, calls = _capture_transport(_ok_response())
        llm_provider.set_test_transport(transport)

        assert llm_provider.is_configured() is False
        app_settings_repo.set("llm_api_key", "db-key")
        assert llm_provider.is_configured() is True

        assert llm_provider.chat("p", "s", "t") == "模型回复"
        assert calls[0].headers["Authorization"] == "Bearer db-key"

    def test_base_url_and_model_change_take_effect(self, monkeypatch):
        """界面切换服务商/模型后，请求打到新地址并携带新模型名"""
        monkeypatch.setattr(config.settings, "llm_api_key", "")
        transport, calls = _capture_transport(_ok_response())
        llm_provider.set_test_transport(transport)

        app_settings_repo.set("llm_api_key", "k")
        app_settings_repo.set("llm_base_url", "https://other-provider.example/v1")
        app_settings_repo.set("llm_model", "other-model")

        assert llm_provider.chat("p", "s", "t") == "模型回复"
        assert str(calls[0].url) == "https://other-provider.example/v1/chat/completions"
        assert json.loads(calls[0].content)["model"] == "other-model"

    def test_clearing_db_key_disables_again(self, monkeypatch):
        monkeypatch.setattr(config.settings, "llm_api_key", "")
        app_settings_repo.set("llm_api_key", "db-key")
        assert llm_provider.is_configured() is True
        app_settings_repo.delete("llm_api_key")
        assert llm_provider.is_configured() is False


class TestConnectionDiagnostic:

    def test_success_reports_latency(self):
        transport, calls = _capture_transport(_ok_response("OK"))
        llm_provider.set_test_transport(transport)

        result = llm_provider.test_connection("k", "https://x.example/v1", "m")
        assert result["ok"] is True
        assert "连接成功" in result["message"]
        assert "OK" in result["message"]
        assert result["model"] == "m"
        assert result["latency_ms"] is not None
        assert str(calls[0].url) == "https://x.example/v1/chat/completions"
        assert calls[0].headers["Authorization"] == "Bearer k"

    def test_401_translated_to_friendly_message(self):
        transport, _ = _capture_transport(httpx.Response(401, text="unauthorized"))
        llm_provider.set_test_transport(transport)

        result = llm_provider.test_connection("bad-key", "https://x.example/v1", "m")
        assert result["ok"] is False
        assert "密钥" in result["message"]
        assert "unauthorized" not in result["message"], "不应把原始响应透给用户"

    def test_404_hints_base_url(self):
        transport, _ = _capture_transport(httpx.Response(404, text="not found"))
        llm_provider.set_test_transport(transport)

        result = llm_provider.test_connection("k", "https://x.example", "m")
        assert result["ok"] is False
        assert "Base URL" in result["message"]

    def test_connect_error_friendly(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        llm_provider.set_test_transport(httpx.MockTransport(handler))
        result = llm_provider.test_connection("k", "https://x.example/v1", "m")
        assert result["ok"] is False
        assert "无法连接" in result["message"]

    def test_missing_key_short_circuits(self):
        llm_provider.set_test_transport(None)
        result = llm_provider.test_connection("", "https://x.example/v1", "m")
        assert result["ok"] is False
        assert "API Key" in result["message"]

    def test_does_not_touch_breaker_or_receipts(self, monkeypatch):
        """诊断调用不受熔断限制，也不写回执、不计熔断"""
        monkeypatch.setattr(config.settings, "llm_max_consecutive_failures", 2)
        with llm_provider._failure_lock:
            llm_provider._consecutive_failures = 2  # 熔断已打开

        transport, calls = _capture_transport(_ok_response("OK"))
        llm_provider.set_test_transport(transport)

        result = llm_provider.test_connection("k", "https://x.example/v1", "m")
        assert result["ok"] is True, "诊断动作应允许在熔断后验证修复"
        assert len(calls) == 1

        with llm_provider._failure_lock:
            assert llm_provider._consecutive_failures == 2, "诊断调用不应改动熔断计数"
