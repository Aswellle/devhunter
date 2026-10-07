"""
tests/test_threads/test_digest.py
Thread AI 综述测试：提示词构建（纯函数）+ 生成流程（stub 传输）+ 手动生成。
"""
import httpx
import pytest

from app.core import config
from app.core.exceptions import (
    DigestGenerationFailedError,
    DigestTooFewItemsError,
    LLMNotConfiguredError,
    LLMUnavailableError,
    NotFoundError,
)
from app.llm import provider as provider_module
from app.llm.config import LLM_SETTING_KEYS
from app.llm.provider import llm_provider
from app.repositories.item_repo import item_repo
from app.repositories.settings_repo import app_settings_repo
from app.repositories.task_repo import task_repo
from app.repositories.thread_repo import thread_repo
from app.services.thread_service import thread_service
from app.threads.digest import DIGEST_SYSTEM_PROMPT, build_digest_prompt, generate_digest
from datetime import datetime, timezone
import uuid


@pytest.fixture(autouse=True)
def _clean_llm_overrides():
    """隔离共享测试库：界面覆盖的 LLM 配置不得影响 env 桩"""
    for key in LLM_SETTING_KEYS:
        app_settings_repo.delete(key)
    yield
    for key in LLM_SETTING_KEYS:
        app_settings_repo.delete(key)


def _stub(text: str = "这是一个多来源事件的中文综述。"):
    state = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["count"] += 1
        return httpx.Response(200, json={
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 200, "completion_tokens": 80},
        })

    return httpx.MockTransport(handler), state


@pytest.fixture()
def provider(monkeypatch):
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


