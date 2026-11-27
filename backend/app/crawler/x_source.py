"""
app/crawler/x_source.py
X（推特）公开时间线适配器。

X 的官方 API 需要付费 Bearer Token，且搜索接口不开放匿名访问。为了让
自托管实例无需任何登录/密钥即可接入 X，本适配器使用 X 的公开嵌入时间线
（syndication.twitter.com）：页面是 Next.js HTML，推文数据在
`__NEXT_DATA__.props.pageProps.timeline.entries[].content.tweet` 中。

能力与边界：
- 仅支持**账号时间线**（https://x.com/<账号>），不支持搜索/列表；
  需要更多主题时，可复制模板并把 URL 换成其他公开账号
- 只取最近一页（约 20~40 条），过滤转推与回复，保留原推
- 受 X 嵌入接口限流（约 30 次/窗口），模板推荐每小时抓取一次
- 推文链接统一使用 https://x.com/<账号>/status/<id>，external_id 取推文 ID
"""
from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

# 单次解析上限：账号时间线接口有时返回近百条（如 BBC 中文），
# 只取最近的 N 条，避免一次任务写入过多历史内容
MAX_X_POSTS = 40

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)
_TWITTER_DATE_RE = re.compile(
    r"^[A-Z][a-z]{2} ([A-Z][a-z]{2}) (\d{2}) (\d{2}):(\d{2}):(\d{2}) "
    r"([+-])(\d{2})(\d{2}) (\d{4})$"
)
_TCO_RE = re.compile(r"https?://t\.co/\w+")
_SCREEN_NAME_RE = re.compile(r"/screen-name/([A-Za-z0-9_]{1,30})")
_HANDLE_RE = re.compile(r"^@?([A-Za-z0-9_]{1,30})$")
_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

_X_PROFILE_HOSTS = {
    "x.com", "www.x.com", "mobile.x.com",
    "twitter.com", "www.twitter.com", "mobile.twitter.com",
}
_X_SYNDICATION_HOSTS = {"syndication.twitter.com", "cdn.syndication.twimg.com"}
# 不是账号主页的保留路径：避免把 x.com/search 当成账号 "search"
_X_RESERVED_PATHS = {
    "i", "home", "explore", "search", "settings", "notifications",
    "messages", "compose", "login", "logout", "signup", "tos", "privacy",
}


def normalize_x_source_url(url: str) -> str | None:
    """
    把用户填写的 X 账号主页 URL 归一为公开嵌入时间线地址。

    - https://x.com/BBCWorld        → syndication 时间线（showReplies=false）
    - https://twitter.com/BBCWorld  → 同上
    - 已是 syndication 地址          → 原样返回
    - 推文详情/搜索/列表等          → None（X 模式只支持账号时间线）
    """
    parsed = urlparse((url or "").strip())
    host = (parsed.netloc or "").lower().split(":")[0]
    if not host:
        return None

    if host in _X_SYNDICATION_HOSTS:
        return url

    if host in _X_PROFILE_HOSTS:
        path = parsed.path.strip("/")
        if not path or "/" in path:
            return None
        handle = path.lstrip("@")
        if handle.lower() in _X_RESERVED_PATHS:
            return None
        m = _HANDLE_RE.match(handle)
        if not m:
            return None
        screen_name = m.group(1)
        return (
            "https://syndication.twitter.com/srv/timeline-profile/"
            f"screen-name/{screen_name}?showReplies=false"
        )

    return None


def extract_screen_name(url: str) -> str:
    """从 syndication 或 x.com URL 中提取账号名（用于兜底构造推文链接）。"""
    m = _SCREEN_NAME_RE.search(url or "")
    if m:
        return m.group(1)
    parsed = urlparse(url or "")
    path = parsed.path.strip("/")
    if path and "/" not in path:
        return path.lstrip("@")
    return ""


def _parse_twitter_datetime(value: Any) -> datetime | None:
    """解析 X 的 'Wed Nov 25 17:00:00 +0000 2026' 或 ISO 时间。"""
    if not value:
        return None
    text = str(value).strip()

    iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso_text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass

    m = _TWITTER_DATE_RE.match(text)
    if not m:
        return None
    month_name, day, hour, minute, second, sign, off_h, off_m, year = m.groups()
    month = _MONTHS.get(month_name)
    if not month:
        return None
    offset_minutes = int(off_h) * 60 + int(off_m)
    if sign == "-":
        offset_minutes = -offset_minutes
    try:
        parsed = datetime(
            int(year), month, int(day), int(hour), int(minute), int(second),
            tzinfo=timezone(timedelta(minutes=offset_minutes)),
        )
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc)


