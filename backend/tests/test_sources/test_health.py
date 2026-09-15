"""
tests/test_sources/test_health.py
Source Health 单元测试
"""
import pytest
from app.sources.health import health_calculator


class TestSourceHealthCalculator:
    """Source Health 计算测试"""

    def test_calculate_no_executions(self):
        """无执行记录时返回 unknown"""
        result = health_calculator.calculate("nonexistent_task")
        assert result["health_score"] == 0
        assert result["status"] == "unknown"
        assert result["total_executions"] == 0

    def test_calc_freshness_recent(self):
        """最近执行 → 新鲜度高"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        score = health_calculator._calc_freshness(now)
        assert score == 100.0

    def test_calc_freshness_old(self):
        """很久未执行 → 新鲜度低"""
        score = health_calculator._calc_freshness("2020-01-01T00:00:00Z")
        assert score < 50.0

    def test_calc_freshness_none(self):
        """无执行时间 → 0"""
        score = health_calculator._calc_freshness(None)
        assert score == 0.0

    def test_calc_duplicate_rate(self):
        """重复率计算"""
        executions = [
            {"items_fetched": 100, "items_new": 80},
            {"items_fetched": 100, "items_new": 70},
        ]
        rate = health_calculator._calc_duplicate_rate(executions)
        assert 0 <= rate <= 100
