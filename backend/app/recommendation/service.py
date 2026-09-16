"""
app/recommendation/service.py
Recommendation Service V2：个性化推荐引擎。

数据流：
Candidate Generation → Feature Extraction → Scoring → Ranking → Diversification → Explanation

R1: 支持完整交互分类（impression/open/dwell/star/hide/...）
R3: 负反馈持久化到 user_negative_feedback 表，并在候选生成时排除
"""
import logging
from typing import Any

from app.recommendation.candidates import candidate_generator
from app.recommendation.scoring import recommendation_scorer
from app.recommendation.diversification import diversifier
from app.recommendation.explanations import explanation_generator
from app.recommendation.profile import user_profile_builder

logger = logging.getLogger(__name__)

# R1: 交互类型权重映射
INTERACTION_WEIGHTS = {
    "impression": 0.1,
    "open": 0.3,
    "click_source": 0.4,
    "dwell": 0.5,
    "read": 0.6,
    "star": 1.0,
    "unstar": -0.5,
    "thread_expand": 0.4,
    "search": 0.2,
    "hide": -0.8,
    "not_interested": -1.0,
    "share": 0.8,
}


class RecommendationEngine:
    """推荐引擎 V2"""

    def __init__(
        self,
        exploration_ratio: float = 0.2,
        max_per_thread: int = 1,
        max_per_source: int = 4,
        max_per_topic: int = 6,
    ):
        self.exploration_ratio = exploration_ratio
        self.max_per_thread = max_per_thread
        self.max_per_source = max_per_source
        self.max_per_topic = max_per_topic

    def recommend(
        self,
        user_id: str | None = None,
        limit: int = 20,
        exclude_read: bool = True,
    ) -> list[dict[str, Any]]:
        """
        获取个性化推荐。
        """
        # 1. 构建用户画像
        user_profile = user_profile_builder.build(user_id)

        # 2. 候选生成
        candidates = candidate_generator.generate(user_id, limit=500)
        if not candidates:
            return []

        # 3. 评分
        scored_items = []
        for item in candidates:
            if exclude_read and item.get("is_read"):
                continue

            score_details = recommendation_scorer.score(item, user_profile)
            scored_items.append({
                **item,
                "recommendation_score": score_details["total_score"],
                "score_details": score_details,
            })

        # 4. 排序
        scored_items.sort(key=lambda x: x["recommendation_score"], reverse=True)

        # 5. 多样性
        diverse_items = diversifier.apply(scored_items)

        # 6. 解释
        result = []
        for item in diverse_items[:limit]:
            reasons = explanation_generator.generate(
                item, item.get("score_details", {}), user_profile
            )
            result.append({
                **item,
                "recommendation_reasons": reasons,
            })

        logger.info(
            "Recommendation: %d candidates -> %d results (exploration=%.0f%%)",
            len(candidates), len(result), self.exploration_ratio * 100,
        )
        return result

    def record_interaction(
        self,
        item_id: str,
        interaction_type: str,
        dwell_seconds: int | None = None,
    ) -> dict[str, Any]:
        """
        R1: 记录用户交互事件（完整分类）。

        Args:
            item_id: Item ID
            interaction_type: 交互类型 (impression/open/dwell/star/hide/...)
            dwell_seconds: 停留秒数

        Returns:
            交互记录
        """
        from app.repositories.user_prefs_repo import user_interaction_repo

        weight = INTERACTION_WEIGHTS.get(interaction_type, 0.1)
        return user_interaction_repo.record(
            item_id=item_id,
            interaction_type=interaction_type,
            dwell_seconds=dwell_seconds,
            weight=weight,
        )

    def record_feedback(
        self,
        feedback_type: str,
        target_value: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """
        R3: 记录用户负反馈。

        Args:
            feedback_type: 反馈类型 (not_interested, hide_source, mute_topic)
            target_value: 目标值 (item_id / source_id / topic_keyword)
            reason: 原因说明

        Returns:
            反馈记录
        """
        from app.repositories.user_prefs_repo import user_interaction_repo

        fid = user_interaction_repo.record_negative_feedback(
            feedback_type=feedback_type,
            target_value=target_value,
            reason=reason,
        )

        logger.info("Negative feedback recorded: %s -> %s", feedback_type, target_value[:40])
        return {"id": fid, "feedback_type": feedback_type, "target_value": target_value}


# 全局单例
recommendation_engine = RecommendationEngine()
