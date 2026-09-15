"""
tests/test_sources/test_tester.py
Config Tester 单元测试
"""
import pytest
from app.sources.tester import config_tester, TestResult


class TestConfigTester:
    """配置测试器测试"""

    def test_test_result_to_dict(self):
        """TestResult 序列化"""
        result = TestResult(
            success=True,
            transport_success=True,
            parse_success=True,
            semantic_success=True,
            http_status=200,
            items_found=10,
            field_coverage=0.95,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["http_status"] == 200
        assert d["items_found"] == 10

    def test_test_result_empty(self):
        """空 TestResult"""
        result = TestResult()
        d = result.to_dict()
        assert d["success"] is False
        assert d["errors"] == []
