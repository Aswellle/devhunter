"""
tests/test_api/test_notifications_api.py
通知 API 与触发集成回归（PROD-003）。

覆盖：渠道 CRUD 的 SSRF 校验、规则 CRUD、投递重试、手动投递，
以及 task 失败/部分成功经 jobs 触发 health 事件、keyword 触发。
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _deterministic_ssrf(monkeypatch):
    """渠道 API 直接调用 SSRF 预检（含 DNS 解析）：CI 环境 hooks.example.com
    不可解析会 fail-closed 400，测试必须确定——IP 字面量按黑名单拒绝，
    域名一律放行（真正的私网/回环拦截由 ssrf 单测覆盖）。"""
    from urllib.parse import urlparse

    def fake_resolve(url: str):
        host = urlparse(url).hostname or ""
        if host in ("127.0.0.1", "0.0.0.0", "::1") or host.startswith("10.")                 or host.startswith("192.168."):
            return False, f"禁止访问私有/保留 IP 地址: {host}", None
        return True, "", None

    monkeypatch.setattr("app.core.ssrf.resolve_and_validate_url", fake_resolve)


def _auth():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


def _channel(url="https://hooks.example.com/api", name=None):
    return client.post("/api/notifications/channels", json={
        "name": name or f"渠道 {uuid.uuid4().hex[:6]}",
        "url": url,
    }, headers=_auth())


class TestChannelApi:
    def test_create_and_list_channel(self):
        created = _channel()
        assert created.status_code == 201, created.text
        channel = created.json()
        assert channel["enabled"] == 1

        listed = client.get("/api/notifications/channels", headers=_auth()).json()
        assert any(c["id"] == channel["id"] for c in listed)

    def test_private_webhook_is_rejected(self):
        resp = _channel("http://127.0.0.1/hook")
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "UNSAFE_WEBHOOK_URL"

    def test_private_webhook_rejected_on_update(self):
        channel = _channel().json()
        resp = client.patch(f"/api/notifications/channels/{channel['id']}",
                            json={"url": "http://10.0.0.5/hook"}, headers=_auth())
        assert resp.status_code == 400

    def test_delete_channel(self):
        channel = _channel().json()
        resp = client.delete(f"/api/notifications/channels/{channel['id']}", headers=_auth())
        assert resp.status_code == 204


class TestRuleApi:
    def test_create_rule_requires_existing_channel(self):
        resp = client.post("/api/notifications/rules", json={
            "name": "r", "trigger_type": "keyword",
            "config": {"keywords": ["x"]}, "channel_id": "missing",
        }, headers=_auth())
        assert resp.status_code == 400

    def test_keyword_rule_requires_keywords(self):
        channel = _channel().json()
        resp = client.post("/api/notifications/rules", json={
            "name": "r", "trigger_type": "keyword", "config": {},
            "channel_id": channel["id"],
        }, headers=_auth())
        assert resp.status_code == 400

    def test_rule_crud_roundtrip(self):
        channel = _channel().json()
        created = client.post("/api/notifications/rules", json={
            "name": "Rust 追踪", "trigger_type": "keyword",
            "config": {"keywords": ["rust"]}, "channel_id": channel["id"],
        }, headers=_auth())
        assert created.status_code == 201
        rule = created.json()
        assert rule["trigger_type"] == "keyword"

        patched = client.patch(f"/api/notifications/rules/{rule['id']}",
                               json={"enabled": False}, headers=_auth())
        assert patched.status_code == 200
        assert patched.json()["enabled"] == 0

        assert client.delete(f"/api/notifications/rules/{rule['id']}",
                             headers=_auth()).status_code == 204


class TestDeliveryApi:
    def test_run_and_retry_endpoints(self, monkeypatch):
        from app.notifications import service as notif

        calls = []

        class _Client:
            def post(self, url, json=None, headers=None, timeout=None):
                calls.append(url)
                return type("R", (), {"status_code": 500})()

        monkeypatch.setattr(notif, "get_http_client", lambda: _Client())
        monkeypatch.setattr(notif, "_ssrf_check", lambda url: (True, ""))

        channel = _channel().json()
        rule = client.post("/api/notifications/rules", json={
            "name": "关键词", "trigger_type": "keyword",
            "config": {"keywords": [f"kw{uuid.uuid4().hex[:6]}"]},
            "channel_id": channel["id"],
        }, headers=_auth()).json()

        notif.dispatch_keyword_items([
            {"id": uuid.uuid4().hex, "title": rule["config"]["keywords"][0],
             "url": "https://example.com/x"},
        ])
        stats = client.post("/api/notifications/deliveries/run", headers=_auth()).json()
        assert stats["failed"] >= 1
        assert calls, "应至少发起一次投递"

        deliveries = client.get("/api/notifications/deliveries", headers=_auth()).json()
        mine = [d for d in deliveries if d["rule_id"] == rule["id"]]
        assert mine and mine[0]["status"] == "failed"

        retried = client.post(
            f"/api/notifications/deliveries/{mine[0]['id']}/retry", headers=_auth())
        assert retried.status_code == 200
        assert retried.json()["status"] == "pending"


class TestJobTriggerIntegration:
    def test_failed_task_dispatches_health_event(self, monkeypatch):
        """任务抓取失败 → jobs 触发 health 通知（配置了 failure 规则时）。"""
        import uuid as _uuid
        from app.crawler.engine import CrawlResult
        from app.notifications import repo as notif_repo
        from app.repositories.execution_repo import execution_repo
        from app.repositories.task_repo import task_repo
        from app.scheduler import jobs

        monkeypatch.setattr("app.services.task_service.MAX_TASKS_LIMIT", 10**6)
        channel = notif_repo.create_channel("健康", "https://hooks.example.com/h")["id"]
        rule_id = notif_repo.create_rule(
            "失败告警", "health", {"kinds": ["failure"]}, channel,
        )["id"]

        task_id = task_repo.insert({
            "name": f"失败任务 {_uuid.uuid4().hex[:6]}",
            "source_url": "https://example.com/",
            "selector_list": "div",
            "selector_title": "h2",
            "selector_link": "a",
            "cron_expression": "0 9 * * *",
        })["id"]
        exec_id = str(_uuid.uuid4())
        from datetime import datetime, timezone
        execution_repo.create_running(
            exec_id, task_id,
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

        def fake_fetch(**kwargs):
            return CrawlResult(error="HTTP 502 Bad Gateway", http_status=502)

        monkeypatch.setattr("app.crawler.engine.fetch_and_parse", fake_fetch)
        jobs.execute_task(task_id, exec_id=exec_id, _skip_lock=True)

        rows = notif_repo.list_deliveries_for_rule(rule_id)
        assert rows, "失败任务必须触发 health 通知（旧链路上没有通知）"
        assert rows[0]["payload"]["source"]["kind"] == "failure"

    def test_new_items_dispatch_keyword_event(self, monkeypatch):
        from app.crawler.engine import CrawlItem, CrawlResult
        from app.notifications import repo as notif_repo
        from app.repositories.execution_repo import execution_repo
        from app.repositories.task_repo import task_repo
        from app.scheduler import jobs

        monkeypatch.setattr("app.services.task_service.MAX_TASKS_LIMIT", 10**6)
        token = f"kw{uuid.uuid4().hex[:6]}"
        channel = notif_repo.create_channel("关键词", "https://hooks.example.com/k")["id"]
        rule_id = notif_repo.create_rule(
            "关键词命中", "keyword", {"keywords": [token]}, channel,
        )["id"]

        task_id = task_repo.insert({
            "name": f"采集任务 {uuid.uuid4().hex[:6]}",
            "source_url": "https://example.com/",
            "selector_list": "div",
            "selector_title": "h2",
            "selector_link": "a",
            "cron_expression": "0 9 * * *",
        })["id"]
        exec_id = str(uuid.uuid4())
        from datetime import datetime, timezone
        execution_repo.create_running(
            exec_id, task_id,
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

        monkeypatch.setattr(
            "app.crawler.engine.fetch_and_parse",
            lambda **kwargs: CrawlResult(items=[CrawlItem(
                title=f"Story about {token}",
                url=f"https://example.com/{uuid.uuid4().hex}",
                url_hash=uuid.uuid4().hex,
                summary="s",
            )], list_count=1),
        )
        jobs.execute_task(task_id, exec_id=exec_id, _skip_lock=True)

        rows = notif_repo.list_deliveries_for_rule(rule_id)
        assert rows, "关键词命中的新条目必须入队通知"
        assert rows[0]["payload"]["item"]["title"].endswith(token)
