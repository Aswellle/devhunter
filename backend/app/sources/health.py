"""
app/sources/health.py
Source Health：数据源健康度计算。

健康评分维度：
- HTTP availability (30%)
- Parse success rate (30%)
- Required field coverage (20%)
- Item freshness (10%)
- Duplicate rate (10%)
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.database import get_db
from app.repositories.execution_repo import execution_repo

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hours_since(iso_date: str) -> float:
    """计算距离 ISO 日期的小时数"""
    if not iso_date:
        return 999.0
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except (ValueError, TypeError):
        return 999.0


class SourceHealthCalculator:
    """数据源健康度计算器"""

    # 统计窗口：主窗口 24h（与文案一致）；窗口内无执行时回退 7 天并标记
    _WINDOW_HOURS = 24
    _FALLBACK_WINDOW_HOURS = 24 * 7
    # 条目样本量低于该值时标记 low_confidence——单次成功不该显示满分健康
    _LOW_CONFIDENCE_SAMPLE = 10

    def _recent_executions(self, task_id: str, window_hours: int) -> list[dict]:
        """窗口内的执行记录（executed_at 字符串 ISO 序可直接比较）。"""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        executions, _ = execution_repo.list_by_task(task_id, per_page=200)
        return [
            e for e in executions
            if (e.get("executed_at") or "") >= cutoff
        ]

    def calculate(self, task_id: str) -> dict[str, Any]:
        """
        计算指定任务（数据源）的健康评分。
        返回 health_score (0-100) 和详细指标。

        field coverage 按 items 表 title/url 非空率计算，与 duplicate rate
        （items_new/items_fetched）解耦——旧实现用 new/fetched 冒充覆盖率，
        两个指标完全同源，加权等于重复计分。
        """
        window_hours = self._WINDOW_HOURS
        executions = self._recent_executions(task_id, window_hours)
        window = "24h"
        if not executions:
            window_hours = self._FALLBACK_WINDOW_HOURS
            executions = self._recent_executions(task_id, window_hours)
            window = "7d"
        if not executions:
            return {
                "health_score": 0,
                "status": "unknown",
                "http_availability": 0,
                "parse_success_rate": 0,
                "field_coverage": 0,
                "freshness": 0,
                "duplicate_rate": 0,
                "total_executions": 0,
                "last_executed_at": None,
                "window": window,
                "sample_size": 0,
                "low_confidence": True,
                "field_breakdown": {"title": 0.0, "url": 0.0},
            }

        total = len(executions)
        http_success = sum(1 for e in executions if e.get("status") != "failure")
        parse_success = sum(
            1 for e in executions
            if e.get("status") in ("success", "warning")
        )

        # 真实字段覆盖率：窗口内条目 title/url 非空率
        field_coverage, breakdown, sample_size = self._calc_field_coverage(
            task_id, window_hours
        )

        # 新鲜度：最近执行时间
        latest = executions[0] if executions else {}
        last_executed = latest.get("executed_at")
        freshness = self._calc_freshness(last_executed)

        # 重复率（与 field coverage 同窗口但不同源）
        duplicate_rate = self._calc_duplicate_rate(executions)

        # 加权计算
        http_score = (http_success / total) * 100 if total else 0
        parse_score = (parse_success / total) * 100 if total else 0

        health_score = (
            0.30 * http_score
            + 0.30 * parse_score
            + 0.20 * field_coverage
            + 0.10 * freshness
            + 0.10 * (100 - duplicate_rate)  # 重复率越低越好
        )

        # 状态判定
        if health_score >= 80:
            status = "healthy"
        elif health_score >= 50:
            status = "degraded"
        else:
            status = "broken"

        return {
            "health_score": round(health_score, 1),
            "status": status,
            "http_availability": round(http_score, 1),
            "parse_success_rate": round(parse_score, 1),
            "field_coverage": round(field_coverage, 1),
            "freshness": round(freshness, 1),
            "duplicate_rate": round(duplicate_rate, 1),
            "total_executions": total,
            "last_executed_at": last_executed,
            "window": window,
            "sample_size": sample_size,
            "low_confidence": sample_size < self._LOW_CONFIDENCE_SAMPLE,
            "field_breakdown": breakdown,
        }

    def _calc_field_coverage(
        self, task_id: str, window_hours: int
    ) -> tuple[float, dict[str, float], int]:
        """窗口内条目的 title/url 非空率。

        返回 (覆盖率百分比, 分字段百分比, 条目样本数)；样本为空返回 0。"""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        with get_db() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS total,
                          SUM(CASE WHEN TRIM(COALESCE(title, '')) != ''
                                   THEN 1 ELSE 0 END) AS title_ok,
                          SUM(CASE WHEN TRIM(COALESCE(url, '')) != ''
                                   THEN 1 ELSE 0 END) AS url_ok
                   FROM items
                   WHERE task_id = ? AND COALESCE(fetched_at, created_at) >= ?""",
                (task_id, cutoff)
            ).fetchone()
        total = (row["total"] or 0) if row else 0
        if not total:
            return 0.0, {"title": 0.0, "url": 0.0}, 0
        title_pct = (row["title_ok"] or 0) / total * 100
        url_pct = (row["url_ok"] or 0) / total * 100
        coverage = (title_pct + url_pct) / 2
        return coverage, {"title": title_pct, "url": url_pct}, total

    def _calc_freshness(self, last_executed_at: str | None) -> float:
        """计算新鲜度分数"""
        if not last_executed_at:
            return 0.0
        hours = _hours_since(last_executed_at)
        if hours <= 1:
            return 100.0
        elif hours <= 6:
            return 90.0
        elif hours <= 24:
            return 70.0
        elif hours <= 72:
            return 40.0
        else:
            return 10.0

    def _calc_duplicate_rate(self, executions: list[dict]) -> float:
        """计算重复率"""
        if not executions:
            return 0.0
        total_fetched = sum(e.get("items_fetched", 0) for e in executions)
        total_new = sum(e.get("items_new", 0) for e in executions)
        if total_fetched == 0:
            return 0.0
        return ((total_fetched - total_new) / total_fetched) * 100


# 全局单例
health_calculator = SourceHealthCalculator()
