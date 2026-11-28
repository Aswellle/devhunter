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
            elif discovery_result.source_type == "x":
                result = self._preview_x(url, limit)
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

        # 预览不做关键词过滤，全量展示
        crawl_result = fetch_and_parse(url, selectors, [])

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

        crawl_result = fetch_and_parse(url, selectors, [])

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

    def _preview_x(self, url: str, limit: int) -> PreviewResult:
        """预览 X（推特）公开账号时间线（引擎内部改写为 syndication 地址）"""
        result = PreviewResult()

        selectors = {
            "list": "x:",
            "title": "x:text",
            "link": "x:url",
            "summary": "x:meta",
        }

        crawl_result = fetch_and_parse(url, selectors, [])

        if crawl_result.error:
            if "429" in crawl_result.error or "Too Many Requests" in crawl_result.error:
                result.error = (
                    "X 嵌入接口限流（HTTP 429）：同一 IP 约 30 次/窗口。"
                    "请稍后再试，或把 X 任务频率降到每小时一次。"
                )
            else:
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
        """预览 JSON API：沿用自动发现的字段映射（与执行落库走同一份选择器）"""
        result = PreviewResult()

        # list selector 优先用发现结果原样透传（json-post 场景含请求体，
        # 从 json_path 重建会把 POST 降级成 GET）；title/link/summary 用发现
        # 到的字段名，与向导保存进 Task、引擎执行时使用的映射保持一致。
        selectors = {
            "list": discovery.list_selector
            or (f"json:{discovery.json_path}" if discovery.json_path else "json:"),
            "title": discovery.title_selector or "title",
            "link": discovery.link_selector or "url",
            "summary": discovery.summary_selector or "description",
        }

        crawl_result = fetch_and_parse(url, selectors, [])

        if crawl_result.error:
            result.error = crawl_result.error
            return result

        if crawl_result.extracted_count == 0:
            result.error = (
                "未提取到任何条目：请检查列表路径与 title/link 字段映射——"
                "title 或 link 缺失的条目会被跳过（HTTP "
                f"{crawl_result.http_status}）"
            )
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
