"""
app/services/recommendation_service.py
个性化推荐业务层
基于用户偏好主题、行为亲缘度、 item 新鲜度计算推荐得分
"""
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any

from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.user_prefs_repo import (
    recommendation_config_repo,
    user_affinity_repo,
    user_interaction_repo,
    user_topics_repo,
)
from app.utils.similarity import tokenize

logger = logging.getLogger(__name__)

# 默认推荐配置
DEFAULT_CONFIG = {
    "topic_match_weight": 0.4,
    "affinity_weight": 0.3,
    "recency_weight": 0.2,
    "engagement_weight": 0.1,
    "min_score_threshold": 0.1,
    "max_items": 20,
    "dwell_time_decay": 0.95,
    "view_decay": 0.9,
    "affinity_boost": 0.1,
}


def _get_config(key: str) -> float:
    return recommendation_config_repo.get(key, DEFAULT_CONFIG.get(key, 0.0))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hours_since(iso_date: str) -> float:
    """计算距离 ISO 日期的小时数"""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        return delta.total_seconds() / 3600
    except Exception:
        return 999.0  # 默认极大值


class RecommendationService:

    def get_recommended_items(
        self,
        limit: int = 20,
        exclude_read: bool = True,
    ) -> list[dict]:
        """
        获取个性化推荐 Items。

        评分公式：
        score = topic_weight * topic_score
              + affinity_weight * affinity_score
              + recency_weight * recency_score
              + engagement_weight * engagement_score

        1. 获取用户设置的主题偏好及其权重
        2. 获取用户对任务/平台的亲缘度
        3. 获取最近 N 条 Items
        4. 对每条 Item 计算综合得分
        5. 排序返回 top N
        """
        config = {
            "topic_match_weight": _get_config("topic_match_weight"),
            "affinity_weight": _get_config("affinity_weight"),
            "recency_weight": _get_config("recency_weight"),
            "engagement_weight": _get_config("engagement_weight"),
            "min_score_threshold": _get_config("min_score_threshold"),
            "max_items": min(limit, int(_get_config("max_items"))),
        }

        # 1. 获取用户主题偏好
        user_topics = user_topics_repo.get_all_topics_with_weights()
        topic_tokens_map: dict[str, float] = {topic: weight for topic, weight in user_topics}

        # 2. 获取亲缘度映射
        affinity_map = user_affinity_repo.get_all_affinities_map()

        # 3. 获取亲缘任务列表（得分 > 0.5 的任务优先）
        task_affinities = {
            r["affinity_value"]: r["affinity_score"]
            for r in user_affinity_repo.get_top_affinities(affinity_type="task", limit=50)
            if r["affinity_score"] > 0.3
        }
        platform_affinities = {
            r["affinity_value"]: r["affinity_score"]
            for r in user_affinity_repo.get_top_affinities(affinity_type="platform", limit=20)
        }

        # 4. 获取候选 Items（最近 7 天）
        items, total = item_repo.query(page=1, per_page=500)
        if not items:
            return []

        # 5. 计算每条 Item 的推荐得分
        scored_items: list[tuple[float, dict]] = []
        for item in items:
            if exclude_read and item.get("is_read"):
                continue

            score = self._compute_item_score(
                item=item,
                topic_tokens_map=topic_tokens_map,
                affinity_map=affinity_map,
                task_affinities=task_affinities,
                platform_affinities=platform_affinities,
                config=config,
            )

            if score >= config["min_score_threshold"]:
                scored_items.append((score, item))

        # 6. 排序返回 top N
        scored_items.sort(key=lambda x: x[0], reverse=True)
        result = scored_items[: config["max_items"]]

        return [
            {**item, "recommendation_score": round(score, 4)}
            for score, item in result
        ]

    def _compute_item_score(
        self,
        item: dict,
        topic_tokens_map: dict[str, float],
        affinity_map: dict[str, float],
        task_affinities: dict[str, float],
        platform_affinities: dict[str, float],
        config: dict,
    ) -> float:
        """
        计算单条 Item 的推荐得分。
        """
        title = item.get("title", "")
        summary = item.get("summary", "") or ""
        task_id = item.get("task_id", "")
        task_name = item.get("task_name", "") or ""
        fetched_at = item.get("fetched_at", "")

        # ── 1. 主题匹配得分 ──────────────────────────────
        topic_score = self._calc_topic_score(title + " " + summary, topic_tokens_map)

        # ── 2. 亲缘度得分 ────────────────────────────────
        affinity_score = 0.0

        # 任务亲缘度
        task_score = task_affinities.get(task_id, 0.0)
        if task_score > 0:
            affinity_score += task_score * 0.6

        # 平台亲缘度
        if task_name:
            plat_score = platform_affinities.get(task_name, 0.0)
            if plat_score > 0:
                affinity_score += plat_score * 0.4

        # ── 3. 新鲜度得分 ───────────────────────────────
        recency_score = self._calc_recency_score(fetched_at)

        # ── 4. 参与度得分 ───────────────────────────────
        engagement_score = self._calc_engagement_score(item)

        # ── 综合得分 ───────────────────────────────────
        total = (
            config["topic_match_weight"] * topic_score
            + config["affinity_weight"] * affinity_score
            + config["recency_weight"] * recency_score
            + config["engagement_weight"] * engagement_score
        )

        return min(1.0, total)

    def _calc_topic_score(self, text: str, topic_tokens_map: dict[str, float]) -> float:
        """计算文本与用户主题偏好的匹配程度"""
        if not topic_tokens_map:
            return 0.0

        text_lower = text.lower()
        text_tokens = set(tokenize(text_lower))

        if not text_tokens:
            return 0.0

        matched_weight = 0.0
        total_weight = 0.0

        for topic, weight in topic_tokens_map.items():
            total_weight += weight
            # 检查主题词是否出现在文本中
            topic_lower = topic.lower()
            if topic_lower in text_lower:
                # 完全匹配主题词
                matched_weight += weight
            else:
                # 检查主题词分词后是否在文本中
                topic_tokens = set(tokenize(topic_lower))
                if topic_tokens & text_tokens:
                    matched_weight += weight * 0.5  # 部分匹配打五折

        if total_weight == 0:
            return 0.0
        return matched_weight / total_weight

    def _calc_recency_score(self, fetched_at: str) -> float:
        """新鲜度衰减得分：24h内为1.0，之后指数衰减"""
        hours = _hours_since(fetched_at)
        if hours <= 24:
            return 1.0
        # 24h后每6小时衰减一半
        decay = math.pow(0.5, (hours - 24) / 6)
        return max(0.0, decay)

    def _calc_engagement_score(self, item: dict) -> float:
        """参与度得分：根据已有交互数据计算"""
        item_id = item.get("id", "")
        if not item_id:
            return 0.0

        stats = user_interaction_repo.get_user_engagement_stats(item_id)
        view_count = stats.get("view_count", 0) or 0
        avg_dwell = stats.get("avg_dwell_seconds", 0) or 0

        # 有阅读记录 → 有参与
        if view_count > 0:
            # 标准化：阅读3次以上得满分，停留30秒以上得满分
            view_score = min(1.0, view_count / 3)
            dwell_score = min(1.0, avg_dwell / 30)
            return (view_score + dwell_score) / 2
        return 0.0

    def record_interaction(
        self,
        item_id: str,
        interaction_type: str,
        dwell_seconds: int | None = None,
    ) -> dict:
        """
        记录用户交互，并更新亲缘度。
        """
        # 1. 记录交互（返回完整记录含 created_at）
        interaction = user_interaction_repo.record(
            item_id=item_id,
            interaction_type=interaction_type,
            dwell_seconds=dwell_seconds,
        )

        # 2. 获取 item 信息
        item = item_repo.get(item_id)
        if not item:
            return interaction

        task_id = item.get("task_id", "")
        task_name = item.get("task_name", "") or ""

        # 3. 更新亲缘度
        if interaction_type in ("view", "click", "dwell"):
            # 任务亲缘度 +0.05
            if task_id:
                user_affinity_repo.update_affinity("task", task_id, score_delta=0.05)

            # 平台亲缘度 +0.03
            if task_name:
                user_affinity_repo.update_affinity("platform", task_name, score_delta=0.03)

        elif interaction_type == "star":
            # 收藏亲缘度更高 +0.1
            if task_id:
                user_affinity_repo.update_affinity("task", task_id, score_delta=0.1)
            if task_name:
                user_affinity_repo.update_affinity("platform", task_name, score_delta=0.08)

        # 4. 关键词亲缘度（从标题提取）
        if interaction_type in ("view", "dwell") and dwell_seconds and dwell_seconds > 10:
            keywords = self._extract_keywords(item.get("title", ""))
            for kw in keywords[:3]:  # 最多取3个关键词
                user_affinity_repo.update_affinity("keyword", kw, score_delta=0.02)

        return interaction

    def _extract_keywords(self, text: str) -> list[str]:
        """从文本提取关键词（简单分词）"""
        tokens = tokenize(text.lower())
        # 过滤停用词和短词
        stopwords = {"the", "a", "an", "is", "are", "in", "on", "at", "to", "for", "of", "and", "or", "with", "by"}
        keywords = [t for t in tokens if len(t) > 3 and t not in stopwords]
        return keywords[:5]

    # ── 用户偏好管理 ────────────────────────────────────────

    def get_user_topics(self) -> list[dict]:
        """获取用户主题偏好列表"""
        return user_topics_repo.list_all()

    def add_user_topic(self, topic: str, category: str = "custom", weight: float = 1.0) -> dict:
        """添加用户主题偏好"""
        return user_topics_repo.upsert(topic=topic, category=category, weight=weight)

    def remove_user_topic(self, topic: str) -> bool:
        """删除用户主题偏好"""
        return user_topics_repo.delete_by_topic(topic)

    def update_user_topic_weight(self, topic: str, weight: float) -> dict | None:
        """更新主题权重"""
        existing = user_topics_repo.get_by_topic(topic)
        if not existing:
            return None
        now = _now_iso()
        with __import__("app.core.database", fromlist=["get_db"]).get_db() as conn:
            conn.execute(
                "UPDATE user_topics SET weight = ?, updated_at = ? WHERE topic = ?",
                (weight, now, topic),
            )
        return user_topics_repo.get_by_topic(topic)

    def get_recommended_topics(self, limit: int = 10) -> list[dict]:
        """
        根据用户阅读历史，推荐可能感兴趣的主题。
        从用户高亲缘度的任务/平台中提取关键词作为推荐。
        """
        affinities = user_affinity_repo.get_top_affinities(limit=20)
        if not affinities:
            return []

        # 从高亲缘度任务名提取推荐
        recommended: list[tuple[str, str, float]] = []
        for aff in affinities:
            if aff["affinity_type"] == "task":
                # 从任务名提取词作为推荐主题
                tokens = tokenize(aff["affinity_value"].lower())
                for token in tokens:
                    if len(token) > 2:
                        recommended.append((token, "ai" if any(k in token for k in ["ai", "ml", "gpt", "llm"]) else "custom", aff["affinity_score"]))
            elif aff["affinity_type"] == "keyword":
                recommended.append((aff["affinity_value"], "custom", aff["affinity_score"]))

        # 去重并按得分排序
        seen = set()
        unique_recs = []
        for topic, category, score in recommended:
            if topic not in seen:
                seen.add(topic)
                unique_recs.append({"topic": topic, "category": category, "score": round(score, 2)})

        unique_recs.sort(key=lambda x: x["score"], reverse=True)
        return unique_recs[:limit]


# 全局单例
recommendation_service = RecommendationService()
