"""
tests/test_threads/test_stats.py
Thread 聚合画像（build_thread_stats）单元测试——纯函数，无 DB、无 I/O
"""
from datetime import datetime, timedelta, timezone

from app.threads.stats import build_thread_stats, confidence_label, parse_iso_utc

NOW = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


def _hours_ago(hours: float) -> str:
    return (NOW - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _thread(first_seen_at: str, last_seen_at: str) -> dict:
    return {"first_seen_at": first_seen_at, "last_seen_at": last_seen_at}


class TestConfidenceLabel:
    """置信度标签边界"""

    def test_none_when_no_data(self):
        """无数据 → None"""
        assert confidence_label(None) is None

    def test_high_boundary(self):
        """≥0.70 → high"""
        assert confidence_label(0.70) == "high"
        assert confidence_label(0.95) == "high"

    def test_medium_boundary(self):
        """0.45 ≤ x < 0.70 → medium"""
        assert confidence_label(0.45) == "medium"
        assert confidence_label(0.6999) == "medium"

    def test_low(self):
        """<0.45 → low"""
        assert confidence_label(0.44) == "low"


class TestParseIsoUtc:
    """时间解析兼容性"""

    def test_z_suffix(self):
        """尾缀 Z 的 UTC 时间"""
        dt = parse_iso_utc("2026-10-07T12:00:00Z")
        assert dt is not None and dt.tzinfo is not None

    def test_naive_gets_utc(self):
        """无时区按 UTC 处理"""
        dt = parse_iso_utc("2026-10-07T12:00:00")
        assert dt is not None and dt.utcoffset().total_seconds() == 0

    def test_invalid_returns_none(self):
        """非法输入 → None 不抛异常"""
        assert parse_iso_utc("not-a-date") is None
        assert parse_iso_utc(None) is None
        assert parse_iso_utc("") is None


class TestBuildThreadStats:
    """聚合画像构建"""

    def test_basic_multi_platform(self):
        """多平台多条目：规模、活跃度、平台分布"""
        items = [
            {"id": "a", "task_name": "Hacker News", "fetched_at": _hours_ago(30),
             "similarity": 1.0, "match_reason": "initial_item"},
            {"id": "b", "task_name": "V2EX", "fetched_at": _hours_ago(20),
             "similarity": 0.8, "match_reason": "lexical_match"},
            {"id": "c", "task_name": "V2EX", "fetched_at": _hours_ago(2),
             "similarity": 0.6, "match_reason": "semantic_match"},
            {"id": "d", "task_name": "GitHub", "fetched_at": _hours_ago(1),
             "similarity": 0.7, "match_reason": "entity_match"},
        ]
        stats = build_thread_stats(
            _thread(_hours_ago(30), _hours_ago(1)), items, now=NOW
        )

        assert stats["item_count"] == 4
        assert stats["platform_count"] == 3
        assert stats["is_cross_platform"] is True
        # 分布按条目数倒序
        assert stats["platform_breakdown"][0] == {"platform": "V2EX", "count": 2}
        # 近 24h = b(20h 前? 否, 20>24? 否 → 在 24h 内) c d = 3 条；近 6h = c d
        assert stats["recent_24h_count"] == 3
        assert stats["recent_6h_count"] == 2
        # 置信度只统计非种子条目
        assert stats["matched_item_count"] == 3
        assert stats["similarity_avg"] == round((0.8 + 0.6 + 0.7) / 3, 4)
        assert stats["similarity_max"] == 0.8
        assert stats["confidence"] == "high"

    def test_seed_excluded_from_confidence(self):
        """种子条目（similarity=1.0, initial_item）不计入置信度"""
        items = [
            {"id": "a", "task_name": "HN", "fetched_at": _hours_ago(10),
             "similarity": 1.0, "match_reason": "initial_item"},
            {"id": "b", "task_name": "HN", "fetched_at": _hours_ago(5),
             "similarity": 0.5, "match_reason": "lexical_match"},
        ]
        stats = build_thread_stats(_thread(_hours_ago(10), _hours_ago(5)), items, now=NOW)
        assert stats["similarity_avg"] == 0.5
        assert stats["confidence"] == "medium"

    def test_legacy_data_fallback_earliest_is_seed(self):
        """017 之前的旧数据无 match_reason：最早条目视为种子"""
        items = [
            {"id": "old", "task_name": "HN", "fetched_at": _hours_ago(48),
             "similarity": 1.0, "match_reason": None},
            {"id": "new", "task_name": "HN", "fetched_at": _hours_ago(1),
             "similarity": 0.6, "match_reason": None},
        ]
        stats = build_thread_stats(_thread(_hours_ago(48), _hours_ago(1)), items, now=NOW)
        assert stats["matched_item_count"] == 1
        assert stats["similarity_avg"] == 0.6

    def test_single_item_thread(self):
        """单条目 Thread：无置信度数据，返回 None 而非误导性 100%"""
        items = [
            {"id": "a", "task_name": "HN", "fetched_at": _hours_ago(1),
             "similarity": 1.0, "match_reason": "initial_item"},
        ]
        stats = build_thread_stats(_thread(_hours_ago(1), _hours_ago(1)), items, now=NOW)
        assert stats["item_count"] == 1
        assert stats["matched_item_count"] == 0
        assert stats["similarity_avg"] is None
        assert stats["similarity_max"] is None
        assert stats["confidence"] is None
        assert stats["is_cross_platform"] is False

    def test_empty_items(self):
        """空条目列表（孤儿 Thread）也能得到合法结构"""
        stats = build_thread_stats(_thread(_hours_ago(5), _hours_ago(5)), [], now=NOW)
        assert stats["item_count"] == 0
        assert stats["platform_count"] == 0
        assert stats["platform_breakdown"] == []
        assert stats["confidence"] is None

    def test_span_hours(self):
        """时间跨度按小时计"""
        stats = build_thread_stats(_thread(_hours_ago(48), _hours_ago(2)), [], now=NOW)
        assert stats["span_hours"] == 46.0

    def test_unknown_platform_counted(self):
        """task_name 缺失归入 unknown 而非崩溃"""
        items = [
            {"id": "a", "fetched_at": _hours_ago(1), "similarity": 1.0,
             "match_reason": "initial_item"},
        ]
        stats = build_thread_stats(_thread(_hours_ago(1), _hours_ago(1)), items, now=NOW)
        assert stats["platform_breakdown"] == [{"platform": "unknown", "count": 1}]
        assert stats["platform_count"] == 1

    def test_bad_timestamps_do_not_crash(self):
        """非法时间字符串不崩溃，对应计数归零"""
        items = [
            {"id": "a", "task_name": "HN", "fetched_at": "garbage",
             "similarity": 1.0, "match_reason": "initial_item"},
        ]
        stats = build_thread_stats(
            _thread("bad", "also-bad"), items, now=NOW
        )
        assert stats["recent_24h_count"] == 0
        assert stats["span_hours"] is None
