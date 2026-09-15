"""
app/recommendation/service.py
Recommendation Service V2：个性化推荐引擎。

数据流：
Candidate Generation → Feature Extraction → Scoring → Ranking → Diversification → Explanation
"""
import logging
from typing import Any

from app.recommendation.candidates import candidate_generator
from app.recommendation.scoring import recommendation_scorer
from app.recommendation.diversification import diversifier
from app.recommendation.explanations import explanation_generator
from app.recommendation.profile import user_profile_builder

logger = logging.getLogger(__name__)


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

        Args:
            user_id: 用户 ID
            limit: 返回数量
            exclude_read: 排除已读

        Returns:
            推荐 Item 列表（含得分和解释）
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

    def record_feedback(
        self,
        item_id: str,
        feedback_type: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """
        记录用户反馈（负反馈）。

        Args:
            item_id: Item ID
            feedback_type: 反馈类型 (not_interested, dismiss, hide)
            reason: 原因 (topic, source, keyword)

        Returns:
            反馈记录
        """
        from app.repositories.user_prefs_repo import user_interaction_repo

        # 记录负反馈
        interaction = user_interaction_repo.record(
            item_id=item_id,
            interaction_type=feedback_type,
        )

        # 根据原因调整亲缘度
        if reason == "topic":
            # 降低主题亲缘度
            pass
        elif reason == "source":
            # 降低来源亲缘度
            pass

        return interaction


# 全局单例
recommendation_engine = RecommendationEngine()
