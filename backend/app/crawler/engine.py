"""
app/crawler/engine.py
核心抓取引擎：HTTP fetch + HTML/JSON/RSS 解析 + 关键词过滤

支持三种解析模式（通过 selectors['list'] 前缀自动识别）：
  html       : CSS Selector 解析（默认，无前缀）
  json:      : JSON API GET 解析，selector_list = "json:<dot_path>"
  json-post: : JSON API POST 解析，selector_list = "json-post:<path>|||<body_json>"
  rss:       : RSS 2.0 / Atom feed 解析，selector_list = "rss:"

链接字段支持 PREF:prefix|path 语法：自动拼接前缀 + JSON 路径值。
永远不向调用方抛异常，错误通过 CrawlResult.error 字段传递。
"""
import json as _json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin

import chardet
import httpx
from bs4 import BeautifulSoup

import ipaddress
from urllib.parse import urlparse

from app.core.config import settings
from app.core.http_client import get_http_client
from app.utils.url import compute_url_hash

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = settings.crawler_max_response_mb * 1024 * 1024
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2
MAX_PAGES = 10
ProgressCallback = Callable[[str, str, dict], None]


@dataclass
class CrawlItem:
    title: str
    url: str
    summary: str = ""
    url_hash: str = ""


@dataclass
class CrawlResult:
    items: list[CrawlItem] = field(default_factory=list)
    error: str | None = None
    html_size_kb: float = 0.0
    http_status: int = 0
    list_count: int = 0
    extracted_count: int = 0
    filtered_count: int = 0
    fetch_ms: int = 0
    retries_used: int = 0
    pages_fetched: int = 1

    @property
    def success(self) -> bool:
        return self.error is None


# ─── SSRF Protection ─────────────────────────────────────────────────────────

# Reserved/private IP ranges that should be blocked
_PRIVATE_IP_BLOCKS = [
    ipaddress.ip_network("10.0.0.0/8"),       # Class A private
    ipaddress.ip_network("172.16.0.0/12"),     # Class B private
    ipaddress.ip_network("192.168.0.0/16"),    # Class C private
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local (including 169.254.169.254)
    ipaddress.ip_network("0.0.0.0/8"),         # Current network
    ipaddress.ip_network("100.64.0.0/10"),    # Carrier-grade NAT
    ipaddress.ip_network("192.0.0.0/24"),    # IETF Protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),    # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),   # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),     # Multicast
    ipaddress.ip_network("240.0.0.0/4"),     # Reserved
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    ipaddress.ip_network("::1/128"),          # Loopback (IPv6)
    ipaddress.ip_network("fc00::/7"),         # Unique local (IPv6)
    ipaddress.ip_network("fe80::/10"),        # Link-local (IPv6)
]


