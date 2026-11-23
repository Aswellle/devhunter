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

        # 1. 偏好匹配（尽量点出命中的具体兴趣词）
        if score_details.get("preference_score", 0) > 0.3:
            reasons.append({
                "type": "topic",
                "label": self._topic_label(item, user_profile),
            })

        # 2. 亲缘度（现行评分器中 affinity_score 是 0.6*任务 + 0.4*来源 的加权
        # 衰减累积值，0.05+ 已代表多次交互；0.3 的旧阈值按 V2 尺度写的，永不可达）
        if score_details.get("affinity_score", 0) > 0.05:
            task_name = item.get("task_name", "")
            if task_name:
                reasons.append({
                    "type": "affinity",
                    "label": f"你最近常看 {task_name}",
                })

        # 3. 新鲜度：按条目真实年龄出标签，与卡片上的时间戳保持同一口径。
        #    旧实现用 recency_score > 0.8 判定"刚刚发布"，而当时的分数在
        #    24 小时内恒为 1.0——"刚刚发布"会挂在"3 小时前""20 小时前"
        #    的条目上，徽章与时间戳自相矛盾。
        recency_hours = score_details.get("recency_hours")
        if recency_hours is not None:
            if recency_hours < 1:
                reasons.append({"type": "recency", "label": "刚刚发布"})
            elif recency_hours < 24:
                reasons.append({"type": "recency", "label": "今日发布"})
        elif score_details.get("recency_score", 0) > 0.8:
            # 兼容未提供 recency_hours 的调用方：不给任何时间断言
            reasons.append({"type": "recency", "label": "新鲜内容"})

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

        # 6. 探索：只在探索对总分的加权贡献足够大时展示（探索模式或
        #    高新奇度），避免把"没交互过的来源"全标成探索徽章
        if (
            score_details.get("exploration_contribution", 0) >= 0.08
            and score_details.get("exploration_score", 0) > 0.5
        ):
            reasons.append({
                "type": "exploration",
                "label": "探索新领域",
            })

        return reasons

    def _topic_label(self, item: dict[str, Any], user_profile: dict[str, Any]) -> str:
        """主题匹配原因：点出命中的兴趣词，匹配不到时回退到通用文案。"""
        topics = user_profile.get("topics") or []
        title = (item.get("title") or "").lower()
        summary = (item.get("summary") or "").lower()
        for topic in topics:
            t = str(topic).lower().strip()
            if t and (t in title or t in summary):
                return f"匹配你的兴趣「{topic}」"
        return "符合你的兴趣"


# 全局单例
explanation_generator = ExplanationGenerator()
