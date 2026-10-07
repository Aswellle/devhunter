"""
app/sources/discovery.py
URL Autodiscovery：自动发现 URL 的内容结构。

发现能力：
- 识别 RSS/Atom feed
- 识别 JSON API
- 查找文章列表
- 检测 pagination
- 分析 DOM 结构
"""
import json as _json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..core.http_client import get_http_client
from ..crawler.engine import MAX_REDIRECTS, resolve_and_validate_url

logger = logging.getLogger(__name__)

@dataclass
class DiscoveryResult:
    """发现结果"""
    url: str
    source_type: str = "unknown"  # rss | json | html
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
        }


class URLDiscoverer:
    """URL 自动发现器"""

    def discover(self, url: str) -> DiscoveryResult:
        """
        自动发现 URL 的内容结构。

        Args:
            url: 目标 URL

        Returns:
            DiscoveryResult
        """
        result = DiscoveryResult(url=url)

        try:
            # 1. 获取页面
            response = self._fetch(url)
            if not response:
                result.errors.append(
                    "无法访问该 URL：请检查网址是否正确、站点是否可访问；"
                    "内网/保留地址会被安全策略拦截"
                )
                return result

            content_type = response.headers.get("content-type", "")
            body = response.text

            # 2. 检测 RSS/Atom
            if "rss" in content_type or "atom" in content_type or self._looks_like_feed(body):
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
                return result

            # 3. 检测 JSON API
            if "json" in content_type or self._looks_like_json(body):
                result.source_type = "json"
                result.json_path = self._detect_json_path(body)
                result.list_selector = f"json:{result.json_path}"
                (result.title_selector, result.link_selector,
                 result.summary_selector) = self._detect_json_fields(body, result.json_path)
                return result

            # 4. HTML 页面分析
            result.source_type = "html"
            self._analyze_html(body, url, result)

        except Exception as e:
            result.errors.append(f"Discovery error: {str(e)}")

        return result

    def _fetch(self, url: str) -> httpx.Response | None:
        """
        获取页面：SSRF 校验 + 手动跟随重定向（每一跳重新校验）。

        ⚠️ 这里刻意不做 IP pinning。把请求地址换成「已验证 IP + Host 头」会让
        HTTPS 的 SNI 与证书按 IP 校验，直接
        `CERTIFICATE_VERIFY_FAILED: IP address mismatch` —— 于是所有 https
        站点的自动发现都失败。抓取引擎采用的是同一套策略：先校验、再按原 URL
        请求（follow_redirects=False），每一跳手动重新校验 SSRF。
        """
        is_safe, error_msg, _ = resolve_and_validate_url(url)
        if not is_safe:
            logger.warning("SSRF check blocked URL %s: %s", url, error_msg)
            return None

        try:
            client = get_http_client()
            response = client.get(url, follow_redirects=False, timeout=15.0)

            hops = 0
            while getattr(response, "is_redirect", False) and hops < MAX_REDIRECTS:
                location = response.headers.get("location")
                if not location:
                    break
                next_url = str(httpx.URL(location, base=response.url))
                hop_safe, hop_msg, _ = resolve_and_validate_url(next_url)
                if not hop_safe:
                    logger.warning("SSRF blocked on redirect %s -> %s: %s",
                                   url, next_url, hop_msg)
                    return None
                hops += 1
                response = client.get(next_url, follow_redirects=False, timeout=15.0)

            response.raise_for_status()
            return response
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return None

    def _looks_like_feed(self, body: str) -> bool:
        """检测是否为 RSS/Atom feed"""
        return bool(re.search(r"<(rss|feed|channel)\b", body, re.IGNORECASE))

    def _looks_like_json(self, body: str) -> bool:
        """检测是否为 JSON"""
        body = body.strip()
        return body.startswith("{") or body.startswith("[")

    def _extract_feed_title(self, body: str) -> str:
        """提取 feed 标题"""
        match = re.search(r'<title>([^<]+)</title>', body, re.IGNORECASE)
        return match.group(1) if match else ""

    def _extract_feed_description(self, body: str) -> str:
        """提取 feed 描述"""
        match = re.search(r'<description>([^<]+)</description>', body, re.IGNORECASE)
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

    def _analyze_html(self, body: str, base_url: str, result: DiscoveryResult) -> None:
        """分析 HTML 结构"""
        soup = BeautifulSoup(body, "html.parser")

        # 1. 提取页面标题
        title_tag = soup.find("title")
        if title_tag:
            result.title = title_tag.get_text(strip=True)

        # 2. 提取描述
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            result.description = meta_desc.get("content", "")

        # 3. 查找文章列表
        list_selector = self._find_list_selector(soup)
        if list_selector:
            result.list_selector = list_selector

            # 4. 提取标题/链接/摘要选择器
            items = soup.select(list_selector)[:5]
            result.candidate_count = len(soup.select(list_selector))

            if items:
                # 尝试找到标题选择器
                result.title_selector = self._find_title_selector(items[0])
                result.link_selector = self._find_link_selector(items[0])
                result.summary_selector = self._find_summary_selector(items[0])

                # 提取样本
                for item in items[:5]:
                    sample = self._extract_sample(item, result, base_url)
                    if sample:
                        result.sample_items.append(sample)

        # 5. 检测 pagination
        result.next_page_selector = self._find_next_page_selector(soup)

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