def _thread_with_items(n_items: int) -> str:
    """创建任务 + n 条同标题条目，聚合成一个多来源 Thread"""
    task_id = task_repo.insert({
        "name": f"digest 任务 {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })["id"]
    token = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    item_repo.bulk_insert([
        {
            "task_id": task_id,
            "title": f"同一事件报道 {token} #{i}",
            "url": f"https://example.com/digest/{token}/{i}",
            "url_hash": f"digest-hash-{token}-{i}",
            "summary": f"事件摘要 {i}",
            "fetched_at": now,
        }
        for i in range(n_items)
    ])
    items, _ = item_repo.query(task_id=task_id)
    # 直接用 repo 组装一个 Thread（不走聚类评分，聚焦综述逻辑）
    first = items[0]
    thread_id = thread_repo.create(title=first["title"], item_id=first["id"], platform="srcA")
    for idx, it in enumerate(items[1:], start=2):
        thread_repo.add_item(
            thread_id=thread_id, item_id=it["id"], similarity=0.8,
            title=it["title"], platform=f"src{idx}",
        )
    return thread_id


class TestBuildDigestPrompt:
    """提示词构建（纯函数）"""

    def test_contains_materials(self):
        items = [
            {"task_name": "Hacker News", "title": "OpenAI 发布 X", "summary": "官方公告"},
            {"task_name": "V2EX", "title": "如何看待 X", "summary": "社区讨论"},
        ]
        system, user = build_digest_prompt("X 事件", items)
        assert system == DIGEST_SYSTEM_PROMPT
        assert "[Hacker News] OpenAI 发布 X" in user
        assert "[V2EX] 如何看待 X" in user
        assert "事件标题：X 事件" in user

    def test_caps_items_and_summary(self):
        items = [
            {"task_name": f"src{i}", "title": f"t{i}", "summary": "长" * 500}
            for i in range(15)
        ]
        _, user = build_digest_prompt("标题", items)
        assert "src9]" in user and "src10]" not in user, "最多 10 条材料"
        assert "长" * 300 in user and "长" * 301 not in user, "摘要截断 300 字符"

    def test_empty_summary_omits_line(self):
        _, user = build_digest_prompt("T", [{"task_name": "A", "title": "x", "summary": None}])
        assert "摘要：" not in user


class TestGenerateDigest:
    """生成流程"""

    def test_generates_and_stores(self, provider):
        thread_id = _thread_with_items(3)
        transport, state = _stub("事件综述正文")
        provider.set_test_transport(transport)

        text = generate_digest(thread_id)

        assert text == "事件综述正文"
        assert state["count"] == 1
        thread = thread_repo.get(thread_id)
        assert thread["digest"] == "事件综述正文"
        assert thread["digest_at"]

    def test_idempotent(self, provider):
        thread_id = _thread_with_items(2)
        transport, state = _stub()
        provider.set_test_transport(transport)
        first = generate_digest(thread_id)
        second = generate_digest(thread_id)
        assert first == second
        assert state["count"] == 1, "已有综述不重复调用"

    def test_single_item_skipped(self, provider):
        thread_id = _thread_with_items(1)
        transport, state = _stub()
        provider.set_test_transport(transport)
        assert generate_digest(thread_id) is None
        assert state["count"] == 0, "单条目不调用 LLM"

    def test_llm_unavailable_returns_none(self, provider, monkeypatch):
        monkeypatch.setattr(config.settings, "llm_api_key", "")
        thread_id = _thread_with_items(2)
        transport, state = _stub()
        provider.set_test_transport(transport)
        assert generate_digest(thread_id) is None
        assert state["count"] == 0

    def test_unknown_thread(self, provider):
        assert generate_digest("nonexistent") is None


class TestManualDigest:
    """手动生成（thread_service.generate_thread_digest）：显式动作，错误要明确"""

    def test_generates(self, provider):
        thread_id = _thread_with_items(3)
        transport, state = _stub("手动生成的综述")
        provider.set_test_transport(transport)

        result = thread_service.generate_thread_digest(thread_id)
        assert result["digest"] == "手动生成的综述"
        assert result["digest_at"]
        assert state["count"] == 1

    def test_existing_digest_returns_without_call(self, provider):
        thread_id = _thread_with_items(2)
        transport, state = _stub()
        provider.set_test_transport(transport)
        thread_service.generate_thread_digest(thread_id)
        assert state["count"] == 1

        again = thread_service.generate_thread_digest(thread_id, force=False)
        assert again["digest"] == "这是一个多来源事件的中文综述。"
        assert state["count"] == 1, "已有综述且未 force → 不重复调用"

    def test_force_regenerates(self, provider):
        """force 重新走生成链路；相同材料在 chat 层命中结果复用，不重复付费"""
        thread_id = _thread_with_items(2)
        transport, state = _stub()
        provider.set_test_transport(transport)
        thread_service.generate_thread_digest(thread_id)
        first_at = thread_repo.get(thread_id)["digest_at"]
        thread_service.generate_thread_digest(thread_id, force=True)
        assert state["count"] == 1, "相同材料命中结果复用"
        assert thread_repo.get(thread_id)["digest_at"] >= first_at

    def test_single_item_raises(self, provider):
        thread_id = _thread_with_items(1)
        transport, _ = _stub()
        provider.set_test_transport(transport)
        with pytest.raises(DigestTooFewItemsError):
            thread_service.generate_thread_digest(thread_id)

    def test_not_configured_raises(self, provider, monkeypatch):
        monkeypatch.setattr(config.settings, "llm_api_key", "")
        thread_id = _thread_with_items(2)
        transport, state = _stub()
        provider.set_test_transport(transport)
        with pytest.raises(LLMNotConfiguredError):
            thread_service.generate_thread_digest(thread_id)
        assert state["count"] == 0

    def test_breaker_open_raises_unavailable(self, provider, monkeypatch):
        monkeypatch.setattr(config.settings, "llm_max_consecutive_failures", 2)
        with llm_provider._failure_lock:
            llm_provider._consecutive_failures = 2
        thread_id = _thread_with_items(2)
        transport, state = _stub()
        provider.set_test_transport(transport)
        try:
            with pytest.raises(LLMUnavailableError):
                thread_service.generate_thread_digest(thread_id)
            assert state["count"] == 0
        finally:
            with llm_provider._failure_lock:
                llm_provider._consecutive_failures = 0

    def test_generation_failure_raises(self, provider):
        thread_id = _thread_with_items(2)

        def failing_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        provider.set_test_transport(httpx.MockTransport(failing_handler))
        with pytest.raises(DigestGenerationFailedError):
            thread_service.generate_thread_digest(thread_id)

    def test_unknown_thread_raises(self, provider):
        with pytest.raises(NotFoundError):
            thread_service.generate_thread_digest("nonexistent")
