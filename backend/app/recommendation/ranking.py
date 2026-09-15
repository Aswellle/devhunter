"""
app/recommendation/ranking.py
Learning-to-Rank：基于特征的排序模型。

当前实现：线性加权排序（可替换为 ML 模型）
未来可扩展：梯度提升树、神经网络等

特征：
- preference_score: 用户偏好匹配
- affinity_score: 亲缘度
- recency_score: 新鲜度
- engagement_score: 参与度
- thread_importance_score: Thread 重要性
- exploration_score: 探索得分
"""
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RankFeatures:
    """排序特征"""
    preference_score: float = 0.0
    affinity_score: float = 0.0
    recency_score: float = 0.0
    engagement_score: float = 0.0
    thread_importance_score: float = 0.0
    exploration_score: float = 0.0

    def to_list(self) -> list[float]:
        """转换为特征向量"""
        return [
            self.preference_score,
            self.affinity_score,
            self.recency_score,
            self.engagement_score,
            self.thread_importance_score,
            self.exploration_score,
        ]


class LinearRanker:
    """
    线性加权排序器。

    使用固定权重对特征进行线性加权，作为 learning-to-rank 的 baseline。
    未来可替换为训练好的 ML 模型。
    """

    # 默认权重（可通过训练优化）
    DEFAULT_WEIGHTS = [0.35, 0.20, 0.15, 0.10, 0.10, 0.10]

    def __init__(self, weights: list[float] | None = None):
        """
        Args:
            weights: 特征权重列表，None 使用默认权重
        """
        self.weights = weights or self.DEFAULT_WEIGHTS

    def rank(self, features: RankFeatures) -> float:
        """
        计算排序分数。

        Args:
            features: 排序特征

        Returns:
            排序分数
        """
        feature_vec = features.to_list()
        score = sum(w * f for w, f in zip(self.weights, feature_vec))
        return min(1.0, max(0.0, score))

    def batch_rank(self, features_list: list[RankFeatures]) -> list[float]:
        """批量计算排序分数"""
        return [self.rank(f) for f in features_list]


class FeatureExtractor:
    """
    特征提取器。

    从 Item 和用户画像中提取排序特征。
    """

    def extract(
        self,
        item: dict[str, Any],
        user_profile: dict[str, Any],
        thread_info: dict[str, Any] | None = None,
    ) -> RankFeatures:
        """
        提取排序特征。

        Args:
            item: Item dict
            user_profile: 用户画像
            thread_info: Thread 信息（可选）

        Returns:
            RankFeatures
        """
        features = RankFeatures()

        # 1. Preference score
        features.preference_score = self._calc_preference_score(
            item, user_profile.get("topics", {})
        )

        # 2. Affinity score
        features.affinity_score = self._calc_affinity_score(
            item, user_profile.get("affinities", {})
        )

        # 3. Recency score
        features.recency_score = self._calc_recency_score(
            item.get("published_at") or item.get("fetched_at", "")
        )

        # 4. Engagement score
        features.engagement_score = user_profile.get("engagement_stats", {}).get(
            item.get("id", ""), {}
        ).get("score", 0.0)

        # 5. Thread importance score
        if thread_info:
            features.thread_importance_score = self._calc_thread_importance(thread_info)

        # 6. Exploration score
        features.exploration_score = self._calc_exploration_score(item, user_profile)

        return features

    def _calc_preference_score(
        self, item: dict[str, Any], user_topics: dict[str, float]
    ) -> float:
        """计算偏好匹配得分"""
        if not user_topics:
            return 0.0

        title = item.get("title", "").lower()
        summary = item.get("summary", "").lower()
        text = title + " " + summary

        matched_weight = 0.0
        total_weight = sum(user_topics.values())

        if total_weight == 0:
            return 0.0

        for topic, weight in user_topics.items():
            if topic.lower() in text:
                matched_weight += weight

        return matched_weight / total_weight

    def _calc_affinity_score(
        self, item: dict[str, Any], affinities: dict[str, float]
    ) -> float:
        """计算亲缘度得分"""
        if not affinities:
            return 0.0

        task_id = item.get("task_id", "")
        task_name = item.get("task_name", "") or ""

        score = 0.0
        if task_id and task_id in affinities:
            score += affinities[task_id] * 0.6
        if task_name and task_name in affinities:
            score += affinities[task_name] * 0.4

        return min(1.0, score)

    def _calc_recency_score(self, date_str: str) -> float:
        """计算新鲜度得分"""
        if not date_str:
            return 0.0
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            if hours <= 24:
                return 1.0
            import math
            return max(0.0, math.pow(0.5, (hours - 24) / 6))
        except Exception:
            return 0.0

    def _calc_thread_importance(self, thread_info: dict[str, Any]) -> float:
        """计算 Thread 重要性得分"""
        source_count = thread_info.get("source_count", 1)
        last_seen = thread_info.get("last_seen_at", "")

        source_score = min(1.0, source_count / 5)

        recency = self._calc_recency_score(last_seen)
        return (source_score + recency) / 2

    def _calc_exploration_score(
        self, item: dict[str, Any], user_profile: dict[str, Any]
    ) -> float:
        """计算探索得分"""
        task_id = item.get("task_id", "")
        interacted_tasks = user_profile.get("interacted_tasks", set())

        if task_id and task_id not in interacted_tasks:
            return 0.8

        return 0.2


# 全局单例
linear_ranker = LinearRanker()
feature_extractor = FeatureExtractor()
