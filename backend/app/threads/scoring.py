"""
app/threads/scoring.py
Thread Scoring：多因素 Thread 聚类评分。

评分公式：
thread_score =
    0.30 * lexical_score
  + 0.25 * entity_score
  + 0.20 * semantic_score
  + 0.15 * temporal_score
  + 0.10 * source_score

其中：
- lexical_score: Jaccard 标题相似度
- entity_score: 实体重叠度
- semantic_score: 语义相似度（基于内容指纹）
- temporal_score: 时间相似度
- source_score: 来源独立性（跨平台共识 vs 同源重复）
"""
import logging
from dataclasses import dataclass, field
from typing import Any

from app.features.temporal import temporal_score, detect_event_type, get_event_window_hours
from app.utils.similarity import jaccard_similarity

logger = logging.getLogger(__name__)


@dataclass
class ThreadScore:
    """Thread 匹配评分"""
    total_score: float = 0.0
    lexical_score: float = 0.0
    entity_score: float = 0.0
    semantic_score: float = 0.0
    temporal_score: float = 0.0
    source_score: float = 0.0
    confidence: str = "low"  # high | medium | low

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_score": round(self.total_score, 4),
            "lexical_score": round(self.lexical_score, 4),
            "entity_score": round(self.entity_score, 4),
            "semantic_score": round(self.semantic_score, 4),
            "temporal_score": round(self.temporal_score, 4),
            "source_score": round(self.source_score, 4),
            "confidence": self.confidence,
        }


class ThreadScorer:
    """Thread 多因素评分器"""

    # 权重配置
    WEIGHTS = {
        "lexical": 0.30,
        "entity": 0.25,
        "semantic": 0.20,
        "temporal": 0.15,
        "source": 0.10,
    }

    # 置信度阈值
    CONFIDENCE_THRESHOLDS = {
        "high": 0.70,
        "medium": 0.45,
        "low": 0.0,
    }

    def score(
        self,
        new_item: dict[str, Any],
        candidate_thread: dict[str, Any],
        new_features: dict[str, Any] | None = None,
        candidate_features: dict[str, Any] | None = None,
    ) -> ThreadScore:
        """
        计算新 Item 与候选 Thread 的匹配分数。

        Args:
            new_item: 新 Item dict
            candidate_thread: 候选 Thread dict
            new_features: 新 Item 的特征（可选）
            candidate_features: 候选 Thread 的特征（可选）

        Returns:
            ThreadScore 对象
        """
        score = ThreadScore()

        # 1. Lexical score (Jaccard)
        new_title = new_item.get("title", "")
        thread_title = candidate_thread.get("title", "")
        score.lexical_score = jaccard_similarity(new_title, thread_title)

        # 2. Entity score (实体重叠)
        score.entity_score = self._calc_entity_score(
            new_features.get("entities", {}) if new_features else {},
            candidate_features.get("entities", {}) if candidate_features else {},
        )

        # 3. Semantic score (内容指纹)
        score.semantic_score = self._calc_semantic_score(
            new_features.get("fingerprint", "") if new_features else "",
            candidate_features.get("fingerprint", "") if candidate_features else "",
        )

        # 4. Temporal score (时间相似度)
        new_date = new_item.get("published_at") or new_item.get("fetched_at", "")
        thread_date = candidate_thread.get("last_seen_at") or candidate_thread.get("first_seen_at", "")
        event_type = detect_event_type(new_title, new_item.get("summary", ""))
        window_hours = get_event_window_hours(event_type)
        score.temporal_score = temporal_score(new_date, thread_date, window_hours)

        # 5. Source score (来源独立性)
        score.source_score = self._calc_source_score(
            new_item.get("source_id", ""),
            candidate_thread.get("platforms", []),
        )

        # 加权总分
        score.total_score = (
            self.WEIGHTS["lexical"] * score.lexical_score
            + self.WEIGHTS["entity"] * score.entity_score
            + self.WEIGHTS["semantic"] * score.semantic_score
            + self.WEIGHTS["temporal"] * score.temporal_score
            + self.WEIGHTS["source"] * score.source_score
        )

        # 置信度
        if score.total_score >= self.CONFIDENCE_THRESHOLDS["high"]:
            score.confidence = "high"
        elif score.total_score >= self.CONFIDENCE_THRESHOLDS["medium"]:
            score.confidence = "medium"
        else:
            score.confidence = "low"

        return score

    def _calc_entity_score(
        self,
        entities_a: dict[str, list[str]],
        entities_b: dict[str, list[str]],
    ) -> float:
        """计算实体重叠度"""
        if not entities_a or not entities_b:
            return 0.0

        # 收集所有实体类型
        all_types = set(entities_a.keys()) | set(entities_b.keys())
        if not all_types:
            return 0.0

        total_overlap = 0.0
        for entity_type in all_types:
            set_a = set(entities_a.get(entity_type, []))
            set_b = set(entities_b.get(entity_type, []))
            if set_a and set_b:
                intersection = set_a & set_b
                union = set_a | set_b
                total_overlap += len(intersection) / len(union)

        return total_overlap / len(all_types)

    def _calc_semantic_score(self, fingerprint_a: str, fingerprint_b: str) -> float:
        """计算语义相似度（基于内容指纹）"""
        if not fingerprint_a or not fingerprint_b:
            return 0.0
        # 完全相同 → 1.0，否则 → 0.0
        # 未来可以改为 embedding 相似度
        return 1.0 if fingerprint_a == fingerprint_b else 0.0

    def _calc_source_score(self, new_source_id: str, thread_platforms: list[str]) -> float:
        """
        计算来源独立性分数。

        - 新 Item 来源不在 Thread 已有来源中 → 1.0（跨平台共识）
        - 新 Item 来源已在 Thread 已有来源中 → 0.3（同源重复）
        """
        if not new_source_id:
            return 0.5  # 未知来源

        if not thread_platforms:
            return 1.0  # 空 Thread，视为跨平台

        if new_source_id in thread_platforms:
            return 0.3  # 同源重复

        return 1.0  # 跨平台共识


# 全局单例
thread_scorer = ThreadScorer()
