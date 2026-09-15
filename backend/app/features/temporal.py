"""
app/features/temporal.py
Temporal Score：时间相似度计算。

同一事件通常具有时间窗口：
- Breaking news: 6~48h
- Product launch: 2~7d
- Open-source release: 3~14d
- Long-running topic: 7~30d

时间相似度评分：
0~6h     → 1.0
6~24h    → 0.8
24~72h   → 0.5
>72h     → 0.1
"""
from datetime import datetime, timezone
from typing import Any


def _parse_iso_date(iso_date: str) -> datetime | None:
    """解析 ISO 日期字符串"""
    if not iso_date:
        return None
    try:
        # 处理 Z 后缀
        if iso_date.endswith("Z"):
            iso_date = iso_date[:-1] + "+00:00"
        return datetime.fromisoformat(iso_date)
    except (ValueError, TypeError):
        return None


def _hours_between(date_a: datetime, date_b: datetime) -> float:
    """计算两个日期之间的小时数（绝对值）"""
    diff = abs((date_a - date_b).total_seconds())
    return diff / 3600


def temporal_score(
    date_a: str | None,
    date_b: str | None,
    event_window_hours: float = 24.0,
) -> float:
    """
    计算两个日期的时间相似度分数。

    Args:
        date_a: ISO 日期字符串
        date_b: ISO 日期字符串
        event_window_hours: 事件窗口（小时），默认 24h

    Returns:
        时间相似度分数 [0.0, 1.0]
    """
    if not date_a or not date_b:
        return 0.0

    dt_a = _parse_iso_date(date_a)
    dt_b = _parse_iso_date(date_b)

    if not dt_a or not dt_b:
        return 0.0

    hours = _hours_between(dt_a, dt_b)

    # 基于事件窗口的衰减
    if hours <= 6:
        return 1.0
    elif hours <= 24:
        return 0.8
    elif hours <= 72:
        return 0.5
    elif hours <= event_window_hours:
        return 0.3
    else:
        return 0.1


def temporal_score_from_hours(hours: float) -> float:
    """
    基于小时数计算时间相似度。

    Args:
        hours: 时间差（小时）

    Returns:
        时间相似度分数 [0.0, 1.0]
    """
    if hours <= 6:
        return 1.0
    elif hours <= 24:
        return 0.8
    elif hours <= 72:
        return 0.5
    else:
        return 0.1


def get_event_window_hours(event_type: str = "default") -> float:
    """
    获取事件类型的窗口（小时）。

    Args:
        event_type: 事件类型
            - breaking_news: 6~48h
            - product_launch: 2~7d (48~168h)
            - open_source_release: 3~14d (72~336h)
            - long_running_topic: 7~30d (168~720h)
            - default: 24h

    Returns:
        事件窗口（小时）
    """
    windows = {
        "breaking_news": 48.0,
        "product_launch": 168.0,  # 7d
        "open_source_release": 336.0,  # 14d
        "long_running_topic": 720.0,  # 30d
        "default": 24.0,
    }
    return windows.get(event_type, 24.0)


def detect_event_type(title: str, summary: str = "") -> str:
    """
    从标题和摘要中检测事件类型。

    Args:
        title: 标题
        summary: 摘要

    Returns:
        事件类型字符串
    """
    text = (title + " " + summary).lower()

    if any(kw in text for kw in ["breaking", "urgent", "alert", "快讯", "突发"]):
        return "breaking_news"
    if any(kw in text for kw in ["release", "launch", "announce", "发布", "推出", "上线"]):
        return "product_launch"
    if any(kw in text for kw in ["open source", "oss", "github", "开源"]):
        return "open_source_release"
    if any(kw in text for kw in ["trending", "popular", "热门", "趋势"]):
        return "long_running_topic"

    return "default"
