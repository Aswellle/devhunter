"""
tests/test_recommendation/test_scoring_semantics.py
推荐打分语义回归：

1. 新鲜度必须连续衰减——旧实现 24 小时内恒为 1.0，导致同批条目分数
   完全并列（推荐分全是同一个数字），且解释徽章"刚刚发布"会挂到
   20 小时前的条目上，与时间戳矛盾。
2. 探索因子必须真实存在——旧"探索发现"模式只是把四项权重整体调低，
   既无探索因子也无探索行为。
3. 总分必须是归一化加权平均——各模式权重之和不同，直接求和会让切换
   模式时全部条目分数整体缩放（并可能被最低分阈值整批过滤掉）。
"""
import pytest

from app.api.user_prefs import _MODE_WEIGHTS
from app.recommendation.explanations import explanation_generator
from app.services.recommendation_service import recommendation_service

svc = recommendation_service


def _details(**overrides):
    """构造一条 item 的打分明细（默认无任何个性化信号）。"""
    item = {"id": "i1", "title": "t", "summary": "", "task_id": "task-1",
            "task_name": "Hacker News", "fetched_at": "2026-01-01T00:00:00Z"}
    kwargs = dict(
        item=item,
        topic_tokens_map={},
        affinity_map={},
        task_affinities={},
        platform_affinities={},
        config={
            "topic_match_weight": 0.35,
            "affinity_weight": 0.30,
            "recency_weight": 0.20,
            "engagement_weight": 0.10,
            "exploration_weight": 0.05,
        },
        engagement_stats_map={},
    )
    kwargs.update(overrides)
    return svc._compute_item_score_details(**kwargs)


# ── 新鲜度：连续衰减 ─────────────────────────────────────────────

class TestRecencyDecay:
    def test_zero_age_is_full_score(self):
        assert svc._calc_recency_score(0) == 1.0

    def test_half_life_is_24h(self):
        assert svc._calc_recency_score(24) == pytest.approx(0.5, abs=1e-6)

    def test_decays_smoothly_within_a_day(self):
        """回归：24h 内必须随年龄递减，而不是恒为 1.0 全并列。"""
        hour1 = svc._calc_recency_score(1)
        hour12 = svc._calc_recency_score(12)
        hour23 = svc._calc_recency_score(23)
        assert hour1 > hour12 > hour23, "一天内的新旧差异必须体现在分数里"
        assert hour23 < 0.6, "23 小时前不应仍是满新鲜度"

    def test_monotonic_and_bounded(self):
        values = [svc._calc_recency_score(h) for h in range(0, 200, 5)]
        assert values == sorted(values, reverse=True)
        assert all(0.0 <= v <= 1.0 for v in values)

    def test_unparseable_age_scores_zero(self):
        assert svc._calc_recency_score(999.0) == 0.0


# ── 解释徽章与真实年龄一致 ───────────────────────────────────────

class TestRecencyReasonConsistency:
    def test_within_an_hour_says_just_published(self):
        reasons = explanation_generator.generate({}, {"recency_hours": 0.3}, {})
        labels = [r["label"] for r in reasons if r["type"] == "recency"]
        assert labels == ["刚刚发布"]

    def test_five_hours_says_today_not_just_published(self):
        """回归：5 小时前绝不能再声称"刚刚发布"（与"5 小时前"时间戳冲突）。"""
        reasons = explanation_generator.generate({}, {"recency_hours": 5.0}, {})
        labels = [r["label"] for r in reasons if r["type"] == "recency"]
        assert labels == ["今日发布"]

    def test_older_than_a_day_has_no_recency_badge(self):
        reasons = explanation_generator.generate({}, {"recency_hours": 30.0}, {})
        assert not [r for r in reasons if r["type"] == "recency"]

    def test_fallback_without_hours_makes_no_time_claim(self):
        reasons = explanation_generator.generate({}, {"recency_score": 0.9}, {})
        labels = [r["label"] for r in reasons if r["type"] == "recency"]
        assert labels == ["新鲜内容"], "无精确年龄时不得断言任何时间"