def _format_count(value: Any) -> str:
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _clean_tweet_text(tweet: dict[str, Any]) -> str:
    """
    清理推文正文：反转义 HTML、展开短链、移除媒体占位链接，
    并给纯媒体推文补一个人工可读标记。
    """
    text = str(tweet.get("full_text") or tweet.get("text") or "")
    text = html_lib.unescape(text)

    entities = tweet.get("entities") or {}
    media = entities.get("media") or []
    media_types = {str(m.get("type") or "") for m in media if isinstance(m, dict)}

    # 短链展开为 display_url（比 expanded_url 短，适合标题展示）
    for entity in entities.get("urls") or []:
        if not isinstance(entity, dict):
            continue
        short = str(entity.get("url") or "")
        expanded = str(entity.get("display_url") or entity.get("expanded_url") or "")
        if short and expanded:
            text = text.replace(short, expanded)

    # 媒体 t.co 占位链接从正文移除，末尾统一加标记
    for media_item in media:
        if isinstance(media_item, dict):
            short = str(media_item.get("url") or "")
            if short:
                text = text.replace(short, "")

    text = _TCO_RE.sub("", text)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = re.sub(r"\s+", " ", text).strip()

    if media_types:
        marker = " [视频]" if media_types & {"video", "animated_gif"} else " [图片]"
        text = f"{text}{marker}".strip()

    if not text and media_types:
        text = "视频动态" if media_types & {"video", "animated_gif"} else "图片动态"

    return text[:480]


def _build_summary(tweet: dict[str, Any], screen_name: str) -> str:
    """生成摘要：作者、原发时间、互动量、引用内容；用于展示与聚合特征。"""
    parts = [f"@{screen_name}"]
    published = _parse_twitter_datetime(tweet.get("created_at"))
    if published:
        parts.append(published.strftime("%Y-%m-%d %H:%M UTC"))
    parts.append(
        f"{_format_count(tweet.get('favorite_count'))} 赞 · "
        f"{_format_count(tweet.get('retweet_count'))} 转发 · "
        f"{_format_count(tweet.get('reply_count'))} 回复"
    )
    quoted = tweet.get("quoted_status") or {}
    if isinstance(quoted, dict) and quoted:
        quoted_text = _clean_tweet_text(quoted)[:80]
        if quoted_text:
            parts.append(f"引用：{quoted_text}")
    lang = str(tweet.get("lang") or "").strip()
    if lang:
        parts.append(lang.upper())
    return " · ".join(parts)[:400]


def parse_x_timeline(html_text: str, base_url: str) -> tuple[list[dict[str, Any]], int]:
    """
    解析 syndication 页面中的账号时间线。

    Returns: (posts, raw_count)
      posts: [{title, url, summary, external_id, published_at}, ...]
      raw_count: 页面中 tweet 条目总数（含被过滤的转推/回复）
    """
    match = _NEXT_DATA_RE.search(html_text or "")
    if not match:
        return [], 0

    try:
        data = json.loads(match.group(1))
    except (TypeError, ValueError):
        return [], 0

    page_props = (data.get("props") or {}).get("pageProps") or {}
    timeline = page_props.get("timeline") or {}
    entries = timeline.get("entries") or []
    if not isinstance(entries, list):
        return [], 0

    fallback_screen_name = extract_screen_name(base_url)
    posts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    raw_count = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        tweet = ((entry.get("content") or {}).get("tweet")) or {}
        if not isinstance(tweet, dict) or not tweet:
            continue
        raw_count += 1

        # 转推与回复会让同一条内容重复出现/割裂线程，账号时间线只留原推
        if tweet.get("retweeted_status") or tweet.get("in_reply_to_status_id_str"):
            continue

        tweet_id = str(tweet.get("id_str") or tweet.get("id") or "").strip()
        if not tweet_id or tweet_id in seen_ids:
            continue

        text = _clean_tweet_text(tweet)
        if not text:
            continue

        user = tweet.get("user") or {}
        screen_name = str(user.get("screen_name") or fallback_screen_name or "i")
        published = _parse_twitter_datetime(tweet.get("created_at"))

        posts.append({
            "title": text,
            "url": f"https://x.com/{screen_name}/status/{tweet_id}",
            "summary": _build_summary(tweet, screen_name),
            "external_id": tweet_id,
            "published_at": published.strftime("%Y-%m-%dT%H:%M:%SZ") if published else "",
        })
        seen_ids.add(tweet_id)

        if len(posts) >= MAX_X_POSTS:
            break

    return posts, raw_count
