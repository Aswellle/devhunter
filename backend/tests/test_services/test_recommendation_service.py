"""
tests/test_services/test_recommendation_service.py
Recommendation Service 单元测试
"""
import pytest
from app.services.recommendation_service import recommendation_service


class TestRecommendationService:
    """Recommendation Service 测试"""

    def test_get_recommended_items_empty(self):
        """空数据库 → 返回空列表"""
        result = recommendation_service.get_recommended_items(limit=10)
        assert isinstance(result, list)

    def test_get_recommended_items_with_limit(self):
        """限制返回数量"""
        result = recommendation_service.get_recommended_items(limit=5)
        assert len(result) <= 5

    def test_get_recommended_items_default_limit(self):
        """默认限制"""
        result = recommendation_service.get_recommended_items()
        assert isinstance(result, list)
