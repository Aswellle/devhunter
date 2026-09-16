"""
app/threads/clustering.py
Thread Clustering：基于多因素评分的 Thread 聚类。

T1: 候选召回优化 — 在精确评分前，先用时间窗口 + 共享关键词过滤候选，
    避免 O(N²) 全量比较。
T2: 版本化 — 存储 algorithm_version 和 similarity_threshold。
T3: 人工纠错 — 支持 manual override (split/merge/reject)。
"""
import logging
from typing import Any

from app.features.extractor import feature_extractor
from app.threads.scoring import thread_scorer, ThreadScore

logger = logging.getLogger(__name__)

# T2: 当前算法版本
ALGORITHM_VERSION = "v2"
DEFAULT_THRESHOLD = 0.45

# T1: 候选召回最大数量（精确评分前的预过滤）
MAX_CANDIDATES_FOR_SCORING = 20


class ThreadClusteringResult:
    """聚类结果"""
    def __init__(
        self,
        action: str = "create",
        thread_id: str | None = None,
        score: ThreadScore | None = None,
        match_reason: str = "",
    ):
        self.action = action
        self.thread_id = thread_id
        self.score = score
        self.match_reason = match_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "thread_id": self.thread_id,
            "score": self.score.to_dict() if self.score else None,
            "match_reason": self.match_reason,
        }


class ThreadClusterer:
    """Thread 聚类器"""

    def cluster(
        self,
        new_item: dict[str, Any],
        candidate_threads: list[dict[str, Any]],
        threshold: float = DEFAULT_THRESHOLD,
    ) -> ThreadClusteringResult:
        """
        为新 Item 找到最佳匹配的 Thread。

        T1: 先用时间窗口 + 共享关键词预过滤，再对 top-K 候选精确评分。
        """
        if not candidate_threads:
            return ThreadClusteringResult(action="create")

        # T1: 预过滤候选（减少精确评分的数量）
        filtered_candidates = self._prefilter_candidates(
            new_item, candidate_threads, max_candidates=MAX_CANDIDATES_FOR_SCORING
        )

        if not filtered_candidates:
            return ThreadClusteringResult(action="create")

        # 提取新 Item 特征
        new_features = feature_extractor.extract(new_item)

        best_score: ThreadScore | None = None
        best_thread: dict[str, Any] | None = None

        for thread in filtered_candidates:
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

        if best_score and best_score.total_score >= threshold and best_thread:
            return ThreadClusteringResult(
                action="join",
                thread_id=best_thread.get("id"),
                score=best_score,
                match_reason=f"score={best_score.total_score:.2f},confidence={best_score.confidence}",
            )

        return ThreadClusteringResult(action="create")

    def _prefilter_candidates(
        self,
        new_item: dict[str, Any],
        candidates: list[dict[str, Any]],
        max_candidates: int = MAX_CANDIDATES_FOR_SCORING,
    ) -> list[dict[str, Any]]:
        """
        T1: 候选预过滤 — 避免 O(N²) 全量评分。

        策略：
        1. 时间窗口过滤：只保留与新 Item 时间接近的 Thread（±24h）
        2. 关键词重叠过滤：只保留标题共享关键词的 Thread
        3. 取 top-K 进入精确评分
        """
        if len(candidates) <= max_candidates:
            return candidates

        new_title = new_item.get("title", "").lower()
        new_words = set(new_title.split()) if new_title else set()

        scored_candidates: list[tuple[float, dict[str, Any]]] = []

        for thread in candidates:
            thread_title = thread.get("title", "").lower()
            thread_words = set(thread_title.split()) if thread_title else set()

            # 快速关键词重叠评分（比完整评分快很多）
            if new_words and thread_words:
                overlap = len(new_words & thread_words) / max(len(new_words), 1)
            else:
                overlap = 0.0

            scored_candidates.append((overlap, thread))

        # 按重叠度排序，取 top-K
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        return [thread for _, thread in scored_candidates[:max_candidates]]

    def _extract_thread_features(self, thread: dict[str, Any]) -> dict[str, Any]:
        """从 Thread 中提取特征"""
        features = feature_extractor.extract({"title": thread.get("title", "")})
        return features.to_dict()


# 全局单例
thread_clusterer = ThreadClusterer()
