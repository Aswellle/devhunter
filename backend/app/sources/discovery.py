"""
app/sources/discovery.py
URL Autodiscovery：自动发现 URL 的内容结构。

发现能力：
- URL 归一化（补全 scheme、IDN 编码、去 fragment）与有界多候选探测
  （www 变体、http 降级、站点根路径的常见 feed 路径）
- 识别 RSS/Atom feed（含从 HTML `<link rel="alternate">` 自动发现 feed）
- 识别 JSON API
- 查找文章列表
- 检测 pagination
- 分析 DOM 结构

失败分类体系（DiscoveryFailure）：对「技术上根本无法解析」的情况给出
机器可读编码 + 用户文案 + 行动提示，覆盖 DNS/连接/TLS/HTTP 状态/
反爬挑战/非网页内容/JS 渲染页/文章详情页等全部边界。
"""
import json as _json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from ..core.http_client import get_http_client
from ..core.ssrf import resolve_and_validate_url
from ..crawler.engine import MAX_REDIRECTS
from ..crawler.x_source import extract_screen_name, normalize_x_source_url

logger = logging.getLogger(__name__)


# ─── 失败分类体系 ─────────────────────────────────────────────────────────────

class FailureCode:
    """发现失败的机器可读编码：前端据此渲染分类提示"""
    INVALID_URL = "INVALID_URL"              # 无法解析的输入
    UNSUPPORTED_SCHEME = "UNSUPPORTED_SCHEME"  # 非 http(s) 协议
    SSRF_BLOCKED = "SSRF_BLOCKED"            # 内网/保留地址（安全策略，设计使然）
    DNS_NOT_FOUND = "DNS_NOT_FOUND"          # 域名不存在/拼写错误
    CONNECTION_FAILED = "CONNECTION_FAILED"  # 连接被拒/网络不可达
    TIMEOUT = "TIMEOUT"                      # 连接或响应超时
    TLS_ERROR = "TLS_ERROR"                  # 证书无效/握手失败
    REDIRECT_LIMIT = "REDIRECT_LIMIT"        # 重定向超过上限
    HTTP_NOT_FOUND = "HTTP_NOT_FOUND"        # 404/410
    AUTH_REQUIRED = "AUTH_REQUIRED"          # 401/403 需要登录或权限
    BLOCKED_BY_WAF = "BLOCKED_BY_WAF"        # 反爬挑战（Cloudflare 等）
    RATE_LIMITED = "RATE_LIMITED"            # 429
    SERVER_ERROR = "SERVER_ERROR"            # 5xx
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"  # 响应超过大小上限
    NOT_A_WEBPAGE = "NOT_A_WEBPAGE"          # 二进制内容（图片/PDF/音视频/压缩包）
    JS_RENDERED_PAGE = "JS_RENDERED_PAGE"    # 纯前端渲染（服务端无内容）
    NO_LIST_STRUCTURE = "NO_LIST_STRUCTURE"  # 可访问但不是列表页（如文章详情页）
    FETCH_FAILED = "FETCH_FAILED"            # 未归类的获取失败


@dataclass
class DiscoveryFailure:
    """一次发现尝试的结构化失败：编码 + 文案 + 行动提示 + 推荐改用 URL"""
    code: str
    message: str
    hint: str = ""
    url: str = ""
    suggested_url: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "url": self.url,
            "suggested_url": self.suggested_url,
        }


@dataclass
class DiscoveryResult:
    """发现结果"""
    url: str
    source_type: str = "unknown"  # rss | json | html | x
    title: str = ""
    description: str = ""
    feed_url: str = ""
    json_path: str = ""
    list_selector: str = ""
    title_selector: str = ""
    link_selector: str = ""
    summary_selector: str = ""
    next_page_selector: str = ""
    candidate_count: int = 0
    sample_items: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # 结构化失败（成功时为 None）；errors 同步携带人读文案以兼容旧消费方
    failure: DiscoveryFailure | None = None
    # 归一化与探测过程中实际请求过的 URL（探测透明度）
    tried_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "source_type": self.source_type,
            "title": self.title,
            "description": self.description,
            "feed_url": self.feed_url,
            "json_path": self.json_path,
            "list_selector": self.list_selector,
            "title_selector": self.title_selector,
            "link_selector": self.link_selector,
            "summary_selector": self.summary_selector,
            "next_page_selector": self.next_page_selector,
            "candidate_count": self.candidate_count,
            "sample_items": self.sample_items[:5],
            "errors": self.errors,
            "failure": self.failure.to_dict() if self.failure else None,
            "tried_urls": self.tried_urls,
        }


