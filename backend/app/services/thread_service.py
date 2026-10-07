"""
app/services/thread_service.py
Thread 业务层：计算新 Items 的 Thread 归属

V2: 使用多因素评分（lexical + entity + semantic + temporal + source）
"""
import logging
import threading
import time

from app.core.exceptions import ConflictError
from app.repositories.thread_repo import thread_repo
from app.repositories.task_repo import task_repo
from app.utils.similarity import DEFAULT_THRESHOLD, find_similar_titles, jaccard_similarity
from app.features.extractor import feature_extractor
from app.threads.clustering import thread_clusterer
from app.threads.merge import thread_merger
from app.threads.split import thread_splitter
from app.threads.stats import build_thread_stats

logger = logging.getLogger(__name__)

# Thread 重建批次大小：候选池随批次刷新，批次过大窗口内候选会过期
_RECOMPUTE_BATCH_SIZE = 200


class ThreadService:

    # 重建互斥锁：防止两次重建并发交错（SQLite 单写入者，交错会产生半重建状态）
    _recompute_lock = threading.Lock()

    def compute_threads_for_items(
        self,
        new_items: list[dict],
        threshold: float = DEFAULT_THRESHOLD,
        window_hours: int = 24,
    ) -> int:
        """
        为一批新采集的 Items 计算 Thread 归属。

        V2 流程：对每个新 Item，使用多因素评分在近期活跃 Thread 中找最佳匹配；
        匹配则加入，否则创建新 Thread。

        内容性质门控：条目型（content_kind=catalog）任务的条目是独立资源
        （开源项目、产品、视频），彼此无事件关联，聚类只会产生无意义的
        单条目 Thread —— 直接跳过，不建 Thread 也不入 Thread。

        候选 Thread 逐条目刷新：同批次中先前条目刚创建/加入的 Thread 也会
        出现在后续条目的候选里——同一条事件的多篇报道才能聚进同一个 Thread。

        返回实际参与聚类的 Item 数量。
        """
        if not new_items:
            return 0

        # 获取各 task_id -> (platform 名称, content_kind) 的映射
        tasks = {t["id"]: t for t in task_repo.list_active()}
        item_id_to_platform = {
            item["id"]: tasks.get(item.get("task_id"), {}).get("name", "unknown")
            for item in new_items
        }
        clusterable = [
            item for item in new_items
            if tasks.get(item.get("task_id"), {}).get("content_kind", "discussion") == "discussion"
        ]
        skipped = len(new_items) - len(clusterable)
        if skipped:
            logger.info(
                "Thread compute: skipped %d catalog-kind items (no clustering for catalog sources)",
                skipped,
            )

        if not clusterable:
            return 0

        # 处理每个新 Item
        matched_count = 0
        for item in clusterable:
            item_id = item["id"]
            title = item["title"]
            platform = item_id_to_platform.get(item_id, "unknown")

            # 每个条目都重新取候选（近期活跃 Thread），见 get_candidate_threads
            candidate_threads = thread_repo.get_candidate_threads(hours=window_hours)

            # 使用多因素聚类
            result = thread_clusterer.cluster(item, candidate_threads, threshold=threshold)

            if result.action == "join" and result.thread_id:
                # 加入已有 Thread
                matched_count += 1
                thread_repo.add_item(
                    thread_id=result.thread_id,
                    item_id=item_id,
                    similarity=result.score.total_score if result.score else 0.5,
                    title=title,
                    platform=platform,
                    match_reason=result.match_reason,
                )
            else:
                # 创建新 Thread
                thread_repo.create(title=title, item_id=item_id, platform=platform, algorithm_version="v2", similarity_threshold=threshold, match_reason="no_match")

        logger.info(
            "Thread compute: %d items clustered, %d matched to existing threads, %d created new, %d catalog-skipped",
            len(clusterable), matched_count, len(clusterable) - matched_count, skipped,
        )
        return len(clusterable)

    def merge_threads(
        self,
        source_thread_id: str,
        target_thread_id: str,
        reason: str = "",
    ) -> dict | None:
        """
        合并两个 Thread。

        Args:
            source_thread_id: 源 Thread ID（将被删除）
            target_thread_id: 目标 Thread ID
            reason: 合并原因

        Returns:
            合并后的 Thread dict
        """
        return thread_merger.merge(source_thread_id, target_thread_id, reason)

    def split_thread(
        self,
        thread_id: str,
        item_ids: list[str],
        new_thread_title: str | None = None,
    ) -> dict | None:
        """
        拆分 Thread。

        Args:
            thread_id: 源 Thread ID
            item_ids: 要移出的 item ID 列表
            new_thread_title: 新 Thread 标题

        Returns:
            新 Thread dict
        """
        return thread_splitter.split(thread_id, item_ids, new_thread_title)

    def list_threads(
        self,
        task_id: str | None = None,
        page: int = 1,
        per_page: int = 20,
        sort: str = "first_seen",
    ) -> tuple[list[dict], int]:
        """列出 Threads（sort: first_seen | hotness）"""
        return thread_repo.list_all(task_id=task_id, page=page, per_page=per_page, sort=sort)

    def get_thread(self, thread_id: str) -> dict | None:
        """获取 Thread 详情（包含 Items 与聚合画像 stats）"""
        thread = thread_repo.get(thread_id)
        if not thread:
            return None
        items = thread_repo.get_items_in_thread(thread_id)
        return {**thread, "items": items, "stats": build_thread_stats(thread, items)}

    def recompute_all_threads(self, window_hours: int = 24) -> dict:
        """
        重建全部 Thread：清空后按 created_at 时间正序重放所有条目的聚类。

        - 使用与采集管线完全相同的算法（compute_threads_for_items），仅候选
          活动窗口可调（window_hours，默认 24h 与采集路径一致）
        - 按批次重放，候选随批次刷新
        - thread_overrides 为人工纠错审计记录，保留不动（旧引用自然失效）

        同步执行、进程内互斥：已有重建进行中时抛 ConflictError。
        个人规模的条目量（数千级）应在秒级到分钟级内完成。

        Returns:
            {"items": 处理条目数, "threads": 重建后 Thread 数,
             "duration_ms": 耗时, "window_hours": 窗口}
        """
        if not self._recompute_lock.acquire(blocking=False):
            raise ConflictError("Thread 重建已在进行中，请稍后再试")
        try:
            from app.repositories.item_repo import item_repo

            started = time.monotonic()
            thread_repo.delete_all()
            items = item_repo.list_all_chronological()

            for i in range(0, len(items), _RECOMPUTE_BATCH_SIZE):
                self.compute_threads_for_items(
                    items[i:i + _RECOMPUTE_BATCH_SIZE],
                    window_hours=window_hours,
                )

            duration_ms = int((time.monotonic() - started) * 1000)
            result = {
                "items": len(items),
                "threads": thread_repo.count_all(),
                "duration_ms": duration_ms,
                "window_hours": window_hours,
            }
            logger.info(
                "Thread recompute done: %d items -> %d threads in %dms (window=%dh)",
                result["items"], result["threads"], result["duration_ms"], window_hours,
            )
            return result
        finally:
            self._recompute_lock.release()

# 全局单例
thread_service = ThreadService()
