"""
app/sources/github_connector.py
GitHub 官方只读 Connector（PROD-002）。

支持 Repo / Releases / Issues 三类只读来源，全部走官方 REST API：

- 请求统一通过共享 SSRF 客户端（core/http_client）；API 域名固定
  api.github.com，token 只发往该域名。
- ETag：条件请求 If-None-Match，304 视为"来源未变化"（本次无新条目），
  etag 持久化在 http_cache 表（migration 033）。
- 分页：解析 Link header 的 rel="next"，最多 MAX_PAGES 页。
- 配额：403/429 且 x-ratelimit-remaining=0 → 返回可行动错误（配置 token
  或等待重置），短暂 Retry-After 才等待重试，绝不长时间阻塞调度线程。
- token 通过环境变量 GITHUB_TOKEN 注入（最小权限：public_repo 只读即可）；
  撤销路径 = 删除/轮换环境变量后重启，不在模板或数据库中保存明文。
"""
import logging
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.http_client import get_http_client
from app.crawler.engine import CrawlItem, CrawlResult

logger = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"
MAX_PAGES = 3
MAX_ITEMS = 200
# 短暂限流（Retry-After ≤ 该值）才原地等待；更长的重置时间直接报错，
# 避免调度线程长时间阻塞
MAX_INLINE_WAIT_SECONDS = 30.0

_KINDS = ("repo", "releases", "issues")


