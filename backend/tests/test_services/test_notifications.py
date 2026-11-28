"""
tests/test_services/test_notifications.py
通知规则与投递回归（PROD-003）。

验收：规则可按 saved search（关键词）/ Thread / 来源健康触发；
投递具备幂等（同事件不重复）、重试次数上限与 dead-letter 状态、
手动重试；Webhook URL 受 SSRF 限制；秘密不出现在日志。
"""
import json
import uuid
from datetime import datetime, timezone

import httpx
import pytest

from app.core.database import get_db
from app.notifications import service as notif
from app.notifications import repo as notif_repo


def _channel(url: str = "https://hooks.example.com/abc", enabled: bool = True) -> str:
    return notif_repo.create_channel(
        name=f"渠道 {uuid.uuid4().hex[:6]}", url=url, enabled=enabled,
    )["id"]


def _rule(trigger: str, config: dict, channel_id: str, enabled: bool = True) -> str:
    return notif_repo.create_rule(
        name=f"规则 {uuid.uuid4().hex[:6]}",
        trigger_type=trigger,
        config=config,
        channel_id=channel_id,
        enabled=enabled,
    )["id"]


class _Resp:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text
        self.content = text.encode()
        self.headers = httpx.Headers({"content-type": "text/plain"})

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", "https://hooks.example.com/"),
                response=self,  # type: ignore[arg-type]
            )


class _Client:
    def __init__(self, responses=None, exc=None):
        self.calls = []
        self._responses = list(responses or [_Resp()])
        self._exc = exc

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": dict(headers or {})})
        if self._exc:
            raise self._exc
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


@pytest.fixture
def deliveries(monkeypatch):
    monkeypatch.setattr(notif, "get_http_client", lambda: _Client())
    monkeypatch.setattr(notif, "_ssrf_check", lambda url: (True, ""))


class TestRuleMatching:
    def test_keyword_rule_matches_new_item_title(self, deliveries):
        channel = _channel()
        token = uuid.uuid4().hex[:8]
        rule_id = _rule("keyword", {"keywords": [token]}, channel)

        fired = notif.dispatch_keyword_items([
            {"id": f"i-{token}-1", "title": f"Deep dive {token}",
             "url": "https://example.com/1"},
            {"id": f"i-{token}-2", "title": "Unrelated",
             "url": "https://example.com/2"},
        ])

        assert fired == 1
        rows = notif_repo.list_deliveries_for_rule(rule_id)
        assert len(rows) == 1

    def test_keyword_rule_respects_enabled_flag(self, deliveries):
        channel = _channel()
        _rule("keyword", {"keywords": ["rust"]}, channel, enabled=False)
        assert notif.dispatch_keyword_items([
            {"id": "i1", "title": "rust", "url": "https://example.com/1"},
        ]) == 0

    def test_thread_rule_matches_multi_source_thread(self, deliveries):
        channel = _channel()
        rule_id = _rule("thread", {"min_items": 2}, channel)

        thread_id = f"t-{uuid.uuid4().hex[:8]}"
        fired = notif.dispatch_thread_event({
            "thread_id": thread_id, "title": "Big event", "item_count": 3,
            "platforms": ["HN", "V2EX"],
        })

        assert fired == 1
        rows = notif_repo.list_deliveries_for_rule(rule_id)
        assert any(thread_id in (r.get("event_key") or "") for r in rows)

    def test_health_rule_matches_failed_task(self, deliveries):
        channel = _channel()
        rule_id = _rule("health", {"kinds": ["failure"]}, channel)
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        notif.dispatch_health_event({
            "task_id": task_id, "task_name": "HN", "kind": "failure",
            "message": "HTTP 502", "executed_at": "2026-11-28T10:00:00Z",
        })
        rows = notif_repo.list_deliveries_for_rule(rule_id)
        assert len(rows) == 1
        assert rows[0]["payload"]["source"]["kind"] == "failure"

        # 未订阅的 kind 不得命中本规则（共享库中其他规则的命中另行发生）
        notif.dispatch_health_event({
            "task_id": task_id, "task_name": "HN", "kind": "partial",
            "message": "page limit", "executed_at": "2026-11-28T10:00:00Z",
        })
        assert len(notif_repo.list_deliveries_for_rule(rule_id)) == 1


