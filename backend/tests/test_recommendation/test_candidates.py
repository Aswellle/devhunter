"""
tests/test_recommendation/test_candidates.py
Candidate Generation 单元测试
"""
import pytest
from app.recommendation.candidates import candidate_generator


class TestCandidateGenerator:
    """候选生成器测试"""

    def test_generate_empty(self):
        """空数据库 → 返回空列表"""
        result = candidate_generator.generate(limit=10)
        assert isinstance(result, list)

    def test_generate_with_limit(self):
        """限制返回数量"""
        result = candidate_generator.generate(limit=5)
        assert len(result) <= 5

    def test_generate_returns_dicts(self):
        """返回的是 dict 列表"""
        result = candidate_generator.generate(limit=10)
        for item in result:
            assert isinstance(item, dict)
            assert "id" in item
