"""
tests/test_sources/test_discovery.py
URL Autodiscovery 单元测试
"""
import pytest
from app.sources.discovery import url_discoverer, DiscoveryResult


class TestURLDiscoverer:
    """URL 发现器测试"""

    def test_discover_result_to_dict(self):
        """DiscoveryResult 序列化"""
        result = DiscoveryResult(
            url="https://example.com",
            source_type="html",
            title="Test",
            list_selector="article",
        )
        d = result.to_dict()
        assert d["url"] == "https://example.com"
        assert d["source_type"] == "html"
        assert d["title"] == "Test"

    def test_discover_result_empty(self):
        """空 DiscoveryResult"""
        result = DiscoveryResult(url="https://example.com")
        d = result.to_dict()
        assert d["source_type"] == "unknown"
        assert d["errors"] == []


class _FakeResponse:
    """discover() 只用到 headers / text，这里给个够用的 httpx.Response 替身。"""

    def __init__(self, text: str, content_type: str = "text/html") -> None:
        self.text = text
        self.headers = {"content-type": content_type}


class TestDiscoveryProducesEngineReadyConfig:
    """
    发现结果必须能直接落成任务配置。

    历史上 rss/json 分支只填 source_type/json_path，list/title/link 全留空，
    向导于是写出缺少必填选择器的任务（schema 拒绝，或历史上撞 NOT NULL）。
    """

    def _discover(self, monkeypatch, body: str, content_type: str):
        from app.sources import discovery as m
        monkeypatch.setattr(m.URLDiscoverer, "_fetch",
                            lambda self, _url: _FakeResponse(body, content_type))
        return m.url_discoverer.discover("https://example.com/source")

    def test_rss_source_fills_all_required_selectors(self, monkeypatch):
        body = "<rss><channel><title>T</title><description>D</description></channel></rss>"
        result = self._discover(monkeypatch, body, "application/rss+xml")

        assert result.source_type == "rss"
        assert result.list_selector == "rss:"
        assert result.title_selector == "title"
        assert result.link_selector == "url"

    def test_json_root_array_detects_fields(self, monkeypatch):
        import json
        body = json.dumps([{"title": "A", "url": "https://a", "content": "c"}])
        result = self._discover(monkeypatch, body, "application/json")

        assert result.source_type == "json"
        assert result.list_selector == "json:"
        assert (result.title_selector, result.link_selector,
                result.summary_selector) == ("title", "url", "content")

    def test_json_nested_array_sets_dotted_path(self, monkeypatch):
        """嵌套 API（data.items）必须给出点分路径，否则抓到的是一整块 JSON。"""
        import json
        body = json.dumps({"data": {"items": [{"name": "A", "link": "https://a"}]}})
        result = self._discover(monkeypatch, body, "application/json")

        assert result.list_selector == "json:data.items"
        assert (result.title_selector, result.link_selector) == ("name", "link")

    def test_json_missing_known_fields_falls_back_to_engine_defaults(self, monkeypatch):
        """字段名都识别不出时回退到引擎默认值 title/url，而不是留空。"""
        import json
        body = json.dumps({"items": [{"weird_key": "A", "another": "B"}]})
        result = self._discover(monkeypatch, body, "application/json")

        assert result.list_selector == "json:items"
        assert result.title_selector == "title"
        assert result.link_selector == "url"
