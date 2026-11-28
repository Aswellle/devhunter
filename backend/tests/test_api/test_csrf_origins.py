"""
tests/test_api/test_csrf_origins.py
CSRF Origin 白名单中间件测试：自定义域名放行、未知 Origin 拒绝。

中间件逐请求读取 settings.cors_origins_list，测试通过 monkeypatch
运行时配置来模拟"部署方注入了自定义域名"的场景。
"""
import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.main import app

client = TestClient(app)

_ALLOWED = "https://app.example.test"


@pytest.fixture
def origins(monkeypatch):
    """把白名单替换为自定义域名（模拟生产部署注入）。"""
    monkeypatch.setattr(config.settings, "cors_origins", _ALLOWED)


class TestCsrfOriginAllowlist:
    def test_write_request_from_allowed_origin_passes_csrf(self, origins):
        """自定义 HTTPS 域名发写请求：不应被 CSRF 拦截（无认证 → 401 而非 403）。"""
        resp = client.patch(
            "/api/items/batch",
            json={"ids": [], "data": {}},
            headers={"Origin": _ALLOWED},
        )
        assert resp.status_code != 403
        assert resp.json().get("error", {}).get("code") != "CSRF_ERROR"

    def test_write_request_from_unknown_origin_is_rejected(self, origins):
        resp = client.patch(
            "/api/items/batch",
            json={"ids": [], "data": {}},
            headers={"Origin": "https://evil.example.test"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "CSRF_ERROR"

    def test_referer_fallback_follows_allowlist(self, origins):
        """无 Origin 但带外站 Referer 的写请求同样拒绝。"""
        resp = client.patch(
            "/api/items/batch",
            json={"ids": [], "data": {}},
            headers={"Referer": "https://evil.example.test/page"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "CSRF_ERROR"

    def test_non_browser_request_without_origin_passes_csrf(self, origins):
        """两者都缺 → 非浏览器客户端（脚本/API 调用），放行给认证层。"""
        resp = client.patch("/api/items/batch", json={"ids": [], "data": {}})
        assert resp.status_code != 403

    def test_configured_trailing_slash_origin_is_accepted(self, monkeypatch):
        """部署方配置带尾斜杠时也应与浏览器 Origin 精确匹配。"""
        monkeypatch.setattr(config.settings, "cors_origins", _ALLOWED + "/")
        resp = client.patch(
            "/api/items/batch",
            json={"ids": [], "data": {}},
            headers={"Origin": _ALLOWED},
        )
        assert resp.status_code != 403
