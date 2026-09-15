"""
app/recommendation/diversification.py
Diversification：推荐结果多样性处理。

限制：
- max_per_thread: 每个 Thread 最多推荐 N 条
- max_per_source: 每个来源最多推荐 N 条
- max_per_topic: 每个主题最多推荐 N 条
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class Diversifier:
    """多样性处理器"""

    def __init__(
        self,
        max_per_thread: int = 1,
        max_per_source: int = 4,
        max_per_topic: int = 6,
    ):
        self.max_per_thread = max_per_thread
        self.max_per_source = max_per_source
        self.max_per_topic = max_per_topic

    def apply(
        self,
        scored_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        应用多样性限制。

        Args:
            scored_items: 已评分的 Item 列表（按分数降序）

        Returns:
            多样性处理后的 Item 列表
        """
        thread_counts: dict[str, int] = {}
        source_counts: dict[str, int] = {}
        topic_counts: dict[str, int] = {}

        result = []
        for item in scored_items:
            thread_id = item.get("thread_id", "")
            source_id = item.get("source_id", "") or item.get("task_id", "")
            topic = self._extract_topic(item)

            # 检查限制
            if thread_id and thread_counts.get(thread_id, 0) >= self.max_per_thread:
                continue
            if source_counts.get(source_id, 0) >= self.max_per_source:
                continue
            if topic and topic_counts.get(topic, 0) >= self.max_per_topic:
                continue

            # 通过限制
            result.append(item)
            if thread_id:
                thread_counts[thread_id] = thread_counts.get(thread_id, 0) + 1
            source_counts[source_id] = source_counts.get(source_id, 0) + 1
            if topic:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

        logger.debug(
            "Diversification: %d -> %d items (thread=%d, source=%d, topic=%d)",
            len(scored_items), len(result),
            self.max_per_thread, self.max_per_source, self.max_per_topic,
        )
        return result

    def _extract_topic(self, item: dict[str, Any]) -> str:
        """从 Item 中提取主题"""
        # 简化：使用 task_name 或 title 的第一个词
        task_name = item.get("task_name", "")
        if task_name:
            return task_name.lower()
        title = item.get("title", "")
        if title:
            return title.split()[0].lower() if title.split() else ""
        return ""


# 全局单例
diversifier = Diversifier()
