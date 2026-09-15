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
