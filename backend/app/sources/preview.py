"""
app/sources/preview.py
Preview Extraction：预览提取结果。

根据发现的配置，预览提取前 N 条结果。
"""
import logging
from dataclasses import dataclass, field
from typing import Any

from app.crawler.engine import fetch_and_parse
from app.sources.discovery import DiscoveryResult

logger = logging.getLogger(__name__)


@dataclass
class PreviewResult:
    """预览结果"""
    success: bool = False
    items: list[dict[str, Any]] = field(default_factory=list)
    total_found: int = 0
    error: str = ""
    http_status: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "items": self.items,
            "total_found": self.total_found,
            "error": self.error,
            "http_status": self.http_status,
        }


class PreviewExtractor:
    """预览提取器"""

    def preview(
        self,
        url: str,
        discovery_result: DiscoveryResult | None = None,
        limit: int = 5,
    ) -> PreviewResult:
        """
        预览提取结果。

        Args:
            url: 目标 URL
            discovery_result: 发现结果（可选）
            limit: 预览数量

        Returns:
            PreviewResult
        """
        result = PreviewResult()

        try:
            # 如果没有发现结果，先发现
            if not discovery_result:
                from app.sources.discovery import url_discoverer
                discovery_result = url_discoverer.discover(url)

            if discovery_result.errors:
                result.error = "; ".join(discovery_result.errors)
                return result

            # 根据 source_type 选择解析方式
            if discovery_result.source_type == "rss":
                result = self._preview_rss(url, discovery_result, limit)
            elif discovery_result.source_type == "json":
                result = self._preview_json(url, discovery_result, limit)
            else:
                result = self._preview_html(url, discovery_result, limit)

        except Exception as e:
            result.error = f"Preview error: {str(e)}"
            logger.warning("Preview failed for %s: %s", url, e)

        return result

    def _preview_html(
        self, url: str, discovery: DiscoveryResult, limit: int
    ) -> PreviewResult:
        """预览 HTML 页面"""
        result = PreviewResult()

        selectors = {
            "list": discovery.list_selector or "article",
            "title": discovery.title_selector or "h2",
            "link": discovery.link_selector or "a",
            "summary": discovery.summary_selector or "p",
        }

        crawl_result = fetch_and_parse(url, selectors)

        if crawl_result.error:
            result.error = crawl_result.error
            return result

        result.success = True
        result.http_status = crawl_result.http_status
        result.total_found = crawl_result.extracted_count

        for item in crawl_result.items[:limit]:
            result.items.append({
                "title": item.title,
                "url": item.url,
                "summary": item.summary,
            })

        return result

    def _preview_rss(self, url: str, discovery: DiscoveryResult, limit: int) -> PreviewResult:
        """预览 RSS feed"""
        result = PreviewResult()

        selectors = {
            "list": "rss:",
            "title": "rss:title",
            "link": "rss:link",
            "summary": "rss:description",
        }

        crawl_result = fetch_and_parse(url, selectors)

        if crawl_result.error:
            result.error = crawl_result.error
            return result

        result.success = True
        result.http_status = crawl_result.http_status
        result.total_found = crawl_result.extracted_count

        for item in crawl_result.items[:limit]:
            result.items.append({
                "title": item.title,
                "url": item.url,
                "summary": item.summary,
            })

        return result

    def _preview_json(self, url: str, discovery: DiscoveryResult, limit: int) -> PreviewResult:
        """预览 JSON API"""
        result = PreviewResult()

        json_path = discovery.json_path or ""
        selectors = {
            "list": f"json:{json_path}" if json_path else "json:",
            "title": "title",
            "link": "url",
            "summary": "description",
        }

        crawl_result = fetch_and_parse(url, selectors)

        if crawl_result.error:
            result.error = crawl_result.error
            return result

        result.success = True
        result.http_status = crawl_result.http_status
        result.total_found = crawl_result.extracted_count

        for item in crawl_result.items[:limit]:
            result.items.append({
                "title": item.title,
                "url": item.url,
                "summary": item.summary,
            })

        return result


# 全局单例
preview_extractor = PreviewExtractor()
