"""
app/services/recommendation_service.py
个性化推荐业务层
基于用户偏好主题、行为亲缘度、 item 新鲜度计算推荐得分
"""
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.user_prefs_repo import (
    recommendation_config_repo,
    user_affinity_repo,
    user_interaction_repo,
    user_topics_repo,
)
from app.recommendation.explanations import explanation_generator
from app.utils.similarity import tokenize

logger = logging.getLogger(__name__)

# 解析失败时的默认年龄（小时）：使新鲜度得分衰减至接近 0
_MAX_HOURS_AGE = 999.0

# 默认推荐配置
DEFAULT_CONFIG = {
    "topic_match_weight": 0.35,
    "affinity_weight": 0.3,
    "recency_weight": 0.2,
    "engagement_weight": 0.1,
    "exploration_weight": 0.05,
    "min_score_threshold": 0.1,
    "max_items": 20,
    "dwell_time_decay": 0.95,
    "view_decay": 0.9,
    "affinity_boost": 0.1,
}


def _get_config(key: str) -> float:
    return recommendation_config_repo.get(key, DEFAULT_CONFIG.get(key, 0.0))


def _is_parseable_date(value: str) -> bool:
    """ISO 日期是否可解析（坏日期回退用）。"""
    if not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except (ValueError, TypeError):
        return False


