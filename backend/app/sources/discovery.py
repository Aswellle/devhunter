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
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..crawler.engine import resolve_and_validate_url

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
                result.errors.append("Failed to fetch URL")
                return result

            content_type = response.headers.get("content-type", "")
            body = response.text

            # 2. 检测 RSS/Atom
            if "rss" in content_type or "atom" in content_type or self._looks_like_feed(body):
                result.source_type = "rss"
                result.feed_url = url
                result.title = self._extract_feed_title(body)
                result.description = self._extract_feed_description(body)
                return result

            # 3. 检测 JSON API
            if "json" in content_type or self._looks_like_json(body):
                result.source_type = "json"
                result.json_path = self._detect_json_path(body)
                return result

            # 4. HTML 页面分析
            result.source_type = "html"
            self._analyze_html(body, url, result)

        except Exception as e:
            result.errors.append(f"Discovery error: {str(e)}")

        return result

    def _fetch(self, url: str) -> httpx.Response | None:
        """获取页面（带 SSRF 保护 + IP pinning 防 DNS rebinding）"""
        # Resolve hostname → validate IP → pin the IP for the actual connection.
        # Connecting to the validated IP (with original Host header) closes the
        # DNS-rebind TOCTOU window: an attacker cannot swap the IP between the
        # check and the fetch because we connect to the already-validated IP.
        is_safe, error_msg, validated_ip = resolve_and_validate_url(url)
        if not is_safe:
            logger.warning("SSRF check blocked URL %s: %s", url, error_msg)
            return None

        try:
            client = get_http_client()
            if validated_ip:
                parsed = urlparse(url)
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                pinned_netloc = f"{validated_ip}:{port}"
                pinned_url = parsed._replace(netloc=pinned_netloc).geturl()
                headers = {"Host": parsed.hostname}
                logger.debug("SSRF IP-pinning: %s -> %s", url, pinned_url)
                response = client.get(
                    pinned_url, headers=headers, follow_redirects=False, timeout=15.0
                )
            else:
                response = client.get(url, follow_redirects=False, timeout=15.0)
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

    def _detect_json_path(self, body: str) -> str:
        """检测 JSON 数据路径"""
        try:
            data = _json.loads(body)
            if isinstance(data, list):
                return ""  # 根就是数组
            if isinstance(data, dict):
                # 查找第一个数组字段
                for key, value in data.items():
                    if isinstance(value, list) and len(value) > 0:
                        return key
        except Exception:
            pass
        return ""

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
