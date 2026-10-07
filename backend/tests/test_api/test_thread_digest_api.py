"""
tests/test_api/test_thread_digest_api.py
Thread AI 综述手动生成端点测试：POST /api/items/threads/{id}/digest
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.core.security import create_access_token
from app.llm import provider as provider_module
from app.llm.config import LLM_SETTING_KEYS
from app.llm.provider import llm_provider
from app.main import app
from app.repositories.item_repo import item_repo
from app.repositories.settings_repo import app_settings_repo
from app.repositories.task_repo import task_repo
from app.repositories.thread_repo import thread_repo
from datetime import datetime, timezone
import uuid

client = TestClient(app)


def _auth_headers():
    token = create_access_token({"sub": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _isolate():
    """隔离共享测试库的 LLM 配置覆盖与 provider 单例状态"""
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


def _thread_with_items(n_items: int) -> str:
    """创建任务 + n 条同事件条目，组装成一个 Thread"""
    task_id = task_repo.insert({
        "name": f"digest api 任务 {uuid.uuid4().hex[:6]}",
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
            "url": f"https://example.com/api-digest/{token}/{i}",
            "url_hash": f"digest-api-hash-{token}-{i}",
            "summary": f"事件摘要 {i}",
            "fetched_at": now,
        }
        for i in range(n_items)
    ])
    items, _ = item_repo.query(task_id=task_id)
    first = items[0]
    thread_id = thread_repo.create(title=first["title"], item_id=first["id"], platform="srcA")
    for idx, it in enumerate(items[1:], start=2):
        thread_repo.add_item(
            thread_id=thread_id, item_id=it["id"], similarity=0.8,
            title=it["title"], platform=f"src{idx}",
        )
    return thread_id


class TestDigestEndpointAuth:

    def test_requires_auth(self):
        assert client.post("/api/items/threads/some-id/digest").status_code == 401


class TestDigestEndpoint:

    def test_unknown_thread_404(self, provider_keys):
        response = client.post(
            "/api/items/threads/nonexistent/digest", headers=_auth_headers(),
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_single_item_409(self, provider_keys):
        thread_id = _thread_with_items(1)
        response = client.post(
            f"/api/items/threads/{thread_id}/digest", headers=_auth_headers(),
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "TOO_FEW_ITEMS"

    def test_not_configured_409(self, provider_keys):
        """环境变量与界面配置都没有 Key → 明确引导接入"""
        thread_id = _thread_with_items(2)
        response = client.post(
            f"/api/items/threads/{thread_id}/digest", headers=_auth_headers(),
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"

    def test_generate_success(self, provider_keys, monkeypatch):
        monkeypatch.setattr(config.settings, "llm_api_key", "test-key")
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
            "choices": [{"message": {"content": "端到端综述"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }))
        llm_provider.set_test_transport(transport)

        thread_id = _thread_with_items(3)
        response = client.post(
            f"/api/items/threads/{thread_id}/digest", headers=_auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["digest"] == "端到端综述"
        assert data["digest_at"]

    @pytest.fixture()
    def provider_keys(self, monkeypatch):
        """默认无 Key 的干净环境（检测 LLM_NOT_CONFIGURED 路径用）"""
        monkeypatch.setattr(config.settings, "llm_api_key", "")
        monkeypatch.setattr(config.settings, "llm_daily_token_budget", 1_000_000)
        monkeypatch.setattr(config.settings, "llm_max_consecutive_failures", 3)
