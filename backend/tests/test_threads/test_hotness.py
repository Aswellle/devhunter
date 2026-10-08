"""
tests/test_threads/test_hotness.py
Thread 热度模型单元测试——纯函数，无 DB、无 I/O
"""
from datetime import datetime, timedelta, timezone

from app.threads.hotness import compute_hotness, hotness_map_from_rows, momentum_map_from_rows

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


class TestMomentumMapFromRows:
    """热度趋势：当前热度 vs 24h 前时点热度"""

    def test_new_thread_is_all_rise(self):
        """24h 前还不存在（latest_at_cutoff 全空）→ previous=0，delta=hotness"""
        rows = [("th1", "taskA", _ago(2), None)]
        m = momentum_map_from_rows(rows, window_hours=24, now=NOW)
        assert m["th1"]["previous"] == 0.0
        assert m["th1"]["delta"] == m["th1"]["hotness"]
        assert m["th1"]["hotness"] > 0.9

    def test_decaying_thread_has_negative_delta(self):
        """最近 24h 无新报道：存量热度自然衰减，delta 为负"""
        # 30h 前的条目：cutoff（24h 前）时年龄 6h → 2^(-0.25)≈0.84；现在 2^(-1.25)≈0.42
        rows = [("th1", "taskA", _ago(30), _ago(30))]
        m = momentum_map_from_rows(rows, window_hours=24, now=NOW)
        assert m["th1"]["hotness"] < m["th1"]["previous"]
        assert m["th1"]["delta"] < -0.3

    def test_rising_thread_with_history(self):
        """cutoff 前有旧报道、cutoff 后又进了新报道：热度上升"""
        rows = [
            ("th1", "taskA", _ago(1), _ago(40)),   # 新报道 + 历史
            ("th1", "taskB", _ago(2), None),        # 新加入的平台
        ]
        m = momentum_map_from_rows(rows, window_hours=24, now=NOW)
        assert m["th1"]["delta"] > 0.5
        assert 0 < m["th1"]["previous"] < m["th1"]["hotness"]

    def test_platform_without_history_contributes_zero_previous(self):
        """cutoff 后才有条目的平台不参与 previous 计算"""
        rows = [("th1", "taskA", _ago(3), None)]
        m = momentum_map_from_rows(rows, window_hours=24, now=NOW)
        assert m["th1"]["previous"] == 0.0

    def test_groups_by_thread_and_empty(self):
        """多 Thread 各自成组；空行集返回空映射"""
        rows = [
            ("th1", "taskA", _ago(2), None),
            ("th2", "taskA", _ago(30), _ago(30)),
        ]
        m = momentum_map_from_rows(rows, window_hours=24, now=NOW)
        assert set(m) == {"th1", "th2"}
        assert m["th1"]["delta"] > 0 > m["th2"]["delta"]
        assert momentum_map_from_rows([], window_hours=24, now=NOW) == {}
