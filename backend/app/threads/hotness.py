"""
app/threads/hotness.py
Thread 热度模型（借鉴 AIHOT 的热度口径，本地化为派生指标）。

定义：
    hotness = Σ_平台 2^(-该平台最新条目年龄 / 24h)

- 唯一来源计数：同一平台（task）的多条报道只按其最新一条计一次——
  同源刷屏不放大热度，跨平台共识才放大
- 半衰期：热度随时间每 24 小时减半
- 窗口：平台最新条目超过 48 小时不再贡献（热度自然归零）
- 值域 [0, 平台数]，纯派生数据（读取时计算，不落库）

纯函数、无 I/O；时间统一由 parse 传入，便于测试注入。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

HALF_LIFE_HOURS = 24.0
WINDOW_HOURS = 48.0


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_hotness(
    platform_latest: dict[str, str | None],
    now: datetime | None = None,
) -> float:
    """
    计算单个 Thread 的热度。

    Args:
        platform_latest: {平台键: 该平台最新条目的 ISO 时间}（平台键可用
            task_id 或 task_name，只要同一 Thread 内口径一致）
        now: 当前时间（可注入以便测试），默认 UTC now

    Returns:
        热度值（float，保留 4 位小数）。无有效数据返回 0.0。
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=WINDOW_HOURS)
    total = 0.0
    for latest in platform_latest.values():
        dt = _parse_iso(latest)
        if dt is None or dt < cutoff:
            continue
        age_hours = max(0.0, (now - dt).total_seconds() / 3600.0)
        total += 2.0 ** (-age_hours / HALF_LIFE_HOURS)
    return round(total, 4)


def hotness_map_from_rows(
    rows: list[Any],
    now: datetime | None = None,
) -> dict[str, float]:
    """
    从 (thread_id, platform_key, latest_iso) 行集构建 {thread_id: hotness}。

    thread_repo.get_hotness_aggregates 的 SQL 结果直接喂给本函数；
    若同一 (thread, platform) 出现多行（不应发生，防御处理），保留最新一条。
    """
    grouped: dict[str, dict[str, str | None]] = {}
    for thread_id, platform_key, latest in rows:
        tid = str(thread_id)
        key = str(platform_key)
        existing = grouped.setdefault(tid, {}).get(key)
        if existing is None or (_parse_iso(latest) or datetime.min.replace(tzinfo=timezone.utc)) > (
            _parse_iso(existing) or datetime.min.replace(tzinfo=timezone.utc)
        ):
            grouped[tid][key] = latest
    return {tid: compute_hotness(platforms, now=now) for tid, platforms in grouped.items()}