class URLDiscoverer:
    """URL 自动发现器"""

    # 站点根路径的常见 feed 路径（输入为站点根且主路径失败/无列表时探测）
    _FEED_PROBE_PATHS = ("/feed", "/rss", "/rss.xml", "/atom.xml", "/feed.xml", "/index.xml")
    # 探测请求的响应体上限：feed 分类只需响应头部内容
    _PROBE_MAX_BYTES = 256 * 1024

    # ── 归一化 ─────────────────────────────────────────────────

    def _normalize_url(self, raw: str) -> tuple[str, DiscoveryFailure | None]:
        """
        归一化用户输入：补全 https:// scheme、主机 IDNA 编码、去 fragment。

        返回 (normalized_url, None) 或 ("", failure)。
        """
        text = (raw or "").strip()
        if not text:
            return "", DiscoveryFailure(
                FailureCode.INVALID_URL,
                "请输入要发现的 URL",
                "支持输入站点根（如 example.com）、栏目页或 Feed 地址，scheme 可省略",
                url=raw,
            )
        # 容错：去内部空白与中文引号包裹
        text = text.strip("'\"“”").strip()
        if re.search(r"\s", text):
            return "", DiscoveryFailure(
                FailureCode.INVALID_URL,
                "URL 中含有空格，请检查是否粘贴完整",
                url=raw,
            )
        if "://" not in text:
            text = "https://" + text
        try:
            parts = urlsplit(text)
        except ValueError:
            return "", DiscoveryFailure(
                FailureCode.INVALID_URL,
                "URL 格式无法解析",
                url=raw,
            )
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https"):
            return "", DiscoveryFailure(
                FailureCode.UNSUPPORTED_SCHEME,
                f"不支持 {scheme or '空'} 协议——本系统只能聚合 http/https 网页内容",
                "浏览器专属协议（ftp/file/mailto 等）或本地文件无法作为数据源；"
                "请改为提供该站点的 http(s) 页面或 Feed 地址",
                url=raw,
            )
        host = (parts.hostname or "").lower()
        if not host:
            return "", DiscoveryFailure(
                FailureCode.INVALID_URL,
                "URL 缺少主机名，请检查格式",
                "完整格式如 https://example.com/feed",
                url=raw,
            )
        try:
            host_ascii = host.encode("idna").decode("ascii")
        except (UnicodeError, ValueError):
            return "", DiscoveryFailure(
                FailureCode.INVALID_URL,
                "域名无法编码为合法主机名",
                url=raw,
            )
        # httpx 期望小写 ASCII 主机；fragment 永远不会发往服务器，直接去掉
        netloc = host_ascii + (f":{parts.port}" if parts.port else "")
        normalized = urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))
        return normalized, None

    # ── 主流程 ─────────────────────────────────────────────────

    def discover(self, url: str) -> DiscoveryResult:
        """
        自动发现 URL 的内容结构。

        流程：归一化 → 主请求 → 内容分类 →（必要时）有界探测回退
        （www 变体 / http 降级 / feed 路径 / HTML 内嵌 feed）。
        任何失败都落在分类体系内，不抛异常。
        """
        result = DiscoveryResult(url=url)

        normalized, fail = self._normalize_url(url)
        if fail:
            result.failure = fail
            result.errors = self._failure_errors(fail)
            return result
        # 结果反映归一化后的实际地址（后续保存任务直接可用）
        result.url = normalized
        tried: list[str] = [normalized]

        # X（推特）账号主页：普通 HTML 抓取只能拿到 SPA 空壳，
        # 直接走内置的公开时间线适配器，避免误判为 JS_RENDERED_PAGE
        x_url = normalize_x_source_url(normalized)
        if x_url:
            screen_name = extract_screen_name(x_url)
            result.source_type = "x"
            result.title = f"X 账号 @{screen_name}" if screen_name else "X 账号时间线"
            result.description = (
                "X（推特）公开时间线：内置适配器解析最新推文，"
                "无需登录/API Key，已自动过滤转推与回复。"
            )
            result.list_selector = "x:"
            result.title_selector = "x:text"
            result.link_selector = "x:url"
            result.summary_selector = "x:meta"
            result.tried_urls = tried
            return result

        resp, fail = self._fetch_with_classification(normalized, timeout=15.0)

        if resp is None:
            # 主请求失败：有界回退探测（www 变体 / http 降级 / 根路径 feed）
            for candidate, purpose in self._fallback_candidates(normalized, fail):
                if candidate in tried:
                    continue
                tried.append(candidate)
                resp2, _ = self._fetch_with_classification(
                    candidate, timeout=10.0, max_bytes=self._PROBE_MAX_BYTES,
                )
                if resp2 is None:
                    continue
                if purpose == "feed-path" and not self._is_feed_response(resp2):
                    continue  # feed 路径返回 HTML 属于软 404，不采用
                # 回退候选命中：按其内容完整分类（feed/json/html 均可接受）
                content_fail, feed_candidates = self._classify_content(resp2, candidate, result)
                if content_fail is None:
                    # 任务 source_url 必须是实际可抓取的地址（如 www 变体）
                    result.url = candidate
                    result.tried_urls = tried
                    return result
                if purpose == "feed-path":
                    continue  # 探测路径的内容不达标就继续换下一个
                break

            final = fail or DiscoveryFailure(
                FailureCode.FETCH_FAILED, "无法访问该 URL，且原因未明", url=normalized,
            )
            result.failure = final
            result.errors = self._failure_errors(final)
            result.tried_urls = tried
            return result

        # 主请求成功 → 内容分类
        content_fail, feed_candidates = self._classify_content(resp, normalized, result)
        if content_fail is None:
            result.tried_urls = tried
            return result

        # 内容可达但不是可直接聚合的结构：feed 回退（内嵌 feed → 根路径探测）。
        # 探测不限于根路径——文章页/标签页失败时，站点级 feed 依然是
        # 可用的替代数据源
        for candidate in feed_candidates[:1]:
            if candidate in tried:
                continue
            tried.append(candidate)
            resp2, _ = self._fetch_with_classification(
                candidate, timeout=10.0, max_bytes=self._PROBE_MAX_BYTES,
            )
            if resp2 is not None and self._is_feed_response(resp2):
                fill_fail = self._fill_rss_result(resp2, candidate, result)
                if fill_fail is None:
                    result.url = candidate
                    result.tried_urls = tried
                    return result
        if content_fail.code in (
            FailureCode.NO_LIST_STRUCTURE, FailureCode.JS_RENDERED_PAGE,
        ):
            for probe in self._feed_path_candidates(normalized):
                if probe in tried:
                    continue
                tried.append(probe)
                resp2, _ = self._fetch_with_classification(
                    probe, timeout=10.0, max_bytes=self._PROBE_MAX_BYTES,
                )
                if resp2 is not None and self._is_feed_response(resp2):
                    fill_fail = self._fill_rss_result(resp2, probe, result)
                    if fill_fail is None:
                        # 推荐改用探测到的 feed 地址
                        content_fail.suggested_url = probe
                        result.url = probe
                        result.tried_urls = tried
                        return result

        result.failure = content_fail
        result.errors = self._failure_errors(content_fail)
        result.tried_urls = tried
        return result

    @staticmethod
    def _failure_errors(fail: DiscoveryFailure) -> list[str]:
        """人读错误清单（兼容旧消费方）：主文案 + 提示"""
        errors = [fail.message]
        if fail.hint:
            errors.append(f"提示：{fail.hint}")
        return errors

    # ── 回退候选生成 ───────────────────────────────────────────

    def _fallback_candidates(
        self, url: str, fail: DiscoveryFailure | None,
    ) -> list[tuple[str, str]]:
        """
        根据主请求的失败类别生成有界回退候选：
        - DNS 解析失败且主机无 www 前缀 → www 变体（最常见的手输差异）
        - https 连接/TLS 失败 → http 降级（内网遗留服务）
        - 根路径 404 → 常见 feed 路径探测
        每类至多一个候选（feed 路径至多 6 个），探测总量有界。
        """
        out: list[tuple[str, str]] = []
        if not fail:
            return out
        parts = urlsplit(url)
        host = parts.hostname or ""
        if fail.code == FailureCode.DNS_NOT_FOUND and not host.startswith("www."):
            out.append((urlunsplit((parts.scheme, f"www.{parts.netloc}", parts.path, parts.query, "")), "www"))
        if fail.code in (FailureCode.CONNECTION_FAILED, FailureCode.TLS_ERROR, FailureCode.TIMEOUT) \
                and parts.scheme == "https":
            out.append((urlunsplit(("http", parts.netloc, parts.path, parts.query, "")), "http"))
        if fail.code == FailureCode.HTTP_NOT_FOUND and self._is_root_path(url):
            for path in self._FEED_PROBE_PATHS:
                out.append((urlunsplit((parts.scheme, parts.netloc, path, "", "")), "feed-path"))
        return out

    @staticmethod
    def _is_root_path(url: str) -> bool:
        parts = urlsplit(url)
        return parts.path in ("", "/")

    def _feed_path_candidates(self, url: str) -> list[str]:
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        return [root + path for path in self._FEED_PROBE_PATHS]

    # ── 抓取与传输层分类 ───────────────────────────────────────

    def _fetch_with_classification(
        self, url: str, timeout: float, max_bytes: int | None = None,
    ) -> tuple[httpx.Response | None, DiscoveryFailure | None]:
        """
        获取页面并把传输层失败映射进分类体系：SSRF 预检 → 有界流式请求 →
        逐跳重定向（每跳重新预检）→ 状态码分类。

        连接层的 IP pinning（DNS rebinding TOCTOU 关闭）由共享客户端的
        传输后端强制执行（core/ssrf.py::SSRFPinnedNetworkBackend）。
        """
        from app.crawler.engine import MAX_RESPONSE_BYTES, _fetch_bounded

        max_bytes = max_bytes or MAX_RESPONSE_BYTES

        is_safe, error_msg, _ = resolve_and_validate_url(url)
        if not is_safe:
            logger.warning("SSRF check blocked URL %s: %s", url, error_msg)
            # 预检"异常"（而非策略拒绝）主要是 DNS 解析失败——映射到对应
            # 类别，不能笼统归为安全拦截
            if "URL 安全校验失败" in error_msg:
                if any(p in error_msg.lower() for p in self._DNS_ERROR_PATTERNS):
                    return None, DiscoveryFailure(
                        FailureCode.DNS_NOT_FOUND,
                        f"域名不存在或无法解析：{urlsplit(url).hostname}",
                        "检查域名拼写；若站点已下线则无法作为数据源",
                        url=url,
                    )
                return None, DiscoveryFailure(
                    FailureCode.INVALID_URL,
                    f"URL 校验失败：{error_msg}",
                    url=url,
                )
            return None, DiscoveryFailure(
                FailureCode.SSRF_BLOCKED,
                f"目标地址被安全策略拦截：{error_msg}",
                "本系统只能聚合公网 http(s) 内容；内网、环回与云元数据地址"
                "按设计一律禁止访问",
                url=url,
            )

        hops = 0
        current = url
        try:
            client = get_http_client()
            while True:
                response, fetch_err = _fetch_bounded(
                    client, "GET", current, max_bytes, timeout=timeout,
                )
                if fetch_err:
                    logger.warning("Discovery fetch error for %s: %s", current, fetch_err)
                    if "too large" in fetch_err.lower():
                        return None, DiscoveryFailure(
                            FailureCode.RESPONSE_TOO_LARGE,
                            "响应体超过大小上限（5 MB），不像可聚合的内容列表",
                            "若该站点同时提供 Feed 或轻量列表页，请改用其地址",
                            url=current,
                        )
                    return None, DiscoveryFailure(
                        FailureCode.FETCH_FAILED,
                        f"读取响应失败：{fetch_err}",
                        url=current,
                    )

                if getattr(response, "is_redirect", False):
                    location = response.headers.get("location")
                    if not location or hops >= MAX_REDIRECTS:
                        return None, DiscoveryFailure(
                            FailureCode.REDIRECT_LIMIT,
                            f"重定向超过 {MAX_REDIRECTS} 跳上限，已放弃",
                            "目标可能在无限重定向循环中；请直接输入最终页面地址",
                            url=current,
                        )
                    next_url = str(response.url.join(location))
                    hop_safe, hop_msg, _ = resolve_and_validate_url(next_url)
                    if not hop_safe:
                        logger.warning("SSRF blocked on redirect %s -> %s: %s",
                                       url, next_url, hop_msg)
                        return None, DiscoveryFailure(
                            FailureCode.SSRF_BLOCKED,
                            f"重定向目标被安全策略拦截：{hop_msg}",
                            url=next_url,
                        )
                    hops += 1
                    current = next_url
                    continue

                response.raise_for_status()
                return response, None

        except httpx.HTTPStatusError as e:
            return None, self._classify_http_status(e.response, current)
        except httpx.TimeoutException as e:
            return None, DiscoveryFailure(
                FailureCode.TIMEOUT,
                f"连接或读取超时（>{int(timeout)}s）：{type(e).__name__}",
                "站点可能临时不可用或对海外访问限速，稍后重试",
                url=current,
            )
        except httpx.ConnectError as e:
            return None, self._classify_connect_error(e, current, timeout)
        except httpx.DecodingError as e:
            return None, DiscoveryFailure(
                FailureCode.FETCH_FAILED,
                f"响应解码失败（压缩数据异常）：{e}",
                url=current,
            )
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return None, DiscoveryFailure(
                FailureCode.FETCH_FAILED,
                f"请求失败：{type(e).__name__}: {e}",
                url=current,
            )

    # DNS 解析失败的跨平台报文特征（gaierror 文案因 OS/语言而异）
    _DNS_ERROR_PATTERNS = (
        "getaddrinfo", "name or service not known", "nodename nor servname",
        "no such host", "host not found", "temporary failure in resolution",
        "temporary failure in name resolution", "没有与主机名称关",
        "不知道这样的主机",
    )
    # TLS/证书失败特征
    _TLS_ERROR_PATTERNS = (
        "certificate", "ssl", "handshake", "certificate_verify",
        "wrong_version_number",
    )

    def _classify_connect_error(
        self, exc: Exception, url: str, timeout: float,
    ) -> DiscoveryFailure:
        text = str(exc).lower()
        if any(p in text for p in self._DNS_ERROR_PATTERNS):
            return DiscoveryFailure(
                FailureCode.DNS_NOT_FOUND,
                f"域名不存在或无法解析：{urlsplit(url).hostname}",
                "检查域名拼写；若站点已下线则无法作为数据源",
                url=url,
            )
        if any(p in text for p in self._TLS_ERROR_PATTERNS):
            return DiscoveryFailure(
                FailureCode.TLS_ERROR,
                f"HTTPS 证书校验失败或握手异常：{type(exc).__name__}",
                "证书过期/自签名站点无法安全抓取；可尝试该站点的 http 地址或 Feed",
                url=url,
            )
        return DiscoveryFailure(
            FailureCode.CONNECTION_FAILED,
            f"无法建立连接：{type(exc).__name__}",
            "站点可能已下线、端口未开放，或防火墙拦截了访问",
            url=url,
        )

    def _classify_http_status(
        self, response: httpx.Response, url: str,
    ) -> DiscoveryFailure:
        status = response.status_code
        reason = response.reason_phrase
        if status in (404, 410):
            return DiscoveryFailure(
                FailureCode.HTTP_NOT_FOUND,
                f"页面不存在（HTTP {status}）",
                "确认路径是否正确；若这是站点首页，常见 Feed 地址会自动尝试",
                url=url,
            )
        if status in (401, 403):
            server = (response.headers.get("server") or "").lower()
            if (
                "cloudflare" in server
                or response.headers.get("cf-mitigated")
                or "just a moment" in response.text[:2000].lower()
                or "challenge" in response.text[:2000].lower()
            ):
                return DiscoveryFailure(
                    FailureCode.BLOCKED_BY_WAF,
                    f"站点启用了反爬人机验证（HTTP {status}，Cloudflare 类挑战）",
                    "浏览器可以过验证但程序抓取过不去——技术上无法直接聚合；"
                    "请寻找该站点提供的 RSS/JSON 数据接口",
                    url=url,
                )
            return DiscoveryFailure(
                FailureCode.AUTH_REQUIRED,
                f"需要登录或访问权限（HTTP {status}）",
                "需要账号才能看到的页面无法聚合；请提供公开可访问的列表页或 Feed",
                url=url,
            )
        if status == 429:
            return DiscoveryFailure(
                FailureCode.RATE_LIMITED,
                "请求过于频繁（HTTP 429），被站点限流",
                "稍后重试；若持续限流则该站点不适合定时抓取",
                url=url,
            )
        if status >= 500:
            return DiscoveryFailure(
                FailureCode.SERVER_ERROR,
                f"站点服务端错误（HTTP {status} {reason}）",
                "站点自身故障，稍后重试",
                url=url,
            )
        return DiscoveryFailure(
            FailureCode.FETCH_FAILED,
            f"意外响应状态（HTTP {status} {reason}）",
            url=url,
        )

    # ── 内容分类 ───────────────────────────────────────────────

    def _classify_content(
        self, response: httpx.Response, url: str, result: DiscoveryResult,
    ) -> tuple[DiscoveryFailure | None, list[str]]:
        """
        对成功响应做内容分类。成功时把结果填入 result 并返回 (None, [])；
        不可直接聚合时返回 (failure, feed_candidates)——feed_candidates 是
        从 HTML 里发现的内容源地址，供上层回退探测。
        """
        content_type = response.headers.get("content-type", "").lower()
        body = response.text

        # 1. 二进制内容：爬取器面向文本列表，技术上无法聚合
        binary = self._binary_kind(content_type, response.content)
        if binary:
            return DiscoveryFailure(
                FailureCode.NOT_A_WEBPAGE,
                f"该地址指向{binary}，不是可聚合的网页内容",
                "请改为提供文章列表页、栏目页或该站点的 Feed 地址",
                url=url,
            ), []

        # 2. RSS/Atom
        if self._is_feed_response(response):
            fail = self._fill_rss_result(response, url, result)
            return fail, []

        # 3. JSON API
        if "json" in content_type or self._looks_like_json(body):
            result.source_type = "json"
            result.json_path = self._detect_json_path(body)
            result.list_selector = f"json:{result.json_path}"
            (result.title_selector, result.link_selector,
             result.summary_selector) = self._detect_json_fields(body, result.json_path)
            return None, []

        # 4. HTML：标题/描述/feed 链接/列表结构
        soup = BeautifulSoup(body, "html.parser")
        title_tag = soup.find("title")
        if title_tag:
            result.title = title_tag.get_text(strip=True)
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            result.description = meta_desc.get("content", "")
        result.source_type = "html"

        feed_candidates = self._find_feed_links(soup, url)

        list_selector = self._find_list_selector(soup)
        accepted = False
        if list_selector:
            items = soup.select(list_selector)[:5]
            result.candidate_count = len(soup.select(list_selector))
            if items:
                result.title_selector = self._find_title_selector(items[0])
                result.link_selector = self._find_link_selector(items[0])
                result.summary_selector = self._find_summary_selector(items[0])
                samples = []
                for item in items[:5]:
                    sample = self._extract_sample(item, result, url)
                    if sample:
                        samples.append(sample)
                # 复读门：真实列表的条目标题互不相同；同一标题反复出现说明
                # 匹配到的是导航/推荐位伪容器（文章详情页的典型误判——伪列表
                # 产出的选择器抓回来全是重复条目，比诚实失败更有害）
                distinct_titles = {s["title"] for s in samples if s["title"]}
                if len(samples) >= 3 and len(distinct_titles) >= min(3, len(samples)):
                    result.list_selector = list_selector
                    result.sample_items = samples
                    accepted = True
        if accepted:
            result.next_page_selector = self._find_next_page_selector(soup)
            return None, []
        # 复读门拒绝时清理半成品字段，按无列表结构继续分类
        result.list_selector = ""
        result.title_selector = ""
        result.link_selector = ""
        result.summary_selector = ""
        result.candidate_count = 0
        result.sample_items = []

        # 5. 无列表结构：区分 SPA / 文章详情页 / 普通空页
        if self._looks_like_spa(soup, body):
            return DiscoveryFailure(
                FailureCode.JS_RENDERED_PAGE,
                "该页面内容由浏览器端 JavaScript 渲染，服务端返回的是空壳"
                "（SPA），HTML 解析在原理上拿不到任何列表",
                "请寻找该站点的 RSS 订阅地址或数据接口（本系统已尝试常见 "
                "Feed 路径与页面内声明的 Feed）",
                url=url,
            ), feed_candidates

        hint = ""
        if self._looks_like_article(soup):
            hint = ("这是文章详情页而非列表页——详情页只有一篇内容，"
                    "聚合器需要「多条标题+链接」的列表结构")
        suggested = feed_candidates[0] if feed_candidates else ""
        return DiscoveryFailure(
            FailureCode.NO_LIST_STRUCTURE,
            "页面可访问，但未发现可聚合的文章列表结构",
            hint or "请改为输入栏目页/列表页/标签页 URL（页面上有多条同类条目的页面）",
            url=url,
            suggested_url=suggested,
        ), feed_candidates

    def _fill_rss_result(
        self, response: httpx.Response, url: str, result: DiscoveryResult,
    ) -> DiscoveryFailure | None:
        """把 RSS/Atom 响应填入结果。返回 None 表示成功。"""
        body = response.text
        result.source_type = "rss"
        result.feed_url = url
        result.title = self._extract_feed_title(body)
        result.description = self._extract_feed_description(body)
        # RSS 的标题/链接来自 feed 自身，配置只需 rss: 前缀；
        # 但仍要把字段填满，否则向导产出的任务缺少必填选择器
        # （与预设模板保持一致）。
        result.list_selector = "rss:"
        result.title_selector = "title"
        result.link_selector = "url"
        result.summary_selector = "description"
        return None

    # ── 响应形态判定 ───────────────────────────────────────────

    def _is_feed_response(self, response: httpx.Response) -> bool:
        """content-type 或正文前部命中 RSS/Atom 形态"""
        content_type = response.headers.get("content-type", "").lower()
        if "rss" in content_type or "atom" in content_type:
            return True
        head = response.text[:4096]
        return bool(re.search(r"<(rss|feed)\b", head, re.IGNORECASE))

    _BINARY_CT_PREFIXES = ("image/", "video/", "audio/", "font/")
    _BINARY_CT_EXACT = {
        "application/pdf": "PDF 文档",
        "application/zip": "压缩包",
        "application/x-zip-compressed": "压缩包",
        "application/gzip": "压缩包",
        "application/x-gzip": "压缩包",
        "application/x-7z-compressed": "压缩包",
        "application/x-rar-compressed": "压缩包",
        "application/octet-stream": "二进制文件",
        "application/wasm": "二进制文件",
    }

    def _binary_kind(self, content_type: str, content: bytes) -> str | None:
        """识别非网页二进制内容，返回中文类别名；网页/文本返回 None"""
        ct = content_type.split(";")[0].strip()
        if ct.startswith(self._BINARY_CT_PREFIXES):
            return "图片" if ct.startswith("image/") else "音视频"
        if ct in self._BINARY_CT_EXACT:
            return self._BINARY_CT_EXACT[ct]
        # content-type 说谎时用魔数兜底（content 已解压，魔数可直接读）
        if content[:5] == b"%PDF-":
            return "PDF 文档"
        if content[:4] in (b"\x89PNG", b"GIF8", b"RIFF"):
            return "图片"
        if content[:2] == b"\x1f\x8b" or content[:4] == b"PK\x03\x04":
            return "压缩包"
        if content[:4] == b"OggS" or content[:3] == b"ID3":
            return "音视频"
        return None

    def _looks_like_spa(self, soup: BeautifulSoup, body: str) -> bool:
        """
        纯前端渲染（SPA）判定：服务端返回的 HTML 只有挂载点与脚本包，
        没有服务端输出的"内容级链接"——列表解析在原理上无内容可解析。

        组合信号判定（不用正文长度做硬性短路：导航/页脚文本可以让
        空壳页的文字量超过阈值，少数派的客户端渲染标签页就是实例）：
        - 挂载点标记（root/app/__next/__nuxt…）在场，且内容级锚点稀少
        - 或打包器特征脚本在场 + 正文极短 + 内容级锚点稀少
        """
        scripts = soup.find_all("script")
        content_links = [
            a for a in soup.find_all("a", href=True)
            if len(a.get_text(strip=True)) >= 8
        ]
        has_mount = bool(soup.find(id=lambda v: v and v.lower() in {
            "root", "app", "__next", "__nuxt", "q-app",
        }))
        has_module_scripts = False
        for s in scripts:
            src = s.get("src") or ""
            if s.get("type") == "module" or "/_next/" in src or "/static/" in src \
                    or "/assets/" in src or "/chunks/" in src:
                has_module_scripts = True
                break

        if has_mount and len(content_links) < 5:
            return True
        if has_module_scripts and len(content_links) < 5 \
                and len(soup.get_text(strip=True)) < 400:
            return True
        return False

    def _looks_like_article(self, soup: BeautifulSoup) -> bool:
        """单篇文章详情页判定：唯一 <article> + 大段正文，没有重复列表"""
        articles = soup.find_all("article")
        if len(articles) != 1:
            return False
        return len(soup.get_text(strip=True)) > 1200

    # ── HTML 内嵌 feed 自动发现 ────────────────────────────────

    def _find_feed_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """`<link rel="alternate" type="application/rss+xml">` 等声明的 feed 地址"""
        out: list[str] = []
        for link in soup.find_all("link"):
            rel = " ".join(link.get("rel") or []).lower()
            if "alternate" not in rel:
                continue
            ltype = (link.get("type") or "").lower()
            if "rss" in ltype or "atom" in ltype:
                href = link.get("href")
                if href:
                    out.append(urljoin(base_url, href))
        return out

    # ── 解析辅助（保持原有行为） ───────────────────────────────

    def _looks_like_json(self, body: str) -> bool:
        """检测是否为 JSON"""
        body = body.strip()
        return body.startswith("{") or body.startswith("[")

    def _extract_feed_title(self, body: str) -> str:
        """提取 feed 标题"""
        match = re.search(r"<title>([^<]+)</title>", body, re.IGNORECASE)
        return match.group(1) if match else ""

    def _extract_feed_description(self, body: str) -> str:
        """提取 feed 描述"""
        match = re.search(r"<description>([^<]+)</description>", body, re.IGNORECASE)
        return match.group(1) if match else ""

    # JSON 条目里常见的字段名（小写比较），用于把 title/link/summary 探测出来
    _JSON_TITLE_KEYS = ("title", "name", "headline", "subject", "question")
    _JSON_LINK_KEYS = ("url", "link", "permalink", "href", "short_link_v2", "short_url")
    _JSON_SUMMARY_KEYS = ("summary", "description", "desc", "content", "brief_content", "selftext", "body")

    def _detect_json_path(self, body: str, max_depth: int = 3) -> str:
        """
        检测 JSON 数据路径：返回「根 → 第一个元素数组」的点分路径。

        只看顶层字段会让嵌套 API（Reddit 的 data.children、掘金的
        data.xxx 等）落空，向导随后写出 json: + 空路径的配置 —— 看起来合法
        但抓取结果是一整块 JSON。这里做有界递归（深度 ≤ 3，够覆盖常见结构）。
        """
        try:
            data = _json.loads(body)
        except Exception:
            return ""
        return self._find_list_path(data, max_depth) or ""

    def _find_list_path(self, node: Any, depth: int) -> str | None:
        """返回第一个「字典数组」所在的点分路径；根即数组时返回空串。"""
        if isinstance(node, list):
            return "" if node and isinstance(node[0], dict) else None
        if depth <= 0 or not isinstance(node, dict):
            return None
        for key, value in node.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return key
            if isinstance(value, dict):
                sub = self._find_list_path(value, depth - 1)
                if sub is not None:
                    return f"{key}.{sub}" if sub else key
        return None

    def _detect_json_fields(self, body: str, json_path: str) -> tuple[str, str, str]:
        """
        从 JSON 首条记录探测 title / link / summary 字段名。

        引擎在字段缺失时会回退到 title / url，但向导要据此写出完整的任务配置，
        否则 JSON 模板会缺少必填选择器（schema 直接拒绝保存）。
        """
        def _pick(lower_keys: dict[str, str], candidates: tuple[str, ...], default: str) -> str:
            for cand in candidates:
                if cand in lower_keys:
                    return lower_keys[cand]
            return default

        try:
            node: Any = _json.loads(body)
            for part in [p for p in json_path.split(".") if p]:
                if isinstance(node, dict):
                    node = node.get(part)
                elif isinstance(node, list) and part.isdigit():
                    node = node[int(part)] if int(part) < len(node) else None
                else:
                    node = None
                if node is None:
                    break
            if isinstance(node, list) and node and isinstance(node[0], dict):
                lower_keys = {str(k).lower(): str(k) for k in node[0]}
                return (
                    _pick(lower_keys, self._JSON_TITLE_KEYS, "title"),
                    _pick(lower_keys, self._JSON_LINK_KEYS, "url"),
                    _pick(lower_keys, self._JSON_SUMMARY_KEYS, ""),
                )
        except Exception:
            pass
        return "title", "url", ""

    def _find_list_selector(self, soup: BeautifulSoup) -> str:
        """查找列表选择器"""
        # 常见的文章列表选择器
        candidates = [
            "article",
            ".post",
            ".entry",
            ".item",
            ".list-item",
            ".card",
            "li.article",
            "div.post",
            ".news-item",
            ".story",
        ]

        for selector in candidates:
            items = soup.select(selector)
            if len(items) >= 3:
                return selector

        # 回退：查找包含多个链接的容器
        for tag in ["div", "section", "ul"]:
            elements = soup.find_all(tag)
            for el in elements:
                links = el.find_all("a", href=True)
                if len(links) >= 5:
                    # 生成类选择器
                    classes = el.get("class", [])
                    if classes:
                        return f"{tag}.{classes[0]}"
                    return tag

        return ""

    def _find_title_selector(self, item: BeautifulSoup) -> str:
        """查找标题选择器"""
        # 优先 h1-h6
        for tag in ["h1", "h2", "h3", "h4"]:
            heading = item.find(tag)
            if heading:
                return tag
        # 回退：第一个链接
        link = item.find("a")
        if link:
            return "a"
        return ""

    def _find_link_selector(self, item: BeautifulSoup) -> str:
        """查找链接选择器"""
        link = item.find("a", href=True)
        if link:
            return "a"
        return ""

    def _find_summary_selector(self, item: BeautifulSoup) -> str:
        """查找摘要选择器"""
        # 优先 p 标签
        p = item.find("p")
        if p:
            return "p"
        # 回退：div 包含文本
        for div in item.find_all("div"):
            text = div.get_text(strip=True)
            if len(text) > 20:
                return "div"
        return ""

    def _find_next_page_selector(self, soup: BeautifulSoup) -> str:
        """查找下一页选择器"""
        # 常见的下一页链接
        patterns = [
            "a.next",
            "a.pagination-next",
            "a[rel='next']",
            ".pagination a:last-child",
            "a:contains('Next')",
            "a:contains('下一页')",
        ]

        for pattern in patterns:
            try:
                next_link = soup.select_one(pattern)
                if next_link:
                    return pattern
            except Exception:
                continue

        return ""

    def _extract_sample(
        self, item: BeautifulSoup, result: DiscoveryResult, base_url: str
    ) -> dict[str, str]:
        """提取样本 item"""
        sample = {"title": "", "url": "", "summary": ""}

        # 标题
        if result.title_selector:
            title_el = item.select_one(result.title_selector)
            if title_el:
                sample["title"] = title_el.get_text(strip=True)

        # 链接
        if result.link_selector:
            link_el = item.select_one(result.link_selector)
            if link_el:
                href = link_el.get("href", "")
                sample["url"] = urljoin(base_url, href)

        # 摘要
        if result.summary_selector:
            summary_el = item.select_one(result.summary_selector)
            if summary_el:
                sample["summary"] = summary_el.get_text(strip=True)[:200]

        return sample


# 全局单例
url_discoverer = URLDiscoverer()
