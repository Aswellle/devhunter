"""
tests/test_threads/test_hotness.py
Thread 热度模型单元测试——纯函数，无 DB、无 I/O
"""
from datetime import datetime, timedelta, timezone

from app.threads.hotness import compute_hotness, hotness_map_from_rows

NOW = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


def _ago(hours: float) -> str:
    return (NOW - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestComputeHotness:
    """热度计算"""

    def test_empty(self):
        """无数据 → 0"""
        assert compute_hotness({}, now=NOW) == 0.0

    def test_single_fresh_source(self):
        """单个刚更新的平台 → 1.0"""
        assert compute_hotness({"t1": _ago(0)}, now=NOW) == 1.0

    def test_half_life(self):
        """24 小时前的单平台 → 衰减到 0.5"""
        assert compute_hotness({"t1": _ago(24)}, now=NOW) == 0.5

    def test_window_cutoff(self):
        """48 小时窗口之外不贡献；窗口边缘按半衰期连续衰减"""
        assert compute_hotness({"t1": _ago(48.1)}, now=NOW) == 0.0
        # 47.9h ≈ 2^(-1.996) ≈ 0.25
        assert 0.24 < compute_hotness({"t1": _ago(47.9)}, now=NOW) < 0.26

    def test_per_source_dedup(self):
        """同一平台多条报道只计一次：同键重复行取最新，不叠加"""
        rows = [("th1", "taskA", _ago(2)), ("th1", "taskA", _ago(40))]
        m = hotness_map_from_rows(rows, now=NOW)
        assert m["th1"] == compute_hotness({"taskA": _ago(2)}, now=NOW)

    def test_cross_platform_sums(self):
        """跨平台共识叠加：两个平台各 0.5 → 1.0"""
        v = compute_hotness({"t1": _ago(24), "t2": _ago(24)}, now=NOW)
        assert v == 1.0

    def test_invalid_time_ignored(self):
        """非法时间不崩溃也不贡献"""
        assert compute_hotness({"t1": "garbage"}, now=NOW) == 0.0


class TestHotnessMapFromRows:
    """行集 → 映射"""

    def test_groups_by_thread(self):
        rows = [
            ("th1", "taskA", _ago(0)),
            ("th1", "taskB", _ago(24)),
            ("th2", "taskA", _ago(47)),
        ]
        m = hotness_map_from_rows(rows, now=NOW)
        # th1: 1.0 + 0.5；th2: 仅剩微弱残余
        assert abs(m["th1"] - 1.5) < 1e-6
        assert 0.2 < m["th2"] < 0.26

    def test_empty_rows(self):
        assert hotness_map_from_rows([], now=NOW) == {}