def _hours_since(iso_date: str) -> float:
    """计算距离 ISO 日期的小时数。

    未来时间（来源时区错误/伪造）clamp 到 0——负小时数会破坏下游
    "年龄非负"的假设；解析失败返回最大年龄（新鲜度归零）。"""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        hours = delta.total_seconds() / 3600
        if hours < 0:
            logger.debug("Future date clamped to 0 hours: %s", iso_date)
            return 0.0
        return hours
    except Exception:
        logger.debug("Failed to parse date: %s", iso_date)
        return _MAX_HOURS_AGE


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
        scored = self.score_candidates(exclude_read=exclude_read)
        max_items = min(limit, int(_get_config("max_items")))
        return scored[:max_items]

    def score_candidates(self, exclude_read: bool = True) -> list[dict]:
        """
        候选生成 + 四因子打分 + 降序排序（推荐列表与打标采样共用同一条路径，
        保证打标快照的 sampled_score 与推荐位次可比）。

        返回通过最低分阈值的全部候选（按得分降序），不打 top-N 截断。
        """
        config = {
            "topic_match_weight": _get_config("topic_match_weight"),
            "affinity_weight": _get_config("affinity_weight"),
            "recency_weight": _get_config("recency_weight"),
            "engagement_weight": _get_config("engagement_weight"),
            "exploration_weight": _get_config("exploration_weight"),
            "min_score_threshold": _get_config("min_score_threshold"),
        }

        # 1. 获取用户主题偏好
        user_topics = user_topics_repo.get_all_topics_with_weights()
        topic_tokens_map: dict[str, float] = {topic: weight for topic, weight in user_topics}

        # 2. 获取亲缘度映射
        affinity_map = user_affinity_repo.get_all_affinities_map()

        # 2.5 负反馈：用户明确拒绝过的内容不再推荐。
        #     旧实现只把反馈写进 user_negative_feedback 表，打分循环从不读取，
        #     前端也没有入口——"不感兴趣"保存后完全不起作用。
        #     语义：not_interested / mute_topic 隐藏该条目本身；
        #     hide_source 隐藏该条目所属来源（任务/平台）的全部条目。
        dismissed_ids, hidden_task_ids, hidden_source_names = (
            self._load_negative_feedback()
        )

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
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
        items, total = item_repo.query(page=1, per_page=500, created_after=cutoff_date)
        if not items:
            return []

        # F1: 批量预取所有候选 item 的参与度统计，避免循环内逐条查询（N+1）
        engagement_stats_map = user_interaction_repo.get_engagement_stats_bulk(
            [item["id"] for item in items if item.get("id")]
        )

        # 推荐解释用：把用户兴趣词传给解释器，让它点出具体命中的兴趣
        user_profile = {"topics": [topic for topic, _ in user_topics]}

        # 5. 计算每条 Item 的推荐得分
        scored_items: list[tuple[float, dict]] = []
        for item in items:
            if exclude_read and item.get("is_read"):
                continue
            if item.get("id") in dismissed_ids:
                continue
            if (item.get("task_id") in hidden_task_ids
                    or (item.get("task_name") or "") in hidden_source_names):
                continue

            score, score_details = self._compute_item_score_details(
                item=item,
                topic_tokens_map=topic_tokens_map,
                affinity_map=affinity_map,
                task_affinities=task_affinities,
                platform_affinities=platform_affinities,
                config=config,
                engagement_stats_map=engagement_stats_map,
            )

            if score >= config["min_score_threshold"]:
                # F5: 附上可解释的推荐理由（前端以徽章展示）
                reasons = explanation_generator.generate(item, score_details, user_profile)
                scored_items.append((score, {**item, "recommendation_reasons": reasons}))

        # 6. 按得分降序
        scored_items.sort(key=lambda x: x[0], reverse=True)

        return [
            {**item, "recommendation_score": round(score, 4)}
            for score, item in scored_items
        ]

    # ── 推荐质量打标（金标采样）─────────────────────────────

    def sample_for_labeling(self, limit: int = 8) -> list[dict]:
        """
        为打标助手采样候选：复用推荐的同一条打分路径，在通过最低分阈值的
        候选中按排名等距取样（头部/中部/尾部都覆盖，只盯头部会把评估变成
        对排序头部的自查）。只返回未打标过的条目。

        返回条目带 recommendation_score（采样时快照，落标时一并存储，
        指标不随后续权重调整漂移）。
        """
        from app.repositories.relevance_repo import relevance_label_repo

        scored = self.score_candidates(exclude_read=True)
        if not scored:
            return []
        labeled = relevance_label_repo.get_labeled_item_ids()
        pool = [item for item in scored if item["id"] not in labeled]
        if not pool:
            return []

        step = max(1, len(pool) // limit)
        sampled = pool[::step][:limit]
        # 采样分数落服务端快照：落标时以此为准，客户端回传值不采信
        relevance_label_repo.record_samples(
            [(item["id"], item["recommendation_score"]) for item in sampled]
        )
        return [
            {
                "id": item["id"],
                "task_id": item.get("task_id"),
                "task_name": item.get("task_name"),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "summary": item.get("summary"),
                "fetched_at": item.get("fetched_at", ""),
                "published_at": item.get("published_at", ""),
                "recommendation_score": item["recommendation_score"],
            }
            for item in sampled
        ]

    def record_label(self, item_id: str, label: bool) -> dict:
        """
        记录/改判一条金标（感兴趣 / 不感兴趣）。

        分数快照取自服务端的采样记录（take_sample_score 取走即删）；
        从未被采样过的条目得分为 NULL，计入总数但不参与贴合度计算；
        无新采样的改判沿用已存分数（仓储层 COALESCE）。
        """
        from app.repositories.relevance_repo import relevance_label_repo

        snapshot = relevance_label_repo.take_sample_score(item_id)
        return relevance_label_repo.upsert(
            item_id=item_id,
            label=label,
            sampled_score=snapshot,
        )

    def get_label_summary(self) -> dict:
        """
        打标汇总：计数 + 排序贴合度（正例得分高于负例的比例）。

        win_rate 为 None 表示正负样本不足，尚无法比较。
        """
        from app.recommendation.eval_metrics import pairwise_win_rate
        from app.repositories.relevance_repo import relevance_label_repo

        stats = relevance_label_repo.summary()
        scores = relevance_label_repo.list_scores()
        positive = [s for s, label in scores if label == 1]
        negative = [s for s, label in scores if label == 0]
        win_rate = pairwise_win_rate(positive, negative)
        return {
            **stats,
            "win_rate": round(win_rate, 4) if win_rate is not None else None,
        }

    def _compute_item_score(
        self,
        item: dict,
        topic_tokens_map: dict[str, float],
        affinity_map: dict[str, float],
        task_affinities: dict[str, float],
        platform_affinities: dict[str, float],
        config: dict,
        engagement_stats_map: dict[str, dict] | None = None,
    ) -> float:
        """
        计算单条 Item 的推荐得分（仅总分）。
        """
        return self._compute_item_score_details(
            item=item,
            topic_tokens_map=topic_tokens_map,
            affinity_map=affinity_map,
            task_affinities=task_affinities,
            platform_affinities=platform_affinities,
            config=config,
            engagement_stats_map=engagement_stats_map,
        )[0]

    def _compute_item_score_details(
        self,
        item: dict,
        topic_tokens_map: dict[str, float],
        affinity_map: dict[str, float],
        task_affinities: dict[str, float],
        platform_affinities: dict[str, float],
        config: dict,
        engagement_stats_map: dict[str, dict] | None = None,
    ) -> tuple[float, dict[str, float]]:
        """
        计算单条 Item 的推荐得分，并返回分因子明细（供推荐解释使用）。
        """
        title = item.get("title", "")
        summary = item.get("summary", "") or ""
        task_id = item.get("task_id", "")
        task_name = item.get("task_name", "") or ""
        # 新鲜度基准优先用原发时间：昨天发布、今天才抓到的内容不能按
        # 抓取时间拿满新鲜度分（时间语义见数据契约 published_at > fetched_at）。
        # 原发时间损坏时回退抓取时间，两个都损坏才拿最大年龄
        freshness_base = item.get("published_at") or ""
        if not _is_parseable_date(freshness_base):
            fallback = item.get("fetched_at") or ""
            freshness_base = fallback if _is_parseable_date(fallback) else ""

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
        recency_hours = _hours_since(freshness_base)
        recency_score = self._calc_recency_score(recency_hours)

        # ── 4. 参与度得分 ───────────────────────────────
        engagement_score = self._calc_engagement_score(item, engagement_stats_map)

        # ── 5. 探索得分（未接触过的来源/平台 → 新奇度高）────
        exploration_score = self._calc_exploration_score(
            task_id=task_id,
            task_name=task_name,
            task_affinities=task_affinities,
            platform_affinities=platform_affinities,
        )

        # ── 综合得分：归一化加权平均 ─────────────────────
        # 各模式预设权重之和可能不同（如探索模式的探索权重挤占了兴趣
        # 权重），若直接求和，切换模式会让所有条目的分数整体缩放——用户
        # 看到推荐分集体跳水、且低于 min_score_threshold 的条目会被整批
        # 过滤掉。按权重总和归一化后，分数始终是 [0,1] 的加权平均，
        # 换配置只改变排序含义，不改变分数量纲。
        weights = {
            "topic_match": (config["topic_match_weight"], topic_score),
            "affinity": (config["affinity_weight"], affinity_score),
            "recency": (config["recency_weight"], recency_score),
            "engagement": (config["engagement_weight"], engagement_score),
            "exploration": (config["exploration_weight"], exploration_score),
        }
        total_weight = sum(w for w, _ in weights.values())
        total = (
            sum(w * s for w, s in weights.values()) / total_weight
            if total_weight > 0 else 0.0
        )

        return min(1.0, total), {
            "preference_score": topic_score,
            "affinity_score": affinity_score,
            "recency_score": recency_score,
            "recency_hours": round(recency_hours, 2),
            "engagement_score": engagement_score,
            "exploration_score": exploration_score,
            # 探索对总分的加权贡献（解释器据此决定是否展示"探索"徽章，
            # 避免仅凭新奇度把"没交互过的来源"全标成探索）
            "exploration_contribution": (
                weights["exploration"][0] * exploration_score / total_weight
                if total_weight > 0 else 0.0
            ),
        }

    def _load_negative_feedback(
        self,
    ) -> tuple[set[str], set[str], set[str]]:
        """
        读取负反馈并解析为 (隐藏条目 id, 隐藏任务 id, 隐藏来源名)。

        反馈表的 target_value 统一存 item_id（见 API 层约定），
        hide_source 需要再解析到该条目的任务/平台，才能隐藏同源内容。
        """
        try:
            feedback = user_interaction_repo.get_negative_feedback_map()
        except Exception as e:  # 反馈表缺失等异常不应阻断推荐主链路
            logger.warning("Failed to load negative feedback: %s", e)
            return set(), set(), set()

        dismissed = feedback.get("not_interested", set()) | feedback.get("mute_topic", set())
        hidden_task_ids: set[str] = set()
        hidden_source_names: set[str] = set()
        for item_id in feedback.get("hide_source", set()):
            item = item_repo.get(item_id)
            if not item:
                continue
            if item.get("task_id"):
                hidden_task_ids.add(item["task_id"])
            if item.get("task_name"):
                hidden_source_names.add(item["task_name"])
        return dismissed, hidden_task_ids, hidden_source_names

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

    def _calc_recency_score(self, hours: float) -> float:
        """
        新鲜度得分：自发布起按 24 小时半衰期连续衰减。

        旧实现「24 小时内恒为 1.0，之后每 6 小时减半」有两个问题：
        1. 一天内的条目全部满新鲜度，同一批采集的条目得分完全并列
           （用户看到的推荐分全部相同，个性化信号被淹没）；
        2. 解释器以 recency_score > 0.8 判定"刚刚发布"，实际覆盖到
           ~26 小时内的条目——与"3 小时前""20 小时前"的时间戳自相矛盾。
        连续衰减让分钟级的新旧差异真实反映在分数里。
        """
        if hours <= 0:
            return 1.0
        if hours >= _MAX_HOURS_AGE:
            return 0.0
        return max(0.0, math.pow(0.5, hours / 24.0))

    def _calc_exploration_score(
        self,
        task_id: str,
        task_name: str,
        task_affinities: dict[str, float],
        platform_affinities: dict[str, float],
    ) -> float:
        """
        探索得分：来源越陌生，新奇度越高（1 - 熟悉度）。

        "探索发现"模式此前只是把四项权重整体调低（和为 0.6），既没有
        探索因子、也没有任何实际探索行为——模式名义存在、语义为空。
        这里以用户已积累的任务/平台亲缘度为熟悉度代理：从未交互过的
        来源新奇度为 1，随亲缘度累积线性下降。

        用户尚无任何交互足迹时返回 0（没有画像时"探索"无意义，
        不应把全部条目都标成探索）。
        """
        if not task_affinities and not platform_affinities:
            return 0.0
        task_known = min(1.0, task_affinities.get(task_id, 0.0)) if task_id else 0.0
        platform_known = (
            min(1.0, platform_affinities.get(task_name, 0.0)) if task_name else 0.0
        )
        familiarity = max(task_known, platform_known)
        return max(0.0, 1.0 - familiarity)

    def _calc_engagement_score(
        self, item: dict, engagement_stats_map: dict[str, dict] | None = None
    ) -> float:
        """参与度得分：根据已有交互数据计算"""
        item_id = item.get("id", "")
        if not item_id:
            return 0.0

        if engagement_stats_map is not None:
            stats = engagement_stats_map.get(item_id, {})
        else:
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

    def get_reading_affinities(self, limit: int = 50) -> list[dict]:
        """
        画像页「阅读偏好」展示数据：解析可读名称并合并重复维度。

        存储层语义：task 行的 affinity_value 是 task_id（对用户不可读），
        platform 行按历史约定存的是任务名称——两者描述的都是"任务"维度，
        直接展示会出现 UUID、且同一任务出现两行。这里把 task 行解析成
        任务名称后与 platform 行按名称合并（得分求和、互动次数取较大值，
        因为两行记录的是同一批交互），keyword 行原样透传。
        """
        rows = user_affinity_repo.get_top_affinities(limit=limit)
        task_name_cache: dict[str, str | None] = {}
        merged: dict[tuple[str, str], dict] = {}

        for row in rows:
            a_type = row.get("affinity_type", "")
            value = row.get("affinity_value", "")

            if a_type == "task":
                if value not in task_name_cache:
                    task = task_repo.get(value)
                    task_name_cache[value] = task.get("name") if task else None
                # 任务已删除（软删除）时保留一个可读的兜底名称
                name = task_name_cache[value] or "已删除的任务"
                display_type = "task"
            elif a_type == "platform":
                name = value
                display_type = "task"
            else:
                name = value
                display_type = a_type or "keyword"

            key = (display_type, name)
            if key in merged:
                agg = merged[key]
                agg["affinity_score"] = agg.get("affinity_score", 0.0) + row.get("affinity_score", 0.0)
                # 同一批交互会同时写入 task 与 platform 两行，互动次数取较大值而非求和
                agg["interaction_count"] = max(
                    agg.get("interaction_count", 0), row.get("interaction_count", 0)
                )
                agg["last_interacted_at"] = max(
                    agg.get("last_interacted_at") or "", row.get("last_interacted_at") or ""
                )
            else:
                merged[key] = {**row, "display_type": display_type, "display_value": name}

        return sorted(merged.values(), key=lambda r: r["affinity_score"], reverse=True)[:limit]

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
        user_topics_repo.update_weight(topic, weight)
        return user_topics_repo.get_by_topic(topic)

    def get_recommended_topics(self, limit: int = 10) -> list[dict]:
        """
        根据阅读历史推荐可能感兴趣的主题。

        候选来源（都可读且添加后真实参与「兴趣匹配」打分）：
        1. 阅读关键词亲缘——交互时从标题提取的关键词（英文词为主）
        2. 常读来源的**标题短语**——高频复现的标题分段（中文标题无空格，
           分词器拿不到词，改按 |｜:：-·、，《》 等分隔符拆段；
           同一短语在 ≥2 条标题出现才算主题候选）

        历史缺陷：task 类型亲缘的 affinity_value 是任务 UUID，旧实现直接
        对它分词，于是"推荐主题"是一堆 8 位十六进制编号（64da59ff…），
        用户既看不懂、添加后也匹配不到任何内容。这里彻底不再把 ID 当主题。
        """
        from collections import Counter

        affinities = user_affinity_repo.get_top_affinities(limit=30)
        if not affinities:
            return []

        existing = {str(t.get("topic", "")).strip().lower()
                    for t in user_topics_repo.list_all()}

        # topic(lower) → {"topic", "score", "reason"}
        candidates: dict[str, dict] = {}

        def _add(topic: str, score: float, reason: str) -> None:
            text = (topic or "").strip()
            if not self._is_meaningful_topic(text):
                return
            key = text.lower()
            if key in existing:
                return
            prev = candidates.get(key)
            if prev is None or score > prev["score"]:
                candidates[key] = {"topic": text, "score": score, "reason": reason}

        # 1) 阅读关键词（真实词，直接可匹配标题）。
        #    极低分关键词多为一次性的用户名/随机串，不进入候选
        for aff in affinities:
            if aff.get("affinity_type") != "keyword":
                continue
            score = float(aff.get("affinity_score") or 0.0)
            if score < 0.05:
                continue
            _add(
                str(aff.get("affinity_value", "")),
                score,
                "来自你的阅读关键词",
            )

        # 2) 常读来源的标题短语（中文标题按分隔符拆段，高频复现才采纳）
        top_task_ids = [
            a["affinity_value"] for a in affinities
            if a.get("affinity_type") == "task" and a.get("affinity_value")
        ][:3]
        # platform 亲缘存的是任务名称，用于给标题短语标注来源
        platform_names = {
            str(a.get("affinity_value", "")): float(a.get("affinity_score") or 0.0)
            for a in affinities
            if a.get("affinity_type") == "platform"
        }

        phrase_counter: Counter[str] = Counter()
        phrase_source: dict[str, str] = {}
        for task_id in top_task_ids:
            try:
                items, _ = item_repo.query(task_id=task_id, page=1, per_page=30)
            except Exception:  # 候选生成失败不应影响推荐主链路
                continue
            task_name = (items[0].get("task_name") if items else None) or ""
            for it in items:
                for seg in self._split_title_phrases(it.get("title") or ""):
                    phrase_counter[seg] += 1
                    if task_name and seg not in phrase_source:
                        phrase_source[seg] = task_name

        if phrase_counter:
            top_count = max(phrase_counter.values())
            for phrase, count in phrase_counter.most_common(40):
                if count < 2:
                    break
                source = phrase_source.get(phrase, "")
                reason = f"来自常读来源「{source}」的标题" if source else "来自你常读内容的标题"
                _add(phrase, count / top_count * 0.8, reason)

        ranked = sorted(candidates.values(), key=lambda c: c["score"], reverse=True)[:limit]
        return [
            {
                "topic": c["topic"],
                "category": self._guess_topic_category(c["topic"]),
                "score": round(c["score"], 2),
                "reason": c["reason"],
            }
            for c in ranked
        ]

    # UUID / 长十六进制串：绝不作为主题候选
    _UUID_RE = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    _HEX_TOKEN_RE = re.compile(r"^[0-9a-f]{6,}$", re.IGNORECASE)
    _TITLE_SPLIT_RE = re.compile(r"[|｜:：\-—–·、,，;；()（）\[\]【】《》<>/\\]+")
    _TOPIC_MAX_LEN = 24
    _TOPIC_MIN_LEN = 2

    def _is_meaningful_topic(self, text: str) -> bool:
        """主题候选过滤：剔除编号/纯数字/过长或过短片段"""
        if not (self._TOPIC_MIN_LEN <= len(text) <= self._TOPIC_MAX_LEN):
            return False
        if text.isdigit():
            return False
        if self._UUID_RE.match(text) or self._HEX_TOKEN_RE.match(text):
            return False
        # 纯符号/纯标点
        if not any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in text):
            return False
        return True

    def _split_title_phrases(self, title: str) -> list[str]:
        """标题按常见分隔符拆段，返回可读短语（中文标题的轻量分词替代）"""
        out: list[str] = []
        for seg in self._TITLE_SPLIT_RE.split(title):
            seg = seg.strip(" 　.。!！?？\"'“”…")
            if self._is_meaningful_topic(seg):
                out.append(seg)
        return out

    @staticmethod
    def _guess_topic_category(topic: str) -> str:
        """粗分类（仅存储用；界面已不暴露分类选择）"""
        lowered = topic.lower()
        if any(k in lowered for k in ("ai", "gpt", "llm", "ml", "模型", "智能")):
            return "ai"
        return "custom"


# 全局单例
recommendation_service = RecommendationService()