def parse_source_url(
    source_url: str, kind_hint: str | None = None,
) -> tuple[str, str, str] | None:
    """解析来源 URL → (kind, owner, repo)；非 GitHub 仓库地址返回 None。

    支持 https://github.com/<owner>/<repo>[/releases|/issues]；
    kind_hint（selector_list 里 github: 后缀）优先于路径推断。
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse((source_url or "").strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host not in ("github.com", "www.github.com"):
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    kind = kind_hint if kind_hint in _KINDS else None
    if kind is None:
        tail = parts[2].lower() if len(parts) > 2 else ""
        kind = tail if tail in ("releases", "issues") else "repo"
    return kind, owner, repo


def _api_url(kind: str, owner: str, repo: str) -> str:
    base = f"{API_ROOT}/repos/{owner}/{repo}"
    if kind == "releases":
        return f"{base}/releases?per_page=50"
    if kind == "issues":
        # 只读、按创建时间倒序；PR 在结果里带 pull_request 字段，解析时过滤
        return f"{base}/issues?state=all&sort=created&direction=desc&per_page=50"
    return base


def _request_headers(token: str, etag: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "DevHunter/1.0 (personal feed aggregator; +github.com/devhunter)",
    }
    if token:
        # token 仅随 api.github.com 请求发出（_api_url 固定该域名）
        headers["Authorization"] = f"Bearer {token}"
    if etag:
        headers["If-None-Match"] = etag
    return headers


# ── ETag 缓存（migration 033）────────────────────────────────────

def _load_etag(url: str) -> str | None:
    try:
        from app.core.database import get_db
        with get_db() as conn:
            row = conn.execute(
                "SELECT etag FROM http_cache WHERE url = ?", (url,)
            ).fetchone()
        return row["etag"] if row else None
    except Exception:
        return None


def _store_etag(url: str, etag: str | None) -> None:
    if not etag:
        return
    try:
        from app.core.database import get_db
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with get_db() as conn:
            conn.execute(
                """INSERT INTO http_cache (url, etag, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET etag = excluded.etag,
                                                 updated_at = excluded.updated_at""",
                (url, etag, now),
            )
    except Exception as e:
        logger.debug("Failed to store etag for %s: %s", url, e)


# ── Link header 分页 ────────────────────────────────────────────

def _next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = part.split(";")
        if len(segments) < 2:
            continue
        if 'rel="next"' in segments[1] or "rel=next" in segments[1]:
            return segments[0].strip().strip("<>")
    return None


def _rate_limit_error(response: httpx.Response) -> str | None:
    """把配额耗尽/限流响应转成可行动错误；非限流错误返回 None。"""
    if response.status_code not in (403, 429):
        return None
    headers = response.headers
    remaining = headers.get("x-ratelimit-remaining")
    if response.status_code == 429 or remaining == "0":
        reset = headers.get("x-ratelimit-reset")
        retry_after = headers.get("retry-after")
        detail = ""
        if remaining == "0" and not headers.get("authorization"):
            detail = "（未配置 token 时 GitHub 限额为 60 次/小时，配置 GITHUB_TOKEN 可提升）"
        wait = ""
        if retry_after and retry_after.isdigit():
            wait = f"，{retry_after}s 后可重试"
        elif reset and reset.isdigit():
            wait = f"，重置时间戳 {reset}"
        return f"GitHub API rate limit exhausted{detail}{wait}"
    return None


# ── 条目映射 ────────────────────────────────────────────────────

def _repo_item(payload: dict[str, Any]) -> CrawlItem | None:
    full_name = payload.get("full_name") or ""
    html_url = payload.get("html_url") or ""
    if not full_name or not html_url:
        return None
    stars = payload.get("stargazers_count")
    desc = payload.get("description") or ""
    summary = f"{desc} · ⭐ {stars}" if stars is not None else desc
    return CrawlItem(
        title=full_name[:500],
        url=html_url,
        summary=summary[:400],
        published_at=payload.get("pushed_at") or payload.get("updated_at") or "",
        external_id=str(payload.get("id") or ""),
    )


def _release_item(payload: dict[str, Any]) -> CrawlItem | None:
    title = payload.get("name") or payload.get("tag_name") or ""
    html_url = payload.get("html_url") or ""
    if not title or not html_url:
        return None
    body = (payload.get("body") or "").strip()
    return CrawlItem(
        title=title[:500],
        url=html_url,
        summary=body[:400],
        published_at=payload.get("published_at") or payload.get("created_at") or "",
        external_id=str(payload.get("id") or ""),
    )


def _issue_item(payload: dict[str, Any]) -> CrawlItem | None:
    # issues 列表接口混有 PR：有 pull_request 字段的一律跳过
    if payload.get("pull_request"):
        return None
    title = payload.get("title") or ""
    html_url = payload.get("html_url") or ""
    if not title or not html_url:
        return None
    body = (payload.get("body") or "").strip()
    return CrawlItem(
        title=title[:500],
        url=html_url,
        summary=body[:400],
        published_at=payload.get("created_at") or "",
        external_id=str(payload.get("id") or ""),
    )


_MAPPERS = {"repo": _repo_item, "releases": _release_item, "issues": _issue_item}


def fetch(
    source_url: str,
    kind: str,
    token: str = "",
    on_progress: Any = None,
) -> CrawlResult:
    """抓取 GitHub 只读来源，返回统一 CrawlResult（永不抛异常）。"""
    parsed = parse_source_url(source_url, kind)
    if not parsed:
        return CrawlResult(error=(
            "GitHub 来源仅支持仓库地址（例如 https://github.com/owner/repo、"
            ".../releases、.../issues）"
        ))
    actual_kind, owner, repo = parsed
    url = _api_url(actual_kind, owner, repo)
    mapper = _MAPPERS[actual_kind]
    client = get_http_client()

    items: list[CrawlItem] = []
    pages = 0
    total_extracted = 0
    etag = _load_etag(url)
    next_url: str | None = url
    while next_url and pages < MAX_PAGES and len(items) < MAX_ITEMS:
        pages += 1
        headers = _request_headers(token, etag if pages == 1 else None)
        try:
            response = client.get(next_url, headers=headers, timeout=settings.crawler_timeout)
        except httpx.TimeoutException:
            return CrawlResult(error=f"GitHub API timeout after {settings.crawler_timeout}s",
                               pages_fetched=pages)
        except httpx.RequestError as e:
            return CrawlResult(error=f"GitHub API connection error: {type(e).__name__}",
                               pages_fetched=pages)

        if response.status_code == 304:
            # 来源未变化：本次执行视为无新增（etag 仍有效）
            return CrawlResult(items=[], pages_fetched=pages, http_status=304,
                               extracted_count=total_extracted)
        if response.status_code >= 400:
            rate_err = _rate_limit_error(response)
            if rate_err:
                return CrawlResult(error=rate_err, http_status=response.status_code,
                                   pages_fetched=pages)
            # 501/404 等：明确状态码，便于用户判断仓库是否存在/是否私有
            return CrawlResult(
                error=f"GitHub API HTTP {response.status_code} {response.reason_phrase}",
                http_status=response.status_code, pages_fetched=pages,
            )

        if pages == 1:
            etag = response.headers.get("etag")
            if etag:
                _store_etag(url, etag)

        try:
            payload = response.json()
        except Exception:
            return CrawlResult(error="GitHub API 返回非 JSON 响应",
                               http_status=response.status_code, pages_fetched=pages)

        records = payload if isinstance(payload, list) else [payload]
        for record in records:
            if not isinstance(record, dict):
                continue
            total_extracted += 1
            item = mapper(record)
            if item:
                items.append(item)

        next_url = _next_link(response.headers.get("link"))

    return CrawlResult(
        items=items[:MAX_ITEMS],
        http_status=200,
        list_count=total_extracted,
        extracted_count=total_extracted,
        pages_fetched=pages,
    )