class TestDelivery:
    def test_successful_delivery_marks_sent(self, deliveries):
        channel = _channel()
        rule_id = _rule("keyword", {"keywords": ["rust"]}, channel)
        item_id = uuid.uuid4().hex
        notif.dispatch_keyword_items([
            {"id": item_id, "title": "rust", "url": "https://example.com/1"},
        ])

        notif.deliver_pending()

        row = notif_repo.list_deliveries_for_rule(rule_id)[0]
        assert row["status"] == "sent"
        assert row["sent_at"]

    def test_same_event_is_delivered_once(self, deliveries):
        channel = _channel()
        token = uuid.uuid4().hex[:8]
        rule_id = _rule("keyword", {"keywords": [token]}, channel)
        item = {"id": f"i-{token}", "title": f"rust {token}",
                "url": "https://example.com/1"}

        notif.dispatch_keyword_items([item])
        assert len(notif_repo.list_deliveries_for_rule(rule_id)) == 1
        # 同事件再次触发：该规则下仍只有一条投递记录
        notif.dispatch_keyword_items([item])
        assert len(notif_repo.list_deliveries_for_rule(rule_id)) == 1, "同事件必须幂等"
        notif.deliver_pending()
        row = notif_repo.list_deliveries_for_rule(rule_id)[0]
        assert row["status"] == "sent"

    def test_failure_retries_with_backoff_then_dead(self, monkeypatch):
        monkeypatch.setattr(notif, "_ssrf_check", lambda url: (True, ""))
        monkeypatch.setattr(notif, "get_http_client",
                            lambda: _Client([_Resp(500)]))
        channel = _channel()
        token = uuid.uuid4().hex[:8]
        rule_id = _rule("keyword", {"keywords": [token]}, channel)
        notif.dispatch_keyword_items([
            {"id": f"i-{token}", "title": f"rust {token}",
             "url": "https://example.com/1"},
        ])

        # 连续失败到上限（MAX_ATTEMPTS）
        for _ in range(notif.MAX_ATTEMPTS):
            # 绕过退避等待：直接把 next_attempt_at 置空
            with get_db() as conn:
                conn.execute(
                    "UPDATE notification_deliveries SET next_attempt_at = NULL "
                    "WHERE status = 'failed'"
                )
            stats = notif.deliver_pending()
            assert stats["failed"] >= 1 or stats["dead"] >= 1

        row = notif_repo.list_deliveries_for_rule(rule_id)[0]
        assert row["status"] == "dead"
        assert row["last_error"]

    def test_ssrf_blocked_url_is_not_called(self, monkeypatch):
        called = {"n": 0}

        def _client():
            called["n"] += 1
            return _Client()

        monkeypatch.setattr(notif, "get_http_client", _client)
        monkeypatch.setattr(notif, "_ssrf_check",
                            lambda url: (False, "private network"))
        token = uuid.uuid4().hex[:8]
        channel = _channel("https://192.168.1.10/hook")
        rule_id = _rule("keyword", {"keywords": [token]}, channel)
        notif.dispatch_keyword_items([
            {"id": f"i-{token}", "title": f"rust {token}",
             "url": "https://example.com/1"},
        ])

        notif.deliver_pending()

        assert called["n"] == 0, "SSRF 拦截的 URL 不得发起请求"
        row = notif_repo.list_deliveries_for_rule(rule_id)[0]
        assert row["status"] in ("failed", "dead")
        assert "private network" in (row["last_error"] or "")

    def test_manual_retry_resets_dead_delivery(self, monkeypatch):
        monkeypatch.setattr(notif, "_ssrf_check", lambda url: (True, ""))
        monkeypatch.setattr(notif, "get_http_client", lambda: _Client([_Resp(500)]))
        token = uuid.uuid4().hex[:8]
        channel = _channel()
        rule_id = _rule("keyword", {"keywords": [token]}, channel)
        notif.dispatch_keyword_items([
            {"id": f"i-{token}", "title": f"rust {token}",
             "url": "https://example.com/1"},
        ])
        with get_db() as conn:
            conn.execute(
                "UPDATE notification_deliveries SET status = 'dead', attempts = 5"
            )
        delivery_id = notif_repo.list_deliveries_for_rule(rule_id)[0]["id"]

        # 恢复可投递
        monkeypatch.setattr(notif, "get_http_client", lambda: _Client([_Resp(200)]))
        assert notif.retry_delivery(delivery_id) is True
        notif.deliver_pending()
        row = notif_repo.list_deliveries_for_rule(rule_id)[0]
        assert row["status"] == "sent"


class TestSecretHygiene:
    def test_last_error_does_not_contain_channel_url_credentials(self, monkeypatch):
        """错误信息不得回显完整 URL（可能含 path token）。"""
        monkeypatch.setattr(notif, "_ssrf_check", lambda url: (True, ""))
        monkeypatch.setattr(notif, "get_http_client", lambda: _Client(exc=httpx.ConnectError("boom")))
        token = uuid.uuid4().hex[:8]
        channel = _channel("https://hooks.example.com/secret-path-token")
        rule_id = _rule("keyword", {"keywords": [token]}, channel)
        notif.dispatch_keyword_items([
            {"id": f"i-{token}", "title": f"rust {token}",
             "url": "https://example.com/1"},
        ])

        notif.deliver_pending()
        row = notif_repo.list_deliveries_for_rule(rule_id)[0]
        assert "secret-path-token" not in (row["last_error"] or "")
