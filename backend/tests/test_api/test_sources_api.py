"""
tests/test_api/test_sources_api.py
模板向导 API 的回归测试。

背景：ef1df3b 把 sources.py 里 discover_source 上方的
`@router.post("/discover")` 装饰器连行一起删掉了 —— 函数还在、路由却不再注册，
前端向导第一步固定 405，向导因此完全不可用。这类「函数还在、路由没了」的回归
只有走一遍 HTTP 才能发现，单元测试直接调用函数是测不出来的。
"""
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.sources.discovery import DiscoveryResult

client = TestClient(app)


def _auth_headers():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


class TestSourceWizardAPI:
    """向导三步（discover / preview / test）必须注册且需要认证"""

    def test_discover_route_registered_and_returns_payload(self, monkeypatch):
        monkeypatch.setattr(
            "app.sources.discovery.url_discoverer.discover",
            lambda url: DiscoveryResult(
                url=url, source_type="html",
                list_selector="article", title_selector="h2", link_selector="a",
                candidate_count=7,
            ),
        )

        response = client.post("/api/sources/discover",
                               json={"url": "https://example.com"}, headers=_auth_headers())

        assert response.status_code == 200, "向导第一步的路由必须可用（曾被误删）"
        data = response.json()
        assert data["list_selector"] == "article"
        assert data["candidate_count"] == 7

    def test_discover_requires_auth(self):
        assert client.post("/api/sources/discover",
                           json={"url": "https://example.com"}).status_code == 401
