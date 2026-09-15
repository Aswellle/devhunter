"""
app/recommendation/candidates.py
Candidate Generation：多阶段候选生成。

候选来源：
A. Topic match - 用户主题匹配
B. User affinity - 用户亲缘度
C. Recently popular - 最近热门
D. Freshest - 最新内容
E. Thread updates - Thread 更新
F. Previously engaged topics - 之前互动的主题
G. Explicitly starred topics - 明确收藏的主题
H. Exploration candidates - 探索候选
"""
import logging
from datetime import datetime, timezone
from typing import Any

from app.repositories.item_repo import item_repo
from app.repositories.thread_repo import thread_repo
from app.repositories.user_prefs_repo import user_topics_repo, user_affinity_repo

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CandidateGenerator:
    """候选生成器"""

    def generate(
        self,
        user_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        生成候选集。

        Args:
            user_id: 用户 ID（可选）
            limit: 候选数量上限

        Returns:
            候选 Item 列表（去重后）
        """
        candidates: dict[str, dict[str, Any]] = {}

        # A. Topic match - 用户主题匹配
        topic_candidates = self._get_topic_match_candidates(limit=200)
        for item in topic_candidates:
            candidates[item["id"]] = item

        # B. User affinity - 用户亲缘度
        affinity_candidates = self._get_affinity_candidates(limit=200)
        for item in affinity_candidates:
            candidates[item["id"]] = item

        # C. Recently popular - 最近热门
        popular_candidates = self._get_popular_candidates(limit=100)
        for item in popular_candidates:
            candidates[item["id"]] = item

        # D. Freshest - 最新内容
        fresh_candidates = self._get_fresh_candidates(limit=100)
        for item in fresh_candidates:
            candidates[item["id"]] = item

        # E. Thread updates - Thread 更新
        thread_candidates = self._get_thread_update_candidates(limit=100)
        for item in thread_candidates:
            candidates[item["id"]] = item

        # H. Exploration candidates - 探索候选
        exploration_candidates = self._get_exploration_candidates(limit=50)
        for item in exploration_candidates:
            candidates[item["id"]] = item

        result = list(candidates.values())
        logger.info("Generated %d candidates from %d sources", len(result), 8)
        return result[:limit]

    def _get_topic_match_candidates(self, limit: int = 200) -> list[dict[str, Any]]:
        """获取主题匹配的候选"""
        # 获取用户主题
        user_topics = user_topics_repo.get_all_topics_with_weights()
        if not user_topics:
            return []

        # 获取最近 items
        items, _ = item_repo.query(page=1, per_page=500)
        if not items:
            return []

        # 简单匹配：标题包含用户主题词
        topic_words = {t["topic"].lower() for t in user_topics}
        matched = []
        for item in items:
            title = item.get("title", "").lower()
            if any(word in title for word in topic_words):
                matched.append(item)

        return matched[:limit]

    def _get_affinity_candidates(self, limit: int = 200) -> list[dict[str, Any]]:
        """获取亲缘度候选"""
        # 获取高亲缘度任务
        task_affinities = user_affinity_repo.get_top_affinities(
            affinity_type="task", limit=20
        )
        if not task_affinities:
            return []

        # 获取这些任务的最近 items
        task_ids = [a["affinity_value"] for a in task_affinities]
        items, _ = item_repo.query(page=1, per_page=500)
        matched = [item for item in items if item.get("task_id") in task_ids]
        return matched[:limit]

    def _get_popular_candidates(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取最近热门候选"""
        # 简化：按 fetched_at 倒序
        items, _ = item_repo.query(page=1, per_page=limit)
        return items

    def _get_fresh_candidates(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取最新候选"""
        items, _ = item_repo.query(page=1, per_page=limit)
        return items

    def _get_thread_update_candidates(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取 Thread 更新候选"""
        # 获取最近更新的 threads
        threads, _ = thread_repo.list_all(page=1, per_page=20)
        if not threads:
            return []

        # 获取这些 threads 的 items
        items = []
        for thread in threads[:10]:
            thread_items = thread_repo.get_items_in_thread(thread["id"])
            items.extend(thread_items)

        return items[:limit]

    def _get_exploration_candidates(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取探索候选（随机采样）"""
        import random
        items, _ = item_repo.query(page=1, per_page=500)
        if not items:
            return []
        # 随机采样
        sample_size = min(limit, len(items))
        return random.sample(items, sample_size)


# 全局单例
candidate_generator = CandidateGenerator()