# ── 探索因子 ───────────────────────────────────────────────────

class TestExplorationFactor:
    def test_no_footprint_scores_zero(self):
        assert svc._calc_exploration_score("t1", "HN", {}, {}) == 0.0

    def test_unknown_source_is_maximally_novel(self):
        score = svc._calc_exploration_score("t1", "HN", {"other-task": 0.5}, {"V2EX": 0.4})
        assert score == 1.0

    def test_familiar_platform_reduces_novelty(self):
        score = svc._calc_exploration_score("t1", "HN", {}, {"HN": 0.6})
        assert score == pytest.approx(0.4, abs=1e-6)

    def test_exploration_reaches_score_details(self):
        _, details = _details(
            task_affinities={}, platform_affinities={"Hacker News": 0.2},
        )
        assert "exploration_score" in details
        assert details["exploration_score"] == pytest.approx(0.8, abs=1e-6)
        assert details["exploration_contribution"] > 0

    def test_exploration_badge_requires_real_contribution(self):
        """低探索权重下不应把每个陌生来源都标成"探索新领域"。"""
        reasons = explanation_generator.generate(
            {}, {"exploration_score": 1.0, "exploration_contribution": 0.01}, {},
        )
        assert not [r for r in reasons if r["type"] == "exploration"]

        reasons = explanation_generator.generate(
            {}, {"exploration_score": 1.0, "exploration_contribution": 0.30}, {},
        )
        assert [r for r in reasons if r["type"] == "exploration"]


# ── 归一化加权平均 ─────────────────────────────────────────────

class TestScoreNormalization:
    def _config_from(self, preset: dict[str, float]) -> dict:
        return {
            "topic_match_weight": preset["topic_match"],
            "affinity_weight": preset["affinity"],
            "recency_weight": preset["recency"],
            "engagement_weight": preset["engagement"],
            "exploration_weight": preset["exploration"],
        }

    def test_all_presets_sum_to_one(self):
        for name, preset in _MODE_WEIGHTS.items():
            total = sum(preset.values())
            assert abs(total - 1.0) < 1e-9, f"{name} 预设权重之和应为 1.0，实际 {total}"

    def test_score_is_weighted_mean_under_every_mode(self):
        """总分必须等于五因子的加权平均（分母是权重和，不是常数 1）。"""
        item = {
            "id": "i1", "title": "gpt", "summary": "", "task_id": "t1",
            "task_name": "HN", "fetched_at": "2026-01-01T00:00:00Z",
        }
        for name, preset in _MODE_WEIGHTS.items():
            total, details = svc._compute_item_score_details(
                item=item,
                topic_tokens_map={"gpt": 1.0},
                affinity_map={},
                task_affinities={"t1": 1.0},
                platform_affinities={"HN": 1.0},
                config=self._config_from(preset),
                engagement_stats_map={"i1": {"view_count": 5, "avg_dwell_seconds": 60}},
            )
            factors = {
                "topic_match": details["preference_score"],
                "affinity": details["affinity_score"],
                "recency": details["recency_score"],
                "engagement": details["engagement_score"],
                "exploration": details["exploration_score"],
            }
            weights = self._config_from(preset)
            expected = sum(
                weights[f"{k}_weight"] * v for k, v in factors.items()
            ) / sum(weights.values())
            assert total == pytest.approx(expected, abs=1e-9), name
            assert 0.0 <= total <= 1.0

    def test_zero_weights_do_not_divide_by_zero(self):
        total, _ = _details(
            config={
                "topic_match_weight": 0.0, "affinity_weight": 0.0,
                "recency_weight": 0.0, "engagement_weight": 0.0,
                "exploration_weight": 0.0,
            },
        )
        assert total == 0.0
