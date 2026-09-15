"""
tests/test_sources/test_preview.py
Preview Extraction 单元测试
"""
import pytest
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
