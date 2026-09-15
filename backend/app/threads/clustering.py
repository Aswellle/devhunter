"""
app/threads/clustering.py
Thread Clustering：基于多因素评分的 Thread 聚类。

使用 ThreadScorer 计算新 Item 与候选 Thread 的匹配分数，
并根据置信度决定：
- HIGH: 直接加入
- MEDIUM: 加入但标记为待确认
- LOW: 创建新 Thread
"""
import logging
from typing import Any

from app.features.extractor import feature_extractor
from app.threads.scoring import thread_scorer, ThreadScore

logger = logging.getLogger(__name__)


class ThreadClusteringResult:
    """聚类结果"""
    def __init__(
        self,
        action: str,  # "join" | "create"
        thread_id: str | None = None,
        score: ThreadScore | None = None,
    ):
        self.action = action
        self.thread_id = thread_id
        self.score = score

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "thread_id": self.thread_id,
            "score": self.score.to_dict() if self.score else None,
        }


class ThreadClusterer:
    """Thread 聚类器"""

    # 加入阈值
    JOIN_THRESHOLD = 0.45

    def cluster(
        self,
        new_item: dict[str, Any],
        candidate_threads: list[dict[str, Any]],
    ) -> ThreadClusteringResult:
        """
        为新 Item 找到最佳匹配的 Thread。

        Args:
            new_item: 新 Item dict
            candidate_threads: 候选 Thread 列表

        Returns:
            ThreadClusteringResult
        """
        if not candidate_threads:
            return ThreadClusteringResult(action="create")

        # 提取新 Item 特征
        new_features = feature_extractor.extract(new_item)

        best_score: ThreadScore | None = None
        best_thread: dict[str, Any] | None = None

        for thread in candidate_threads:
            # 提取 Thread 特征（从 Thread 的 title 和 items）
            thread_features = self._extract_thread_features(thread)

            score = thread_scorer.score(
                new_item=new_item,
                candidate_thread=thread,
                new_features=new_features.to_dict(),
                candidate_features=thread_features,
            )

            if best_score is None or score.total_score > best_score.total_score:
                best_score = score
                best_thread = thread

        if best_score and best_score.total_score >= self.JOIN_THRESHOLD and best_thread:
            return ThreadClusteringResult(
                action="join",
                thread_id=best_thread.get("id"),
                score=best_score,
            )

        return ThreadClusteringResult(action="create")

    def _extract_thread_features(self, thread: dict[str, Any]) -> dict[str, Any]:
        """从 Thread 中提取特征"""
        title = thread.get("title", "")
        # 简化：只从 title 提取特征
        features = feature_extractor.extract({"title": title, "summary": ""})
        return features.to_dict()


# 全局单例
thread_clusterer = ThreadClusterer()
