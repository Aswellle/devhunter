"""
app/scheduler/reddit_retention.py
Reddit 内容 TTL 清理（PROD-004 删除同步策略）。

按 Reddit Data API 条款，应支持内容删除/撤回后的清理。逐帖存在性轮询
成本高且易触发限流，采用 TTL 保留策略：Reddit 来源条目超过
REDDIT_ITEM_TTL_DAYS（默认 30 天）后删除；用户删除来源任务时既有
cleanup 语义会清空该来源全部条目。Thread 关联/统计与交互记录同步清理。
"""
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def purge_expired_reddit_items() -> int:
    """删除超期的 Reddit 条目及其 Thread 关联/交互记录，返回删除行数。

    只处理 selector_list 以 reddit: 开头的任务——不误删其他来源。
    """
    from datetime import datetime, timedelta, timezone

    from app.core.database import transaction
    from app.repositories.thread_repo import thread_repo

    ttl_days = int(settings.reddit_item_ttl_days or 30)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    with transaction() as conn:
        rows = conn.execute(
            """SELECT i.id, i.thread_id FROM items i
               JOIN tasks t ON i.task_id = t.id
               WHERE t.selector_list LIKE 'reddit:%'
                 AND COALESCE(i.published_at, i.fetched_at) < ?""",
            (cutoff,),
        ).fetchall()
        if not rows:
            return 0
        item_ids = [r["id"] for r in rows]
        thread_ids = {r["thread_id"] for r in rows if r["thread_id"]}
        placeholders = ",".join(["?"] * len(item_ids))
        # 先摘除 membership（复用仓储的悬空引用清理），再删条目与交互，
        # 最后重算受影响 Thread 统计（空 Thread 连带回收）
        for item_id in item_ids:
            thread_repo.delete_item_from_thread(item_id, conn=conn)
        conn.execute(
            f"DELETE FROM user_interactions WHERE item_id IN ({placeholders})",
            item_ids,
        )
        conn.execute(f"DELETE FROM items WHERE id IN ({placeholders})", item_ids)
        for thread_id in thread_ids:
            thread_repo.rebuild_thread_stats(thread_id, conn=conn)
        return len(item_ids)


def reddit_retention_job() -> None:
    """调度入口：每日清理超期 Reddit 条目。"""
    try:
        deleted = purge_expired_reddit_items()
        if deleted:
            logger.info(
                "Reddit retention: purged %d item(s) older than %d days",
                deleted, int(settings.reddit_item_ttl_days or 30),
            )
    except Exception as e:  # noqa: BLE001 — 系统任务自己兜底
        logger.error("Reddit retention job failed: %s", e)
