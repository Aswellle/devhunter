"""
tests/test_llm/test_provider.py
LLM provider 单元测试：付费纪律（回执/复用/预算熔断/失败熔断）。
HTTP 层用 httpx.MockTransport 桩，绝不发起真实调用。
"""
import json

import httpx
import pytest

from app.core import config
from app.llm import provider as provider_module
from app.llm.provider import llm_provider
from app.llm.receipt_repo import model_receipt_repo

SYSTEM = "你是测试助手。"


def _stub_completion(text: str = "模型回复", fail: bool = False):
    """构建 MockTransport：计数请求次数，可返回成功或 500"""
    state = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["count"] += 1
        if fail:
            return httpx.Response(500, text="server error")
        payload = json.loads(request.content)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        })

    return httpx.MockTransport(handler), state


@pytest.fixture()
def provider(monkeypatch):
    """配置好 Key 的 provider，隔离单例状态与测试传输"""
    monkeypatch.setattr(config.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(config.settings, "llm_model", "test-model")
    monkeypatch.setattr(config.settings, "llm_daily_token_budget", 1_000_000)
    monkeypatch.setattr(config.settings, "llm_max_consecutive_failures", 3)
    with llm_provider._failure_lock:
        llm_provider._consecutive_failures = 0
    llm_provider._not_configured_logged = False
    llm_provider.set_test_transport(None)
    yield llm_provider
    llm_provider.set_test_transport(None)


class TestConfiguration:
    """未配置 → 静默关闭"""

    def test_disabled_without_key(self, monkeypatch):
        monkeypatch.setattr(config.settings, "llm_api_key", "")
        transport, state = _stub_completion()
        provider_module.llm_provider.set_test_transport(transport)
        assert llm_provider.chat("hi", SYSTEM, "test") is None
        assert state["count"] == 0, "未配置时不应发起任何 HTTP 调用"


class TestReceiptFlow:
    """回执先行 + 结果复用"""

    def test_success_creates_done_receipt_and_reuses(self, provider):
        transport, state = _stub_completion("第一版综述")
        provider.set_test_transport(transport)

        first = provider.chat("prompt-abc", SYSTEM, "thread_digest")
        assert first == "第一版综述"
        assert state["count"] == 1

        # 相同 (model, system, prompt) → 直接复用，不再发起请求
        second = provider.chat("prompt-abc", SYSTEM, "thread_digest")
        assert second == "第一版综述"
        assert state["count"] == 1, "相同输入应复用已付费结果"

    def test_different_prompt_calls_again(self, provider):
        transport, state = _stub_completion()
        provider.set_test_transport(transport)
        provider.chat("prompt-1", SYSTEM, "t")
        provider.chat("prompt-2", SYSTEM, "t")
        assert state["count"] == 2

    def test_failure_marks_receipt_failed(self, provider):
        transport, state = _stub_completion(fail=True)
        provider.set_test_transport(transport)
        assert provider.chat("p", SYSTEM, "t") is None
        stats = model_receipt_repo.stats(limit=5)
        assert stats[0]["status"] == "failed"
        assert stats[0]["error"]


class TestBudgetBreaker:
    """当日 token 预算熔断"""

    def test_exhausted_budget_blocks_calls(self, provider, monkeypatch):
        # 用真实回执把当日消耗推到只剩 5 token
        used_now = model_receipt_repo.tokens_since(
            provider_module.utc_day_start_iso()
        )
        monkeypatch.setattr(config.settings, "llm_daily_token_budget", used_now + 5)

        rid = model_receipt_repo.create_pending("test", "m", "h-budget")
        model_receipt_repo.complete(rid, "x", 10, 0, 1)  # 10 > 5 → 超预算
        assert provider.remaining_budget() == 0

        transport, state = _stub_completion()
        provider.set_test_transport(transport)
        assert provider.chat("prompt-budget", SYSTEM, "t") is None
        assert state["count"] == 0, "预算熔断后不应发起 HTTP 调用"


class TestFailureBreaker:
    """连续失败熔断"""

    def test_opens_after_consecutive_failures(self, provider):
        fail_transport, _ = _stub_completion(fail=True)
        provider.set_test_transport(fail_transport)

        for _ in range(3):  # max_consecutive_failures=3
            assert provider.chat("p", SYSTEM, "t") is None

        # 熔断打开后：换成功传输也不应再发请求
        ok_transport, ok_state = _stub_completion("should not be called")
        provider.set_test_transport(ok_transport)
        assert provider.chat("fresh-prompt", SYSTEM, "t") is None
        assert ok_state["count"] == 0, "连续失败熔断后不应发起 HTTP 调用"

    def test_success_resets_failure_counter(self, provider):
        fail_transport, _ = _stub_completion(fail=True)
        provider.set_test_transport(fail_transport)
        provider.chat("f1", SYSTEM, "t")
        provider.chat("f2", SYSTEM, "t")

        ok_transport, ok_state = _stub_completion("ok")
        provider.set_test_transport(ok_transport)
        assert provider.chat("s1", SYSTEM, "t") == "ok", "失败后成功应重置计数"
        with llm_provider._failure_lock:
            assert llm_provider._consecutive_failures == 0
