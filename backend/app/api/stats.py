"""
app/api/stats.py
系统概览统计端点：GET /api/stats
用于仪表盘展示总条目数、每日趋势、成功率等。
"""
from fastapi import APIRouter, Depends

from app.api.deps import require_auth
from app.core.database import get_db

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
def get_stats(_: str = Depends(require_auth)):
    """
    返回系统概览统计数据：
    - 总条目数、今日采集数
    - 任务状态分布
    - 7 日每日采集量趋势
    - 7 日执行成功率
    """
    with get_db() as conn:

        # ── 总条目数 ─────────────────────────────────────
        total_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

        # ── 今日采集 ─────────────────────────────────────
        items_today = conn.execute(
            "SELECT COUNT(*) FROM items WHERE date(fetched_at) = date('now')"
        ).fetchone()[0]

        # ── 任务状态分布 ──────────────────────────────────
        task_rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM tasks WHERE deleted_at IS NULL GROUP BY status"
        ).fetchall()
        tasks_by_status = {r["status"]: r["c"] for r in task_rows}

        # ── 今日执行次数 ──────────────────────────────────
        executions_today = conn.execute(
            "SELECT COUNT(*) FROM task_executions WHERE date(executed_at) = date('now')"
        ).fetchone()[0]

        # ── 7 日执行成功率 ────────────────────────────────
        exec_stats = conn.execute("""
            SELECT
                COUNT(*)  AS total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successes,
                SUM(CASE WHEN status = 'failure' THEN 1 ELSE 0 END) AS failures
            FROM task_executions
            WHERE executed_at >= datetime('now', '-7 days')
        """).fetchone()
        total_execs   = exec_stats["total"]    or 0
        successes     = exec_stats["successes"] or 0
        failures      = exec_stats["failures"]  or 0
        success_rate  = round(successes / total_execs, 3) if total_execs > 0 else None

        # ── 7 日每日采集量 ────────────────────────────────
        daily_rows = conn.execute("""
            SELECT date(fetched_at) AS day, COUNT(*) AS count
            FROM items
            WHERE fetched_at >= datetime('now', '-7 days')
            GROUP BY date(fetched_at)
            ORDER BY day ASC
        """).fetchall()
        daily_items = [{"date": r["day"], "count": r["count"]} for r in daily_rows]

        # ── 最近活跃任务 Top 5（按采集量） ────────────────
        top_tasks = conn.execute("""
            SELECT t.name, COUNT(i.id) AS item_count
            FROM tasks t
            LEFT JOIN items i ON i.task_id = t.id
                AND i.fetched_at >= datetime('now', '-7 days')
            WHERE t.deleted_at IS NULL
            GROUP BY t.id
            ORDER BY item_count DESC
            LIMIT 5
        """).fetchall()

    return {
        "total_items":      total_items,
        "items_today":      items_today,
        "executions_today": executions_today,
        "tasks": {
            "active":  tasks_by_status.get("active",  0),
            "paused":  tasks_by_status.get("paused",  0),
            "error":   tasks_by_status.get("error",   0),
            "total":   sum(tasks_by_status.values()),
        },
        "success_rate_7d": success_rate,
        "total_executions_7d": total_execs,
        "failures_7d":    failures,
        "daily_items":    daily_items,
        "top_tasks_7d": [
            {"name": r["name"], "item_count": r["item_count"]}
            for r in top_tasks
        ],
    }
