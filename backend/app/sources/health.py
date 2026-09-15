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
from datetime import datetime, timezone
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

    def calculate(self, task_id: str) -> dict[str, Any]:
        """
        计算指定任务（数据源）的健康评分。
        返回 health_score (0-100) 和详细指标。
        """
        # 获取最近 24h 的执行记录
        executions, _ = execution_repo.list_by_task(task_id, per_page=50)
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
            }

        total = len(executions)
        http_success = sum(1 for e in executions if e.get("status") != "failure")
        parse_success = sum(
            1 for e in executions
            if e.get("status") in ("success", "warning")
        )

        # 计算字段覆盖率（从最近一次成功执行）
        field_coverage = self._calc_field_coverage(task_id)

        # 新鲜度：最近执行时间
        latest = executions[0] if executions else {}
        last_executed = latest.get("executed_at")
        freshness = self._calc_freshness(last_executed)

        # 重复率
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
        }

    def _calc_field_coverage(self, task_id: str) -> float:
        """计算最近一次成功执行的字段覆盖率"""
        with get_db() as conn:
            row = conn.execute(
                """SELECT items_fetched, items_new FROM task_executions
                   WHERE task_id = ? AND status IN ('success', 'warning')
                   ORDER BY executed_at DESC LIMIT 1""",
                (task_id,)
            ).fetchone()
            if not row:
                return 0.0
            fetched = row["items_fetched"] or 0
            new = row["items_new"] or 0
            if fetched == 0:
                return 0.0
            # 用 items_new / items_fetched 作为字段覆盖的代理指标
            return min(100.0, (new / fetched) * 100)

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
