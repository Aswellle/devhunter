"""
app/recommendation/eval_metrics.py
推荐排序离线评测指标（二元相关度，纯函数无 I/O）。

约定：
- ranked_ids：管线输出的条目 ID，按推荐排序（降序）
- relevant_ids：相关条目 ID 集合（gold 标注 relevant=1）
- k：只考察前 k 个位置
"""
from __future__ import annotations

import math


def _validate_k(k: int) -> int:
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")
    return k


def precision_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """前 k 位中相关条目的占比，值域 [0, 1]"""
    _validate_k(k)
    if k > len(ranked_ids):
        k = len(ranked_ids)
    if k == 0:
        return 0.0
    hits = sum(1 for item_id in ranked_ids[:k] if item_id in relevant_ids)
    return hits / k


def recall_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """相关条目中被排进前 k 位的占比，值域 [0, 1]；相关集为空返回 0"""
    _validate_k(k)
    if not relevant_ids:
        return 0.0
    hits = sum(1 for item_id in ranked_ids[:k] if item_id in relevant_ids)
    return hits / len(relevant_ids)


def ndcg_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    二元相关度 NDCG@k，值域 [0, 1]。

    DCG  = Σ rel_i / log2(i + 1)（i 从 1 起）
    IDCG = 理想排序（前 min(k, |relevant|) 位全相关）的 DCG
    """
    _validate_k(k)
    if not relevant_ids:
        return 0.0

    def dcg(gains: list[float]) -> float:
        # 位置从 1 起，折减分母 log2(位置 + 1)
        return sum(g / math.log2(pos + 1) for pos, g in enumerate(gains, start=1))

    actual_gains = [1.0 if item_id in relevant_ids else 0.0 for item_id in ranked_ids[:k]]
    ideal_gains = [1.0] * min(k, len(relevant_ids))
    ideal_dcg = dcg(ideal_gains)
    if ideal_dcg == 0.0:
        return 0.0
    return dcg(actual_gains) / ideal_dcg


def pairwise_win_rate(
    positive_scores: list[float],
    negative_scores: list[float],
) -> float | None:
    """
    排序贴合度：正例得分高于负例的比例（平局计 0.5），值域 [0, 1]。

    金标评估用——正负例得分来自标注时的快照，不依赖当前排序会话。
    没有可比较的正负对时返回 None（样本不足；调用方不应显示为 0%）。
    """
    pairs = [(p, n) for p in positive_scores for n in negative_scores]
    if not pairs:
        return None
    wins = sum(
        1.0 if p > n else 0.5 if p == n else 0.0
        for p, n in pairs
    )
    return wins / len(pairs)
