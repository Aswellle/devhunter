"""
app/recommendation/explanations.py
Recommendation Explanations：推荐解释生成。

为每个推荐结果生成可解释的原因。
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ExplanationGenerator:
    """推荐解释生成器"""

    def generate(
        self,
        item: dict[str, Any],
        score_details: dict[str, Any],
        user_profile: dict[str, Any],
    ) -> list[dict[str, str]]:
        """
        生成推荐解释。

        Args:
            item: Item dict
            score_details: 评分详情
            user_profile: 用户画像

        Returns:
            推荐原因列表，每个原因包含 type 和 label
        """
        reasons = []

        # 1. 偏好匹配
        if score_details.get("preference_score", 0) > 0.3:
            reasons.append({
                "type": "topic",
                "label": "符合你的兴趣",
            })

        # 2. 亲缘度
        if score_details.get("affinity_score", 0) > 0.3:
            task_name = item.get("task_name", "")
            if task_name:
                reasons.append({
                    "type": "affinity",
                    "label": f"你最近常看 {task_name}",
                })

        # 3. 新鲜度
        if score_details.get("recency_score", 0) > 0.8:
            reasons.append({
                "type": "recency",
                "label": "刚刚发布",
            })

        # 4. 参与度
        if score_details.get("engagement_score", 0) > 0.5:
            reasons.append({
                "type": "engagement",
                "label": "你之前看过类似内容",
            })

        # 5. Thread 重要性
        if score_details.get("thread_importance_score", 0) > 0.5:
            reasons.append({
                "type": "thread",
                "label": "多平台热议事件",
            })

        # 6. 探索
        if score_details.get("exploration_score", 0) > 0.5:
            reasons.append({
                "type": "exploration",
                "label": "探索新领域",
            })

        return reasons


# 全局单例
explanation_generator = ExplanationGenerator()
