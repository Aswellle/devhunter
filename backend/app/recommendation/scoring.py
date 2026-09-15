"""
app/recommendation/scoring.py
Recommendation Scoring：推荐评分。

评分公式：
final_score =
    0.35 * preference_score
  + 0.20 * affinity_score
  + 0.15 * recency_score
  + 0.10 * engagement_score
  + 0.10 * thread_importance_score
  + 0.10 * exploration_score

其中：
- preference_score: 用户偏好匹配
- affinity_score: 亲缘度
- recency_score: 新鲜度
- engagement_score: 参与度
- thread_importance_score: Thread 重要性
- exploration_score: 探索得分
"""
import logging
import math
from datetime import datetime, timezone
from typing import Any

from app.features.extractor import feature_extractor
from app.threads.scoring import thread_scorer

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


class RecommendationScorer:
    """推荐评分器"""

    # 权重配置
    WEIGHTS = {
        "preference": 0.35,
        "affinity": 0.20,
        "recency": 0.15,
        "engagement": 0.10,
        "thread_importance": 0.10,
        "exploration": 0.10,
    }

    def score(
        self,
        item: dict[str, Any],
        user_profile: dict[str, Any],
        thread_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        计算单条 Item 的推荐得分。

        Args:
            item: Item dict
            user_profile: 用户画像
            thread_info: Thread 信息（可选）

        Returns:
            包含各维度得分和总分的 dict
        """
        # 1. Preference score
        preference_score = self._calc_preference_score(
            item, user_profile.get("topics", {})
        )

        # 2. Affinity score
        affinity_score = self._calc_affinity_score(
            item, user_profile.get("affinities", {})
        )

        # 3. Recency score
        recency_score = self._calc_recency_score(
            item.get("published_at") or item.get("fetched_at", "")
        )

        # 4. Engagement score
        engagement_score = user_profile.get("engagement_stats", {}).get(
            item.get("id", ""), {}
        ).get("score", 0.0)

        # 5. Thread importance score
        thread_importance_score = 0.0
        if thread_info:
            thread_importance_score = self._calc_thread_importance(thread_info)

        # 6. Exploration score
        exploration_score = self._calc_exploration_score(item, user_profile)

        # 加权总分
        total_score = (
            self.WEIGHTS["preference"] * preference_score
            + self.WEIGHTS["affinity"] * affinity_score
            + self.WEIGHTS["recency"] * recency_score
            + self.WEIGHTS["engagement"] * engagement_score
            + self.WEIGHTS["thread_importance"] * thread_importance_score
            + self.WEIGHTS["exploration"] * exploration_score
        )

        return {
            "total_score": round(min(1.0, total_score), 4),
            "preference_score": round(preference_score, 4),
            "affinity_score": round(affinity_score, 4),
            "recency_score": round(recency_score, 4),
            "engagement_score": round(engagement_score, 4),
            "thread_importance_score": round(thread_importance_score, 4),
            "exploration_score": round(exploration_score, 4),
        }

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
            topic_lower = topic.lower()
            if topic_lower in text:
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
        hours = _hours_since(date_str)
        if hours <= 24:
            return 1.0
        # 24h 后每 6 小时衰减一半
        decay = math.pow(0.5, (hours - 24) / 6)
        return max(0.0, decay)

    def _calc_thread_importance(self, thread_info: dict[str, Any]) -> float:
        """计算 Thread 重要性得分"""
        # 基于 source_count 和 freshness
        source_count = thread_info.get("source_count", 1)
        last_seen = thread_info.get("last_seen_at", "")

        # source_count 越多越重要
        source_score = min(1.0, source_count / 5)

        # 新鲜度
        hours = _hours_since(last_seen)
        freshness_score = 1.0 if hours <= 24 else max(0.0, 1.0 - (hours - 24) / 72)

        return (source_score + freshness_score) / 2

    def _calc_exploration_score(
        self, item: dict[str, Any], user_profile: dict[str, Any]
    ) -> float:
        """计算探索得分"""
        # 如果 item 来自用户未互动过的任务/平台 → 探索得分高
        task_id = item.get("task_id", "")
        interacted_tasks = user_profile.get("interacted_tasks", set())

        if task_id and task_id not in interacted_tasks:
            return 0.8  # 高探索得分

        return 0.2  # 低探索得分


# 全局单例
recommendation_scorer = RecommendationScorer()
