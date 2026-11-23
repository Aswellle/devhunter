"""
tests/test_llm/test_receipts_cursor.py
调用记录游标（keyset）分页 + 预算硬闸回归。

1. 游标分页必须在"边翻页边有新调用"时保持稳定——offset 分页会因队首
   插入而整体错位（重复/漏项）。
2. 预算硬闸：剩余预算不足本次调用（输入估算 + 输出上限）时不得发请求。
   旧实现只检查"剩余 > 0"，剩余 50 token 时一次调用仍可能烧掉数千 token。
"""
import json
import time

import httpx
import pytest

from app.core import config
from app.llm import provider as provider_module
from app.llm.provider import llm_provider
from app.llm.receipt_repo import model_receipt_repo
from app.services.llm_config_service import llm_config_service, _decode_cursor, _encode_cursor


def _insert_receipt(tokens: int = 10) -> str:
    rid = model_receipt_repo.create_pending("test", "m", f"hash-{tokens}-{rid_seed()}")
    model_receipt_repo.complete(rid, f"result-{rid}", tokens, 0, 1)
    return rid


def rid_seed() -> str:
    import uuid
    return uuid.uuid4().hex


class TestCursorPagination:
    def test_cursor_roundtrip(self):
        anchor = ("2026-01-01T00:00:00Z", "abc-123")
        assert _decode_cursor(_encode_cursor(anchor)) == anchor
        assert _decode_cursor(None) is None
        assert _decode_cursor("not-base64!!") is None

    def test_pages_have_no_duplicates_and_cover_all(self):
        ids = [_insert_receipt() for _ in range(5)]

        seen: list[str] = []
        cursor = None
        for _ in range(10):
            page = llm_config_service.usage(limit=2, cursor=cursor)
            seen.extend(r["id"] for r in page["receipts"])
            cursor = page["next_cursor"]
            if cursor is None:
                break

        assert len(seen) == len(set(seen)), "翻页不得出现重复条目"
        for rid in ids:
            assert rid in seen, "翻页必须覆盖全部回执"

    def test_new_receipts_do_not_shift_later_pages(self):
        """游标锚定在上一页末条：翻页期间新增记录不会让后续页错位。"""
        base_ids = [_insert_receipt() for _ in range(4)]

        page1 = llm_config_service.usage(limit=2, cursor=None)
        first_page_ids = [r["id"] for r in page1["receipts"]]
        assert page1["next_cursor"]

        # 翻页间隙插入一条新回执（毫秒精度下必然排在锚点之前）
        time.sleep(0.003)
        late_id = _insert_receipt()

        page2 = llm_config_service.usage(limit=2, cursor=page1["next_cursor"])
        page2_ids = [r["id"] for r in page2["receipts"]]
        assert late_id not in page2_ids, "新记录不应出现在后续页"
        assert not (set(page2_ids) & set(first_page_ids)), "后续页不得重复第一页"

    def test_offset_path_still_returns_cursor(self):
        """旧 offset 调用方也能拿到下一页游标，随后即可切换为游标翻页。"""
        _insert_receipt()
        page = llm_config_service.usage(limit=1, offset=0)
        assert "next_cursor" in page


class TestBudgetHardGuard:
    @pytest.fixture()
    def provider(self, monkeypatch):
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

    def test_estimate_over_budget_skips_http_call(self, provider, monkeypatch):
        used_now = model_receipt_repo.tokens_since(provider_module.utc_day_start_iso())
        # 只剩 200 token：一次常规调用（估算输入 + max_tokens）远超此值
        monkeypatch.setattr(config.settings, "llm_daily_token_budget", used_now + 200)
        assert provider.remaining_budget() == 200

        state = {"count": 0}

        def handler(request):
            state["count"] += 1
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "x"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            })

        provider.set_test_transport(httpx.MockTransport(handler))
        long_prompt = "长" * 2000  # 估算 1000 token + max_tokens 600

        assert provider.chat(long_prompt, "系统提示", "t", max_tokens=600) is None
        assert state["count"] == 0, "预算不足以覆盖本次调用时不得发起 HTTP 请求"

    def test_small_call_within_budget_still_runs(self, provider, monkeypatch):
        used_now = model_receipt_repo.tokens_since(provider_module.utc_day_start_iso())
        monkeypatch.setattr(config.settings, "llm_daily_token_budget", used_now + 5000)

        state = {"count": 0}

        def handler(request):
            state["count"] += 1
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            })

        provider.set_test_transport(httpx.MockTransport(handler))
        assert provider.chat("短提示", "sys", "t", max_tokens=100) == "ok"
        assert state["count"] == 1

    def test_status_exposes_budget_breaker(self, provider, monkeypatch):
        used_now = model_receipt_repo.tokens_since(provider_module.utc_day_start_iso())
        monkeypatch.setattr(config.settings, "llm_daily_token_budget", used_now)
        status = provider.status()
        assert status["budget_breaker_open"] is True
        assert status["remaining"] == 0
