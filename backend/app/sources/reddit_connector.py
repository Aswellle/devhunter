"""
app/sources/reddit_connector.py
Reddit 官方 OAuth Connector（PROD-004）。

合规与数据用途边界（必须保留）：

- 只通过官方 OAuth（application-only / client_credentials）读取公开
  subreddit 列表；不抓 HTML/JSON 页面绕过访问控制。
- 用户须自行在 Reddit 创建应用并提供 REDDIT_CLIENT_ID /
  REDDIT_CLIENT_SECRET / REDDIT_USER_AGENT；凭据只经环境变量注入，
  不写入任务模板或数据库。
- 遵守官方速率限制：解析 x-ratelimit-* 头，429 按 Retry-After 有限等待，
  配额耗尽返回可行动错误而不长时间阻塞调度线程。
- 内容按 TTL 保留（REDDIT_ITEM_TTL_DAYS，默认 30 天，调度器每日清理）：
  删除同步采用 TTL + 来源整体清理策略，不做逐帖存在性轮询（成本高且易
  触发限流）；用户删除来源任务即按既有 cleanup 语义清空该来源条目。
- 数据用途限制：采集内容仅用于用户自托管的个人阅读/聚合；
  不得用于模型训练。若启用 LLM 摘要，仅发送被选中的公开帖子文本，
  且提示词必须把帖子内容视为不可信输入（与既有 LLM 契约一致）。
"""
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.core.http_client import get_http_client
from app.crawler.engine import CrawlItem, CrawlResult

logger = logging.getLogger(__name__)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_ROOT = "https://oauth.reddit.com"
MAX_INLINE_WAIT_SECONDS = 30.0
MAX_ITEMS = 100

# 进程内 token 缓存：{token: expiry_epoch}
_TOKEN_CACHE: dict[str, float] = {}
_TOKEN_LOCK = threading.Lock()


def parse_source_url(source_url: str) -> str | None:
    """从 reddit 链接解析 subreddit 名；非 /r/<sub> 返回 None。"""
    from urllib.parse import urlparse

    try:
        parsed = urlparse((source_url or "").strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host not in ("reddit.com", "www.reddit.com", "old.reddit.com"):
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0].lower() == "r":
        return parts[1]
    return None


def _get_token() -> tuple[str | None, str | None]:
    """获取 application-only OAuth token（带缓存）。返回 (token, error)。"""
    client_id = settings.reddit_client_id
    client_secret = settings.reddit_client_secret
    if not client_id or not client_secret:
        return None, (
            "Reddit OAuth 未配置：请设置 REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET"
            "（在 reddit.com/prefs/apps 创建应用），并配置 REDDIT_USER_AGENT"
        )

    with _TOKEN_LOCK:
        for token, expiry in list(_TOKEN_CACHE.items()):
            if expiry > time.time() + 30:
                return token, None
        try:
            response = get_http_client().post(
                TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(client_id, client_secret),
                headers={"User-Agent": settings.reddit_user_agent},
                timeout=settings.crawler_timeout,
            )
        except httpx.TimeoutException:
            return None, "Reddit OAuth token 请求超时"
        except httpx.RequestError as e:
            return None, f"Reddit OAuth 连接失败: {type(e).__name__}"

        if response.status_code >= 400:
            return None, (
                f"Reddit OAuth 认证失败（HTTP {response.status_code}）："
                "请检查 REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET"
            )
        try:
            payload = response.json()
        except Exception:
            return None, "Reddit OAuth 返回非 JSON 响应"
        token = payload.get("access_token")
        if not token:
            return None, "Reddit OAuth 响应缺少 access_token"
        _TOKEN_CACHE.clear()
        _TOKEN_CACHE[token] = time.time() + float(payload.get("expires_in") or 3600)
        return token, None


def _listing_url(subreddit: str, mode: str) -> str:
    sort = mode if mode in ("new", "hot", "top", "rising") else "new"
    return f"{API_ROOT}/r/{subreddit}/{sort}?limit={MAX_ITEMS}&raw_json=1"


def _published(created_utc: Any) -> str:
    try:
        ts = float(created_utc)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_item(data: dict[str, Any]) -> CrawlItem | None:
    if data.get("stickied"):
        return None
    title = (data.get("title") or "").strip()
    permalink = data.get("permalink") or ""
    if not title or not permalink:
        return None
    selftext = (data.get("selftext") or "").strip()
    subreddit = data.get("subreddit") or ""
    summary = f"r/{subreddit} · {selftext}" if subreddit else selftext
    return CrawlItem(
        title=title[:500],
        url=f"https://www.reddit.com{permalink}",
        summary=summary[:400],
        published_at=_published(data.get("created_utc")),
        external_id=str(data.get("id") or ""),
    )


def fetch(source_url: str, mode: str = "new", on_progress: Any = None) -> CrawlResult:
    """读取 subreddit 列表（官方 OAuth），返回统一 CrawlResult，永不抛异常。"""
    subreddit = parse_source_url(source_url)
    if not subreddit:
        return CrawlResult(error=(
            "Reddit 来源仅支持 subreddit 地址（例如 https://www.reddit.com/r/rust/）"
        ))

    token, err = _get_token()
    if err:
        return CrawlResult(error=err)

    url = _listing_url(subreddit, mode)
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": settings.reddit_user_agent,
        "Accept": "application/json",
    }
    try:
        response = get_http_client().get(
            url, headers=headers, params=None, timeout=settings.crawler_timeout,
        )
    except httpx.TimeoutException:
        return CrawlResult(error=f"Reddit API 超时（>{settings.crawler_timeout}s）")
    except httpx.RequestError as e:
        return CrawlResult(error=f"Reddit API 连接失败: {type(e).__name__}")

    if response.status_code == 429:
        retry_after = response.headers.get("retry-after") or ""
        wait = min(float(retry_after), MAX_INLINE_WAIT_SECONDS) if retry_after.replace(".", "", 1).isdigit() else 2.0
        time.sleep(wait)
        try:
            response = get_http_client().get(
                url, headers=headers, params=None, timeout=settings.crawler_timeout,
            )
        except (httpx.TimeoutException, httpx.RequestError):
            return CrawlResult(error="Reddit API 限流后重试失败")

    if response.status_code >= 400:
        if response.status_code in (403, 404):
            return CrawlResult(
                error=f"Reddit API HTTP {response.status_code}：subreddit 不可访问 "
                      "（不存在、私有或已被封禁）",
                http_status=response.status_code,
            )
        return CrawlResult(
            error=f"Reddit API HTTP {response.status_code} {response.reason_phrase}",
            http_status=response.status_code,
        )

    try:
        payload = response.json()
    except Exception:
        return CrawlResult(error="Reddit API 返回非 JSON 响应",
                           http_status=response.status_code)

    children = ((payload or {}).get("data") or {}).get("children") or []
    items: list[CrawlItem] = []
    for child in children:
        data = child.get("data") if isinstance(child, dict) else None
        if not isinstance(data, dict):
            continue
        item = _to_item(data)
        if item:
            items.append(item)

    return CrawlResult(
        items=items[:MAX_ITEMS],
        http_status=response.status_code,
        list_count=len(children),
        extracted_count=len(items),
    )
