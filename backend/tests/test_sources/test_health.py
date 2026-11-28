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


# ── 真实指标回归：字段覆盖率/统计窗口/低样本置信度 ────────────────

import hashlib
import uuid as _uuid
from datetime import datetime, timedelta, timezone

from app.repositories.execution_repo import execution_repo
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo


def _seed_health_task(items, executions):
    """构造任务 + 条目 + 执行记录。items: (title, url, hours_ago)；
    executions: (status, fetched, new, hours_ago)。返回 task_id。"""
    task = task_repo.insert({
        "name": f"健康度测试 {_uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })
    task_id = task["id"]
    for i, (title, url, hours_ago) in enumerate(items):
        ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        item_repo.bulk_insert([{
            "id": str(_uuid.uuid4()),
            "task_id": task_id,
            "title": title,
            "url": url,
            "url_hash": hashlib.sha256(f"{task_id}-{i}".encode()).hexdigest(),
            "summary": "",
            "fetched_at": ts,
        }])
    for status, fetched, new, hours_ago in executions:
        ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        execution_repo.insert({
            "task_id": task_id,
            "status": status,
            "items_fetched": fetched,
            "items_new": new,
            "executed_at": ts,
        })
    return task_id


class TestHealthRealMetrics:
    def test_field_coverage_reflects_empty_fields_not_new_ratio(self):
        """field coverage 必须按字段非空率计算：10 条里 1 条空标题 → 95%，
        与重复率（90%）是两个独立指标——旧实现用 items_new/items_fetched
        冒充覆盖率，两项指标完全同源重复计分。"""
        items = [(f"标题 {i}", f"https://example.com/{i}", 1) for i in range(9)]
        items.append(("", "https://example.com/empty-title", 1))
        task_id = _seed_health_task(
            items,
            [("success", 100, 10, 1)],  # 重复率 90%
        )

        result = health_calculator.calculate(task_id)

        assert result["field_coverage"] == pytest.approx(95.0)
        assert result["field_breakdown"]["title"] == pytest.approx(90.0)
        assert result["field_breakdown"]["url"] == pytest.approx(100.0)
        assert result["duplicate_rate"] == pytest.approx(90.0)
        # 两个指标必须解耦：不再互为补数
        assert result["field_coverage"] != pytest.approx(
            100.0 - result["duplicate_rate"])

    def test_24h_window_excludes_old_executions(self):
        """统计窗口与文案一致（24h）：3 天前的执行不得混入——旧实现读
        最近 50 次，注释写 24h，两处矛盾。"""
        task_id = _seed_health_task(
            [("t", "https://example.com/1", 1)],
            [("success", 10, 5, 2), ("success", 1000, 0, 72)],
        )

        result = health_calculator.calculate(task_id)

        assert result["window"] == "24h"
        assert result["total_executions"] == 1

    def test_fallback_window_is_marked_7d(self):
        """24h 内无执行时回退 7 天窗口，并明确标记 window=7d。"""
        task_id = _seed_health_task(
            [("t", "https://example.com/1", 72)],
            [("success", 10, 5, 72)],
        )

        result = health_calculator.calculate(task_id)

        assert result["window"] == "7d"
        assert result["total_executions"] == 1

    def test_no_executions_within_7d_is_unknown(self):
        """7 天内完全无执行 → unknown，不得用陈旧执行伪装健康。"""
        task_id = _seed_health_task([], [("success", 10, 5, 24 * 10)])

        result = health_calculator.calculate(task_id)

        assert result["status"] == "unknown"
        assert result["total_executions"] == 0

    def test_low_sample_marks_low_confidence(self):
        """样本不足（< 10 条）时标记 low_confidence，防止单次成功
        就显示满分健康。"""
        task_id = _seed_health_task(
            [(f"t{i}", f"https://example.com/{i}", 1) for i in range(3)],
            [("success", 3, 3, 1)],
        )
        result = health_calculator.calculate(task_id)
        assert result["low_confidence"] is True

        task_id2 = _seed_health_task(
            [(f"t{i}", f"https://example.com/x{i}", 1) for i in range(12)],
            [("success", 12, 12, 1)],
        )
        result2 = health_calculator.calculate(task_id2)
        assert result2["low_confidence"] is False
