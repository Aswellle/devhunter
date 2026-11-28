"""
tests/test_api/test_api_tokens.py
独立命名机器令牌回归（SEC-002）。

验收：可创建独立命名 token（含 scope/创建/过期/最后使用/撤销状态）；
Authorization Header 优先；query token 为可关闭的兼容模式；撤销立即
无效；只读 scope 不能触发写操作；日志对 token query 脱敏。
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token, create_api_token, machine_token
from app.main import app

client = TestClient(app)


def _auth():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


def _bearer(raw: str) -> dict:
    return {"Authorization": f"Bearer {raw}"}


class TestTokenLifecycle:
    def test_create_returns_plaintext_once_and_metadata(self):
        resp = client.post("/api/tokens", json={"name": "rss reader"}, headers=_auth())
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["token"].startswith("dh_")
        assert body["scope"] == "read"
        assert body["created_at"]
        assert body["revoked_at"] is None

        listed = client.get("/api/tokens", headers=_auth()).json()
        row = next(t for t in listed if t["id"] == body["id"])
        assert "token" not in row, "列表不得返回明文"
        assert "token_hash" not in row, "列表不得返回哈希"

    def test_header_token_grants_rss_read(self):
        _, raw = create_api_token(f"reader-{uuid.uuid4().hex[:6]}")
        resp = client.get("/api/rss", headers=_bearer(raw))
        assert resp.status_code == 200
        assert "application/rss+xml" in resp.headers["content-type"]

    def test_query_token_works_by_default(self):
        _, raw = create_api_token(f"reader-q-{uuid.uuid4().hex[:6]}")
        resp = client.get(f"/api/rss?token={raw}")
        assert resp.status_code == 200

    def test_query_token_disabled_when_setting_off(self, monkeypatch):
        _, raw = create_api_token(f"reader-off-{uuid.uuid4().hex[:6]}")
        monkeypatch.setattr(settings, "allow_query_token", False)

        assert client.get(f"/api/rss?token={raw}").status_code == 401
        # header 仍然可用（关闭 query 不等于关闭令牌）
        assert client.get("/api/rss", headers=_bearer(raw)).status_code == 200

    def test_revoke_is_immediate(self):
        record, raw = create_api_token(f"revoke-{uuid.uuid4().hex[:6]}")
        assert client.get("/api/rss", headers=_bearer(raw)).status_code == 200

        resp = client.delete(f"/api/tokens/{record['id']}", headers=_auth())
        assert resp.status_code == 204
        assert client.get("/api/rss", headers=_bearer(raw)).status_code == 401

    def test_expired_token_is_rejected(self):
        _, raw = create_api_token(
            f"expired-{uuid.uuid4().hex[:6]}",
            expires_at="2020-01-01T00:00:00Z",
        )
        assert client.get("/api/rss", headers=_bearer(raw)).status_code == 401

    def test_legacy_machine_token_still_works(self):
        assert client.get("/api/rss", headers=_bearer(machine_token())).status_code == 200


class TestScopeIsolation:
    def test_read_token_cannot_write(self):
        """命名令牌只用于机器只读出口：拿它写接口必须是 401。"""
        _, raw = create_api_token(f"scope-{uuid.uuid4().hex[:6]}")
        resp = client.patch("/api/items/batch",
                            json={"ids": [], "data": {}}, headers=_bearer(raw))
        assert resp.status_code == 401


class TestLogRedaction:
    def test_token_query_is_redacted(self):
        import logging
        from app.core.logging import _TokenRedactionFilter

        record = logging.LogRecord(
            "t", logging.INFO, __file__, 1,
            "GET /api/rss?limit=5&token=dh_FAKEFAKEFAKE123", (), None,
        )
        _TokenRedactionFilter().filter(record)
        message = record.getMessage()
        assert "dh_FAKEFAKEFAKE123" not in message
        assert "token=***" in message
        assert "limit=5" in message
