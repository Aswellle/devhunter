"""
tests/test_sources/test_wizard_flow.py
添加数据源向导全链路回归：discover → preview → create → clone + 错误边界。

背景：fetch_and_parse 的 keywords 位置参数与 preview/tester 的调用失配后，
预览 100% 抛 TypeError（包成 200 + error 文案），向导"继续"永远点不了；
create/clone 端点把 Pydantic 模型当 dict 用（body.get）直接 500。
本文件用真实引擎 + MockTransport HTTP 层锁住整条链路。
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.crawler import engine as engine_module
from app.core.security import create_access_token
from app.main import app

client = TestClient(app)

RSS_BODY = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>测试订阅</title>
<item><title>文章一</title><link>https://example.com/1</link><description>摘要一</description></item>
<item><title>文章二</title><link>https://example.com/2</link><description>摘要二</description></item>
<item><title>文章三</title><link>https://example.com/3</link><description>摘要三</description></item>
</channel></rss>"""

HTML_BODY = """<html><head><title>测试列表</title></head><body>
<article><h2><a href="/a/1">标题一</a></h2><p>摘要一的内容足够长</p></article>
<article><h2><a href="/a/2">标题二</a></h2><p>摘要二的内容足够长</p></article>
<article><h2><a href="/a/3">标题三</a></h2><p>摘要三的内容足够长</p></article>
</body></html>"""

JSON_BODY = """{"data": {"items": [
  {"title": "条目一", "url": "https://example.com/j/1", "description": "描述一"},
  {"title": "条目二", "url": "https://example.com/j/2", "description": "描述二"},
  {"title": "条目三", "url": "https://example.com/j/3", "description": "描述三"}
]}}"""


def _auth_headers():
    token = create_access_token({"sub": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def fake_http(monkeypatch):
    """把发现器与引擎的 HTTP 层替换为按 URL 特征路由的 MockTransport 客户端"""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "feed" in url:
            return httpx.Response(200, text=RSS_BODY, headers={"content-type": "application/rss+xml"})
        if "api" in url:
            return httpx.Response(200, text=JSON_BODY, headers={"content-type": "application/json"})
        return httpx.Response(200, text=HTML_BODY, headers={"content-type": "text/html"})

    fake = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(engine_module, "get_http_client", lambda: fake)
    monkeypatch.setattr("app.sources.discovery.get_http_client", lambda: fake)
    yield fake
    fake.close()


def _discover(url: str) -> dict:
    resp = client.post("/api/sources/discover", headers=_auth_headers(), json={"url": url})
    assert resp.status_code == 200
    return resp.json()


def _preview(url: str, discovery: dict) -> dict:
    resp = client.post(
        "/api/sources/preview", headers=_auth_headers(),
        json={"url": url, "discovery_result": discovery},
    )
    assert resp.status_code == 200
    return resp.json()


class TestDiscoverToPreview:
    """发现 → 预览主链路（真实引擎，覆盖三种来源类型）"""

    def test_rss_roundtrip(self, fake_http):
        d = _discover("https://example.com/feed")
        assert d["source_type"] == "rss"
        assert d["errors"] == []
        assert d["list_selector"] == "rss:"

        p = _preview("https://example.com/feed", d)
        assert p["success"] is True, p["error"]
        assert p["total_found"] >= 3
        assert p["items"][0]["title"] == "文章一"
        assert p["items"][0]["url"] == "https://example.com/1"

    def test_html_roundtrip(self, fake_http):
        d = _discover("https://example.com/list")
        assert d["source_type"] == "html"
        assert d["list_selector"], "应发现列表选择器"
        assert d["title_selector"] and d["link_selector"]

        p = _preview("https://example.com/list", d)
        assert p["success"] is True, p["error"]
        assert len(p["items"]) >= 3
        first = p["items"][0]
        assert first["title"] == "标题一"
        assert first["url"] == "https://example.com/a/1", "相对链接应按页面 URL 补全"

    def test_json_roundtrip(self, fake_http):
        d = _discover("https://example.com/api/topics")
        assert d["source_type"] == "json"
        assert d["list_selector"] == "json:data.items"

        p = _preview("https://example.com/api/topics", d)
        assert p["success"] is True, p["error"]
        assert p["total_found"] >= 3
        assert p["items"][0]["title"] == "条目一"


class TestDiscoverErrorBoundaries:
    """发现的错误边界：都应返回 200 + errors 清单（而非 5xx）"""

    @pytest.mark.parametrize("bad_url", [
        "ftp://example.com/list",        # 不支持的协议
        "http://127.0.0.1:8000/admin",   # 环回地址（SSRF）
        "http://192.168.1.1/",           # 私有地址（SSRF）
        "http://169.254.169.254/meta",   # 云元数据地址（SSRF）
        "not a url at all",              # 无法解析
        "https://nonexistent-host-3f8a2b.example/",  # DNS 无法解析
    ])
    def test_bad_urls_return_errors_not_5xx(self, fake_http, bad_url):
        d = _discover(bad_url)
        assert d["errors"], f"坏 URL 应产生错误清单: {bad_url}"
        assert d["source_type"] == "unknown"
        assert not d["list_selector"], "失败时不应产出选择器"

    def test_preview_with_ssrf_url_reports_error(self, fake_http):
        p = _preview("http://127.0.0.1:9000/x", {"url": "http://127.0.0.1:9000/x", "source_type": "html"})
        assert p["success"] is False
        assert "SSRF" in p["error"]

    def test_preview_malformed_discovery_result_400(self):
        resp = client.post(
            "/api/sources/preview", headers=_auth_headers(),
            json={"url": "https://example.com", "discovery_result": {"bogus_key": 1}},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_DISCOVERY"


class TestSaveTemplate:
    """保存/克隆模板端点（曾因 body.get 访问 Pydantic 模型 500）"""

    def test_create_source_201(self):
        resp = client.post("/api/sources", headers=_auth_headers(), json={
            "name": "回归测试源",
            "source_url": "https://example.com/list",
            "selectors": {"list": "article", "title": "h2", "link": "a", "summary": "p"},
            "keywords": ["测试"],
            "cron_expression": "0 9 * * *",
            "category": "tech",
            "tags": ["回归"],
        })
        assert resp.status_code == 201, resp.text
        template = resp.json()
        assert template["name"] == "回归测试源"
        assert template["kind"] == "custom"
        assert template["config"]["source"]["url"] == "https://example.com/list"
        assert template["category"] == "tech"
        assert template["tags"] == ["回归"]

        # 字段缺省（category/tags 不传）也应成功
        resp2 = client.post("/api/sources", headers=_auth_headers(), json={
            "name": "最小参数源",
            "source_url": "https://example.com/min",
        })
        assert resp2.status_code == 201, resp2.text

    def test_clone_source(self):
        created = client.post("/api/sources", headers=_auth_headers(), json={
            "name": "待克隆源", "source_url": "https://example.com/clone",
        }).json()
        resp = client.post(f"/api/sources/{created['id']}/clone", headers=_auth_headers(), json={})
        assert resp.status_code == 200, resp.text
        cloned = resp.json()
        assert cloned["id"] != created["id"]
        assert cloned["name"].startswith("Copy of")
        assert cloned["config"]["source"]["url"] == "https://example.com/clone"

    def test_clone_nonexistent_404(self):
        resp = client.post("/api/sources/nonexistent/clone", headers=_auth_headers(), json={})
        assert resp.status_code == 404