def _is_ssrf_safe_url(url: str) -> tuple[bool, str]:
    """
    Check if a URL is safe from SSRF attacks.
    Returns (is_safe, error_message).
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"不支持的协议: {parsed.scheme}，仅允许 http/https"

        hostname = parsed.hostname
        if not hostname:
            return False, "无法解析的主机名"

        hostname_lower = hostname.lower()
        # Block cloud metadata endpoints
        if hostname_lower == "metadata.google.internal":
            return False, "禁止访问云元数据端点 (metadata.google.internal)"
        if hostname_lower == "169.254.169.254":
            return False, "禁止访问云元数据地址 (169.254.169.254)"
        if hostname_lower.startswith("metadata."):
            return False, f"禁止访问云元数据端点 ({hostname_lower})"

        # Try to resolve hostname to IP(s)
        import socket
        # C1: DNS resolution failure must fail CLOSED (block), not open.
        # Previously any getaddrinfo error (including a transient DNS blip)
        # returned (True, "") — i.e. "safe" — permissively allowing requests
        # that should have been blocked. Resolution errors are now caught by
        # the outer except below and also treated as unsafe.
        addr_info = socket.getaddrinfo(hostname_lower, None)
        if not addr_info:
            return False, "无法解析主机名对应的 IP 地址"

        for family, _, _, _, sockaddr in addr_info:
            if family == socket.AF_INET:
                ip_str = sockaddr[0]
                ip = ipaddress.ip_address(ip_str)
            elif family == socket.AF_INET6:
                ip_str = sockaddr[0]
                ip = ipaddress.ip_address(ip_str)
            else:
                continue

            # Check against private/reserved blocks
            for block in _PRIVATE_IP_BLOCKS:
                if ip in block:
                    return False, f"禁止访问私有/保留 IP 地址: {ip_str}"

        return True, ""

    except Exception as e:
        # C1: fail closed — a malformed URL or DNS resolution error must
        # block the request rather than silently letting it through.
        logger.debug("SSRF check error, blocking as unsafe: %s", e)
        return False, f"URL 安全校验失败: {e}"


# ─── Mode Detection ────────────────────────────────────────────────────────────

def _parse_mode(selector_list: str) -> tuple[str, str, dict]:
    """
    Detect fetch+parse mode from selector_list prefix.
    Returns (mode, list_path, extra).
    """
    sl = selector_list or ""
    if sl.startswith("json-post:"):
        rest = sl[10:]
        parts = rest.split("|||", 1)
        list_path = parts[0].strip()
        post_body: dict = {}
        if len(parts) > 1:
            try:
                post_body = _json.loads(parts[1])
            except Exception:
                pass
        return "json-post", list_path, {"post_body": post_body}

    if sl.startswith("json:"):
        return "json", sl[5:].strip(), {}

    if sl.startswith("rss:"):
        return "rss", "", {}

    # Default: HTML mode
    return "html", sl, {}


# ─── JSON Helpers ──────────────────────────────────────────────────────────────

def _get_nested(obj, path: str):
    """Traverse dict/list with dot-notation path. Empty/$ path returns obj."""
    if not path or path == "$":
        return obj
    for key in path.split("."):
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list):
            try:
                obj = obj[int(key)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return obj


def _resolve_link(item: dict, selector_link: str, base_url: str) -> str:
    """
    Resolve URL from JSON item.
    Supports "PREF:https://example.com/|json.path" to prepend a URL prefix.
    """
    if selector_link.startswith("PREF:"):
        rest = selector_link[5:]
        parts = rest.split("|", 1)
        prefix = parts[0]
        path   = parts[1] if len(parts) > 1 else ""
        val = _get_nested(item, path)
        return prefix + str(val) if val else ""

    val = _get_nested(item, selector_link)
    if not val:
        return ""
    val = str(val).strip()
    if not val:
        return ""
    if val.startswith("http"):
        return val
    return urljoin(base_url, val)


def _parse_json_items(
    data, list_path: str, selectors: dict, base_url: str
) -> tuple[list[CrawlItem], int]:
    """Parse JSON data into CrawlItem list. Returns (items, raw_count)."""
    items_data = _get_nested(data, list_path)
    if items_data is None:
        items_data = data
    if isinstance(items_data, dict):
        items_data = [items_data]
    if not isinstance(items_data, list):
        return [], 0

    raw_count    = len(items_data)
    title_path   = selectors.get("title") or "title"
    link_sel     = selectors.get("link")  or "url"
    summary_path = selectors.get("summary")

    parsed: list[CrawlItem] = []
    for item in items_data:
        if not isinstance(item, dict):
            continue
        title = _get_nested(item, title_path)
        if not title:
            continue
        title = str(title).strip()
        if not title:
            continue

        link = _resolve_link(item, link_sel, base_url)
        if not link or not link.startswith("http"):
            continue

        summary = ""
        if summary_path:
            s = _get_nested(item, summary_path)
            if s:
                # Trim very long JSON text fields
                summary = str(s).strip()[:400]

        parsed.append(CrawlItem(title=title, url=link, summary=summary))

    return parsed, raw_count


# ─── RSS/Atom Helpers ──────────────────────────────────────────────────────────

def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _parse_rss_items(xml_text: str, base_url: str) -> tuple[list[CrawlItem], int]:
    """Parse RSS 2.0 or Atom feed. Returns (items, raw_count)."""
    # Strip namespace declarations so ElementTree parses without ns prefixes
    xml_clean = re.sub(r'\s+xmlns(?::[a-zA-Z0-9]+)?="[^"]*"', "", xml_text)
    # Also strip namespace prefixes from element names (e.g. <atom:title> -> <title>)
    # This handles feeds that use prefixed namespace elements
    xml_clean = re.sub(r'<(\/?)([a-zA-Z0-9]+):([a-zA-Z0-9]+)', r'<\1\3', xml_clean)
    # Remove problematic processing instructions
    xml_clean = re.sub(r"<\?[^?]+\?>", "", xml_clean, count=5)

    try:
        root = ET.fromstring(xml_clean.encode("utf-8", errors="replace"))
    except ET.ParseError as exc:
        logger.warning("RSS/Atom parse error: %s", exc)
        return [], 0

    root_tag = root.tag.split("}")[-1].lower()
    items: list[CrawlItem] = []

    if root_tag == "feed":
        # Atom
        for entry in root.iter("entry"):
            title_el = entry.find("title")
            title = (title_el.text or "").strip() if title_el is not None else ""

            link = ""
            for lel in entry.findall("link"):
                rel  = lel.get("rel", "alternate")
                href = lel.get("href", "")
                if rel == "alternate" or not link:
                    link = href

            summary_el = entry.find("summary")
            if summary_el is None:
                summary_el = entry.find("content")
            summary = ""
            if summary_el is not None and summary_el.text:
                summary = _strip_html_tags(summary_el.text)[:200]

            if title and link:
                items.append(CrawlItem(title=title, url=link, summary=summary))
    else:
        # RSS 2.0 (root = <rss> or <rdf:RDF>)
        for item_el in root.iter("item"):
            title_el = item_el.find("title")
            link_el  = item_el.find("link")
            desc_el  = item_el.find("description")
            # Also check content:encoded which many feeds use instead of description
            if desc_el is None:
                desc_el = item_el.find("encoded")
            guid_el  = item_el.find("guid")

            title = (title_el.text or "").strip() if title_el is not None else ""

            link = ""
            if link_el is not None:
                link = (link_el.text or "").strip()
            if not link and guid_el is not None:
                g = (guid_el.text or "").strip()
                if g.startswith("http"):
                    link = g

            summary = ""
            if desc_el is not None and desc_el.text:
                summary = _strip_html_tags(desc_el.text)[:200]

            if title and link:
                items.append(CrawlItem(title=title, url=link, summary=summary))

    return items, len(items)


# ─── Site-specific Headers ─────────────────────────────────────────────────────

def _get_extra_headers(url: str) -> dict:
    """
    Return site-specific request headers for anti-bot bypass and API compliance.
    Each site's requirements based on their documented or known API specs.
    """
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()

    # Reddit API: requires a non-browser, descriptive User-Agent
    if "reddit.com" in domain:
        return {
            "User-Agent": "DevHunter/1.0 (personal feed aggregator; +github.com/devhunter)",
            "Accept": "application/json",
        }

    # Juejin API: requires referer + origin for CORS
    if "juejin.cn" in domain:
        return {
            "referer":     "https://juejin.cn/",
            "origin":      "https://juejin.cn",
            "x-juejin-aid": "2608",
            "x-juejin-uid": "",
        }

    # Dev.to API: expects JSON accept
    if "dev.to" in domain:
        return {
            "Accept":    "application/json",
            "api-key":   "",        # Public API, no key needed
        }

    # V2EX API: no auth needed, add accept
    if "v2ex.com" in domain:
        return {
            "Accept":   "application/json",
            "Referer":  "https://www.v2ex.com/",
        }

    # Hacker News RSS: standard browser headers
    if "ycombinator.com" in domain:
        return {
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }

    # IndieHackers: RSS accept
    if "indiehackers.com" in domain:
        return {
            "Accept": "application/rss+xml, application/atom+xml, text/xml, */*",
        }

    # sspai: requires a proper User-Agent and Accept header
    if "sspai.com" in domain:
        return {
            "Accept": "application/rss+xml, application/atom+xml, text/xml, */*",
            "User-Agent": "Mozilla/5.0 (compatible; DevHunter/1.0; +https://github.com/devhunter)",
        }

    return {}


# ─── Progress Callback Helper ──────────────────────────────────────────────────

def _emit(cb: ProgressCallback | None, event_type: str, message: str,
          data: dict | None = None) -> None:
    if cb is None:
        return
    try:
        cb(event_type, message, data or {})
    except Exception:
        pass


# ─── Retry Wrapper ─────────────────────────────────────────────────────────────

@dataclass
class _FetchOutcome:
    response: httpx.Response | None = None
    retries_used: int = 0
    error: str | None = None
    http_status: int = 0


def _fetch_page_with_retry(
    client: httpx.Client,
    url: str,
    mode: str,
    mode_extra: dict,
    extra_headers: dict,
    timeout: float,
    on_progress: ProgressCallback | None,
) -> _FetchOutcome:
    """
    Fetch one page with a fixed 3-attempt / 2s-delay retry loop.

    Retryable: httpx.TimeoutException, httpx.RequestError (network), HTTP 5xx.
    Terminal (no retry): HTTP 4xx. SSRF is checked by the caller BEFORE this
    function is invoked, so a blocked URL never reaches here.

    retries_used = number of *extra* attempts beyond the first (0..MAX_RETRY_ATTEMPTS-1).
    Never raises; on exhaustion returns an outcome with error set.
    """
    post_body = mode_extra.get("post_body", {})
    last_error = ""
    last_status = 0
    attempt = 0

    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            if mode == "json-post":
                response = client.post(
                    url,
                    json=post_body,
                    headers={**extra_headers, "Content-Type": "application/json"},
                    timeout=timeout,
                )
            else:
                response = client.get(url, headers=extra_headers, timeout=timeout)

            # C1: redirects are followed manually so each hop's Location URL
            # can be re-validated against the SSRF blocklist. The shared
            # httpx.Client has follow_redirects=False for exactly this reason.
            redirect_hops = 0
            while getattr(response, "is_redirect", False) and redirect_hops < 5:
                location = response.headers.get("location")
                if not location:
                    break
                next_url = str(httpx.URL(location, base=response.url))
                ssrf_safe, ssrf_msg = _is_ssrf_safe_url(next_url)
                if not ssrf_safe:
                    return _FetchOutcome(
                        response=None,
                        retries_used=attempt - 1,
                        error=f"SSRF blocked on redirect: {ssrf_msg}",
                        http_status=response.status_code,
                    )
                redirect_hops += 1
                if mode == "json-post":
                    response = client.post(
                        next_url, json=post_body,
                        headers={**extra_headers, "Content-Type": "application/json"},
                        timeout=timeout,
                    )
                else:
                    response = client.get(next_url, headers=extra_headers, timeout=timeout)

            response.raise_for_status()
            return _FetchOutcome(
                response=response,
                retries_used=attempt - 1,
                error=None,
                http_status=response.status_code,
            )
        except httpx.TimeoutException:
            last_error = f"Timeout after {timeout}s"
            _emit(on_progress, "fetch_error", f"连接超时（>{timeout}s）", {"attempt": attempt})
        except httpx.RequestError as e:
            last_error = f"Connection error: {type(e).__name__}: {e}"
            _emit(on_progress, "fetch_error", f"网络错误: {type(e).__name__}", {"attempt": attempt})
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            last_status = status
            last_error = f"HTTP {status} {e.response.reason_phrase}"
            _emit(on_progress, "fetch_error", last_error, {"status": status, "attempt": attempt})
            if 400 <= status < 500:
                # 4xx is terminal; do not retry. Use a plain HTTP message so
                # operators can distinguish a one-shot 4xx from retry exhaustion.
                return _FetchOutcome(
                    response=None,
                    retries_used=attempt - 1,
                    error=last_error,
                    http_status=status,
                )
            # 5xx falls through to the retry delay below
        except Exception as e:
            last_error = f"Unknown error: {type(e).__name__}: {e}"
            _emit(on_progress, "fetch_error", f"未知错误: {type(e).__name__}", {"attempt": attempt})

        if attempt < MAX_RETRY_ATTEMPTS:
            time.sleep(RETRY_DELAY_SECONDS)

    return _FetchOutcome(
        response=None,
        retries_used=attempt - 1,
        error=f"failed after {attempt} attempt(s), last error: {last_error}",
        http_status=last_status,
    )


# ─── Main Entry Point ──────────────────────────────────────────────────────────

def fetch_and_parse(
    url: str,
    selectors: dict[str, str | None],
    keywords: list[str],
    timeout: float | None = None,
    on_progress: ProgressCallback | None = None,
) -> CrawlResult:
    """
    主入口：拉取 URL → 按模式解析 → 关键词过滤 → 返回 CrawlResult。

    解析模式由 selectors['list'] 前缀决定：
      无前缀         → HTML + CSS Selector（默认）
      json:<path>   → JSON API GET，path 为列表的 dot-notation 路径
      json-post:<path>|||<body> → JSON API POST
      rss:           → RSS 2.0 / Atom 解析

    title/link/summary 字段在 JSON 模式下为 dot-notation 路径；
    link 字段支持 PREF:<prefix>|<path> 语法拼接 URL 前缀。

    分页：selectors['next_page'] 存在时（CSS selector 或 json: 路径），
    引擎会跟随下一页链接最多 MAX_PAGES 页（HTML/json/json-post 模式）。
    RSS 模式忽略 next_page，只抓一页。每页通过 _fetch_page_with_retry
    获得 3×2s 重试保护。永不抛异常，错误经 CrawlResult.error 传递。
    """
    _timeout = timeout or settings.crawler_timeout
    client = get_http_client()

    # ── 检测模式 ─────────────────────────────────────────
    selector_list = selectors.get("list") or ""
    mode, list_path, mode_extra = _parse_mode(selector_list)

    # ── 初始 URL 的 SSRF 安全检查 ────────────────────────
    ssrf_safe, ssrf_msg = _is_ssrf_safe_url(url)
    if not ssrf_safe:
        _emit(on_progress, "fetch_error", f"SSRF 防护已拦截: {ssrf_msg}")
        return CrawlResult(error=f"SSRF blocked: {ssrf_msg}")

    next_page_selector = selectors.get("next_page")
    # RSS 不支持分页：忽略 next_page selector，只抓一页
    if mode == "rss":
        next_page_selector = None

    return _paginate(
        client=client,
        start_url=url,
        mode=mode,
        list_path=list_path,
        mode_extra=mode_extra,
        selectors=selectors,
        keywords=keywords,
        next_page_selector=next_page_selector,
        timeout=_timeout,
        on_progress=on_progress,
    )


# ─── Single-page parser ───────────────────────────────────────────────────────

def _parse_one_page(
    response: httpx.Response,
    mode: str,
    list_path: str,
    selectors: dict[str, str | None],
    base_url: str,
    on_progress: ProgressCallback | None,
    parse_start: float,
) -> tuple[list[CrawlItem], int, object | None]:
    """
    Parse one fetched response by mode. Returns (parsed_items, raw_count, anchor)
    where `anchor` is the parsed document handle for next-page extraction:
      - HTML mode: the BeautifulSoup root (`soup`)
      - json/json-post mode: the decoded JSON `data`
      - rss mode: None (no pagination)
    Never raises; parse errors return ([], 0, None) and emit a parse_error event.
    """
    content = response.content
    if len(content) > MAX_RESPONSE_BYTES:
        logger.warning("Response too large (%d bytes), truncating: %s", len(content), base_url)
        content = content[:MAX_RESPONSE_BYTES]

    if mode in ("json", "json-post"):
        try:
            # C2: parse from the already-truncated `content` bytes, not
            # response.json() — the latter re-reads response.content directly
            # and bypasses the MAX_RESPONSE_BYTES truncation done above,
            # letting an oversized response be fully parsed anyway.
            data = _json.loads(content)
        except Exception as exc:
            err = f"JSON 解析失败: {exc}"
            _emit(on_progress, "parse_error", err)
            return [], 0, None

        json_selectors = {
            "title":   selectors.get("title") or "title",
            "link":    selectors.get("link")  or "url",
            "summary": selectors.get("summary"),
        }
        parsed, raw_count = _parse_json_items(data, list_path, json_selectors, base_url)
        parse_ms = int((time.time() - parse_start) * 1000)
        if raw_count == 0:
            _emit(on_progress, "parse_done", "JSON 返回空数组，请检查 API 地址",
                  {"list_count": 0})
        else:
            _emit(on_progress, "parse_done",
                  f"JSON 解析完成：{raw_count} 项 → 提取 {len(parsed)} 条",
                  {"list_count": raw_count, "extracted": len(parsed), "parse_ms": parse_ms})
        return parsed, raw_count, data

    if mode == "rss":
        encoding = response.encoding
        if not encoding or encoding.lower() in ("", "utf-8", "utf8"):
            detected = chardet.detect(content)
            encoding = detected.get("encoding") or "utf-8"
        try:
            xml_text = content.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            xml_text = content.decode("utf-8", errors="replace")

        parsed, raw_count = _parse_rss_items(xml_text, base_url)
        parse_ms = int((time.time() - parse_start) * 1000)
        if not parsed:
            _emit(on_progress, "parse_done",
                  "RSS 解析完成但未找到条目，请检查 Feed URL", {"list_count": 0})
        else:
            _emit(on_progress, "parse_done",
                  f"RSS 解析完成：{len(parsed)} 条",
                  {"list_count": raw_count, "extracted": len(parsed), "parse_ms": parse_ms})
        return parsed, raw_count, None

    # ──── HTML 解析 ──────────────────────────────────
    encoding = response.encoding
    if not encoding or encoding.lower() in ("", "utf-8", "utf8"):
        detected = chardet.detect(content)
        encoding = detected.get("encoding") or "utf-8"
    try:
        html = content.decode(encoding, errors="replace")
    except (LookupError, UnicodeDecodeError):
        html = content.decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")
    if not list_path:
        err = "selector_list 为空"
        _emit(on_progress, "parse_error", err)
        return [], 0, soup

    # C3: soup.select can raise (e.g. cssselect.SelectorSyntaxError) on a
    # malformed selector; this function's contract is "never raises", so
    # an invalid list_path must degrade to an empty result + parse_error
    # event, matching the pattern already used in _resolve_next_page_url.
    try:
        list_items = soup.select(list_path)
    except Exception as exc:
        err = f"Selector 语法错误: {exc}"
        _emit(on_progress, "parse_error", err)
        return [], 0, soup
    if not list_items:
        _emit(on_progress, "parse_done",
              f"Selector「{list_path[:40]}」匹配到 0 个元素，可能页面结构已变更",
              {"list_count": 0})
        logger.info("Selector matched 0 items on %s (selector: %s)", base_url, list_path)
        return [], 0, soup

    title_sel = selectors.get("title", "")
    link_sel = selectors.get("link", "")
    summary_sel = selectors.get("summary")
    parsed: list[CrawlItem] = []

    for el in list_items:
        title_el = el.select_one(title_sel) if title_sel else None
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        link_el = el.select_one(link_sel) if link_sel else None
        if not link_el:
            continue
        raw_href = link_el.get("href", "")
        if not raw_href:
            raw_href = title_el.get("href", "") if title_el else ""
        if not raw_href:
            continue
        abs_url = urljoin(base_url, str(raw_href))

        summary = ""
        if summary_sel:
            summary_el = el.select_one(summary_sel)
            summary = summary_el.get_text(strip=True) if summary_el else ""

        parsed.append(CrawlItem(title=title, url=abs_url, summary=summary))

    parse_ms = int((time.time() - parse_start) * 1000)
    _emit(on_progress, "parse_done",
          f"找到 {len(list_items)} 个列表项，提取 {len(parsed)} 条有效数据",
          {"list_count": len(list_items), "extracted": len(parsed), "parse_ms": parse_ms})
    return parsed, len(list_items), soup


def _resolve_next_page_url(
    anchor: object | None,
    mode: str,
    next_page_selector: str | None,
    page_url: str,
) -> str:
    """
    Resolve the next-page URL from the current page's parsed anchor.
    Returns "" if there is no next page.
    - HTML mode: soup.select_one(next_page_selector) → href → urljoin.
    - json/json-post: _get_nested(data, path) → urljoin if relative.
    """
    if not next_page_selector:
        return ""

    if mode in ("json", "json-post"):
        if not isinstance(anchor, dict):
            return ""
        path = next_page_selector
        if path.startswith("json:"):
            path = path[5:].strip()
        val = _get_nested(anchor, path)
        if not val:
            return ""
        val = str(val).strip()
        if not val:
            return ""
        if val.startswith("http"):
            return val
        return urljoin(page_url, val)

    if mode == "html":
        if anchor is None:
            return ""
        soup: BeautifulSoup = anchor  # type: ignore[assignment]
        try:
            el = soup.select_one(next_page_selector)
        except Exception:
            return ""
        if el is None:
            return ""
        href = el.get("href", "") if hasattr(el, "get") else ""
        if not href:
            return ""
        return urljoin(page_url, str(href))

    return ""


# ─── Pagination orchestrator ──────────────────────────────────────────────────

def _paginate(
    client: httpx.Client,
    start_url: str,
    mode: str,
    list_path: str,
    mode_extra: dict,
    selectors: dict[str, str | None],
    keywords: list[str],
    next_page_selector: str | None,
    timeout: float,
    on_progress: ProgressCallback | None,
) -> CrawlResult:
    """
    Multi-page crawl orchestrator. Fetches up to MAX_PAGES pages, each via
    _fetch_page_with_retry (3×2s). Stops on: empty next selector, page cap,
    or consecutive duplicate url_hash set (loop guard on filtered items).

    Aggregation (per-page filter, summed across pages):
      - items = merged filtered list across all pages
      - extracted_count / filtered_count / list_count = sums across pages
      - html_size_kb / fetch_ms = sums across pages
      - retries_used = max retries used on any single page
      - pages_fetched = number of pages attempted (incl. the failure page)
    """
    all_items: list[CrawlItem] = []
    total_list_count = 0
    total_extracted = 0
    total_filtered = 0
    total_html_size_kb = 0.0
    total_fetch_ms = 0
    max_retries_used = 0
    last_http_status = 0
    seen_hashes: set[str] | None = None
    page_url = start_url
    page_num = 0

    # extra_headers computed once from the start URL; assumes pagination stays
    # within the same domain/cookie scope (edge case: cross-domain next-page
    # links would need per-page header recomputation — not handled now).
    extra_headers = _get_extra_headers(start_url)

    for page_num in range(1, MAX_PAGES + 1):
        # ── SSRF check per resolved next-page URL ──────────
        ssrf_safe, ssrf_msg = _is_ssrf_safe_url(page_url)
        if not ssrf_safe:
            _emit(on_progress, "fetch_error", f"SSRF 防护已拦截: {ssrf_msg}")
            return CrawlResult(
                error=f"SSRF blocked: {ssrf_msg}",
                pages_fetched=page_num, retries_used=max_retries_used,
            )

        _emit(on_progress, "fetch_connecting",
              f"正在连接 {page_url[:70]}… [{mode.upper()}] 第 {page_num} 页")
        fetch_start = time.time()

        outcome = _fetch_page_with_retry(
            client, page_url, mode, mode_extra, extra_headers, timeout, on_progress,
        )
        page_fetch_ms = int((time.time() - fetch_start) * 1000)
        total_fetch_ms += page_fetch_ms
        max_retries_used = max(max_retries_used, outcome.retries_used)

        if outcome.error:
            # Retry exhaustion or terminal 4xx: whole crawl fails, no partial save.
            return CrawlResult(
                error=outcome.error,
                http_status=outcome.http_status,
                html_size_kb=round(total_html_size_kb, 1),
                fetch_ms=total_fetch_ms,
                retries_used=max_retries_used,
                pages_fetched=page_num,
            )

        response = outcome.response
        assert response is not None  # outcome.error is None ⇒ response set
        last_http_status = response.status_code

        # response body size (truncate)
        content = response.content
        if len(content) > MAX_RESPONSE_BYTES:
            logger.warning("Response too large (%d bytes), truncating: %s", len(content), page_url)
            content = content[:MAX_RESPONSE_BYTES]
        size_kb = round(len(content) / 1024, 1)
        total_html_size_kb += size_kb
        _emit(on_progress, "fetch_done",
              f"HTTP {response.status_code} · {size_kb}KB · {page_fetch_ms}ms",
              {"status": response.status_code, "size_kb": size_kb,
               "fetch_ms": page_fetch_ms, "mode": mode, "page": page_num})

        # ── parse current page ─────────────────────────────
        _emit(on_progress, "parse_start", f"解析内容（{mode.upper()} 模式）第 {page_num} 页…")
        parse_start = time.time()
        parsed, raw_count, anchor = _parse_one_page(
            response, mode, list_path, selectors, page_url, on_progress, parse_start,
        )
        total_list_count += raw_count
        total_extracted += len(parsed)

        # parse_error (e.g. JSON 解析失败 / selector_list 为空) → terminal
        if not parsed and raw_count == 0 and list_path:
            # Distinguish "parse produced nothing" from genuine empty list.
            # _parse_one_page emits parse_error for real errors; here we just
            # treat empty as a valid (warning-level) page and continue/stop.
            pass

        # C5: snapshot pre-filter URLs for the loop guard below — the guard
        # must detect a duplicate/looping PAGE (same page served twice),
        # not "this page's keyword filter happened to reject everything
        # twice in a row" (which would falsely look identical to an empty
        # set on the previous page and abort pagination early).
        pre_filter_hashes = {compute_url_hash(item.url) for item in parsed}

        # ── keyword filter (per page) ──────────────────────
        before_filter = len(parsed)
        if keywords:
            kw_lower = [k.lower().strip() for k in keywords if k.strip()]
            if kw_lower:
                _emit(on_progress, "filter_start",
                      f'关键词过滤：{", ".join(kw_lower[:4])}{"…" if len(kw_lower) > 4 else ""}',
                      {"keywords": kw_lower, "page": page_num})
                parsed = [
                    item for item in parsed
                    if any(
                        kw in item.title.lower() or kw in item.summary.lower()
                        for kw in kw_lower
                    )
                ]
                _emit(on_progress, "filter_done",
                      f"过滤完成：{len(parsed)}/{before_filter} 条命中关键词",
                      {"before": before_filter, "after": len(parsed), "page": page_num})
        else:
            _emit(on_progress, "filter_skip",
                  f"未设置关键词，全量保留 {len(parsed)} 条（第 {page_num} 页）")

        total_filtered += len(parsed)

        # ── emit page_fetched (per-page diagnostic SSE) ────
        _emit(on_progress, "page_fetched",
              f"第 {page_num} 页抓取完成，{len(parsed)} 条",
              {"page": page_num, "count": len(parsed), "retries_used": outcome.retries_used})

        # ── loop guard: exact url_hash set of RAW (pre-filter) items ─
        current_hashes = pre_filter_hashes
        if seen_hashes is not None and current_hashes == seen_hashes:
            _emit(on_progress, "page_fetched",
                  f"检测到第 {page_num} 页与上一页条目重复，停止分页",
                  {"page": page_num, "loop_guard": True})
            break
        seen_hashes = current_hashes
        all_items.extend(parsed)

        # ── resolve next page ───────────────────────────────
        if not next_page_selector:
            break  # no pagination configured
        next_url = _resolve_next_page_url(anchor, mode, next_page_selector, page_url)
        if not next_url or next_url == page_url:
            break  # empty selector match or self-loop
        page_url = next_url

    logger.info("Crawled %s [%s]: %d pages, %d items (keywords=%s)",
                start_url, mode, page_num, len(all_items), keywords or "none")

    return CrawlResult(
        items=all_items,
        html_size_kb=round(total_html_size_kb, 1),
        http_status=last_http_status,
        list_count=total_list_count,
        extracted_count=total_extracted,
        filtered_count=total_filtered,
        fetch_ms=total_fetch_ms,
        retries_used=max_retries_used,
        pages_fetched=page_num,
    )
