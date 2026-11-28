"""
tests/test_sources/test_preview.py
Preview Extraction 单元测试
"""
import pytest
from app.crawler.engine import CrawlItem, CrawlResult
from app.sources.discovery import DiscoveryResult
from app.sources.preview import preview_extractor, PreviewResult


class TestPreviewExtractor:
    """预览提取器测试"""

    def test_preview_result_to_dict(self):
        """PreviewResult 序列化"""
        result = PreviewResult(
            success=True,
            items=[{"title": "Test", "url": "https://example.com"}],
            total_found=1,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert len(d["items"]) == 1

    def test_preview_result_empty(self):
        """空 PreviewResult"""
        result = PreviewResult()
        d = result.to_dict()
        assert d["success"] is False
        assert d["items"] == []


class TestPreviewJsonFieldMapping:
    """JSON 来源预览必须沿用自动发现的字段映射（SRC-001）。

    旧实现把 selectors 硬编码为 title/url/description：自动发现识别出
    name/html_url/body 等非标准字段后，预览阶段全部落空，向导无法继续。"""

    @staticmethod
    def _crawl(items, extracted=None):
        return CrawlResult(
            items=items,
            http_status=200,
            extracted_count=len(items) if extracted is None else extracted,
        )

    def _run(self, monkeypatch, discovery, crawl=None):
        captured: dict = {}

        def fake_fetch(url, selectors, keywords):
            captured["url"] = url
            captured["selectors"] = selectors
            return crawl if crawl is not None else self._crawl([
                CrawlItem(title="t", url="https://example.com/1", summary="s"),
            ])

        monkeypatch.setattr("app.sources.preview.fetch_and_parse", fake_fetch)
        result = preview_extractor.preview(
            "https://api.example.com/x", discovery, limit=5,
        )
        return result, captured

    def test_nonstandard_fields_use_discovered_mapping(self, monkeypatch):
        discovery = DiscoveryResult(
            url="https://api.example.com/repos",
            source_type="json",
            json_path="data.items",
            list_selector="json:data.items",
            title_selector="name",
            link_selector="html_url",
            summary_selector="body",
        )
        result, captured = self._run(monkeypatch, discovery)
        assert result.success is True
        assert captured["selectors"] == {
            "list": "json:data.items",
            "title": "name",
            "link": "html_url",
            "summary": "body",
        }
        assert result.items[0]["title"] == "t"

    def test_root_array_defaults_still_work(self, monkeypatch):
        discovery = DiscoveryResult(
            url="https://api.example.com/list",
            source_type="json",
            json_path="",
            list_selector="json:",
        )
        result, captured = self._run(monkeypatch, discovery)
        assert result.success is True
        assert captured["selectors"] == {
            "list": "json:",
            "title": "title",
            "link": "url",
            "summary": "description",
        }

    def test_json_post_list_selector_is_preserved(self, monkeypatch):
        """POST 场景的 list selector 含请求体，预览不得降级成 GET 路径。"""
        discovery = DiscoveryResult(
            url="https://api.example.com/graphql",
            source_type="json",
            json_path="data.list",
            list_selector='json-post:data.list|||{"query":"x"}',
            title_selector="name",
            link_selector="permalink",
        )
        result, captured = self._run(monkeypatch, discovery)
        assert result.success is True
        assert captured["selectors"]["list"] == 'json-post:data.list|||{"query":"x"}'
        assert captured["selectors"]["title"] == "name"

    def test_zero_extracted_reports_semantic_error(self, monkeypatch):
        """title/link 映射缺失时引擎逐条跳过——预览必须明确报错而不是
        静默返回 success + 空列表。"""
        discovery = DiscoveryResult(
            url="https://api.example.com/x",
            source_type="json",
            json_path="items",
            list_selector="json:items",
        )
        result, _ = self._run(monkeypatch, discovery, crawl=self._crawl([], extracted=0))
        assert result.success is False
        assert "title" in result.error and "link" in result.error
