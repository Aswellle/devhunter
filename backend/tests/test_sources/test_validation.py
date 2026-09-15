"""
tests/test_sources/test_validation.py
Semantic Validation 单元测试
"""
import pytest
from app.sources.validation import SemanticValidator, ValidationResult


class TestSemanticValidator:
    """语义验证测试"""

    def test_transport_success(self):
        """HTTP 200 → transport_success"""
        validator = SemanticValidator(expected_min_items=1, required_fields=["title"])
        result = validator.validate(200, [{"title": "Test", "link": "http://example.com"}])
        assert result.transport_success is True
        assert result.parse_success is True
        assert result.semantic_success is True
        assert result.is_valid is True

    def test_transport_failure(self):
        """HTTP 500 → transport_failed"""
        validator = SemanticValidator()
        result = validator.validate(500, [])
        assert result.transport_success is False
        assert result.status == "transport_failed"

    def test_parse_failure(self):
        """HTTP 200 但无条目 → parse_failed"""
        validator = SemanticValidator()
        result = validator.validate(200, [])
        assert result.transport_success is True
        assert result.parse_success is False
        assert result.status == "parse_failed"

    def test_semantic_failure_low_coverage(self):
        """字段覆盖率低 → semantic_failed"""
        validator = SemanticValidator(
            expected_min_items=5,
            required_fields=["title", "link"],
            min_field_coverage=0.9,
        )
        # 只有 2 条，且缺少 link
        items = [{"title": "A"}, {"title": "B"}]
        result = validator.validate(200, items)
        assert result.transport_success is True
        assert result.parse_success is True
        assert result.semantic_success is False

    def test_field_coverage_calculation(self):
        """字段覆盖率计算"""
        validator = SemanticValidator(required_fields=["title", "link"])
        items = [
            {"title": "A", "link": "http://a.com"},
            {"title": "B", "link": "http://b.com"},
            {"title": "C"},  # 缺少 link
        ]
        coverage = validator._calc_field_coverage(items)
        assert coverage == pytest.approx(5 / 6, rel=0.01)

    def test_validation_result_to_dict(self):
        """验证结果序列化"""
        result = ValidationResult(
            transport_success=True,
            parse_success=True,
            semantic_success=True,
            items_found=10,
            field_coverage=0.95,
        )
        d = result.to_dict()
        assert d["status"] == "valid"
        assert d["items_found"] == 10
