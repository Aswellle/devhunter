"""
app/sources/tester.py
Test Before Save：保存前测试。

测试内容：
1. 测试连接（HTTP 可访问）
2. 测试解析（能提取条目）
3. 验证字段（必填字段覆盖率）
4. 去重键验证（url_hash 有效）
"""
import logging
from dataclasses import dataclass, field
from typing import Any

from app.crawler.engine import fetch_and_parse
from app.sources.validation import SemanticValidator

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """测试结果"""
    __test__ = False  # 防止 pytest 将其作为测试类收集

    success: bool = False
    transport_success: bool = False
    parse_success: bool = False
    semantic_success: bool = False
    http_status: int = 0
    items_found: int = 0
    field_coverage: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "transport_success": self.transport_success,
            "parse_success": self.parse_success,
            "semantic_success": self.semantic_success,
            "http_status": self.http_status,
            "items_found": self.items_found,
            "field_coverage": round(self.field_coverage, 3),
            "errors": self.errors,
            "warnings": self.warnings,
        }


class ConfigTester:
    """配置测试器"""

    def test(
        self,
        url: str,
        selectors: dict[str, str],
        expected_min_items: int = 1,
        required_fields: list[str] | None = None,
    ) -> TestResult:
        """
        测试配置。

        Args:
            url: 目标 URL
            selectors: 选择器配置
            expected_min_items: 期望最小条目数
            required_fields: 必填字段

        Returns:
            TestResult
        """
        result = TestResult()

        try:
            # 1. 抓取页面
            crawl_result = fetch_and_parse(url, selectors)

            if crawl_result.error:
                result.errors.append(crawl_result.error)
                return result

            result.http_status = crawl_result.http_status
            result.transport_success = True

            # 2. 检查解析结果
            if crawl_result.extracted_count == 0:
                result.errors.append("No items extracted")
                return result

            result.parse_success = True
            result.items_found = crawl_result.extracted_count

            # 3. 语义验证
            validator = SemanticValidator(
                expected_min_items=expected_min_items,
                required_fields=required_fields or ["title", "link"],
            )

            items = [
                {"title": item.title, "url": item.url, "summary": item.summary}
                for item in crawl_result.items
            ]

            validation = validator.validate(crawl_result.http_status, items)
            result.semantic_success = validation.semantic_success
            result.field_coverage = validation.field_coverage
            result.warnings = validation.warnings

            if not result.semantic_success:
                result.errors.append("Semantic validation failed")

            result.success = (
                result.transport_success
                and result.parse_success
                and result.semantic_success
            )

        except Exception as e:
            result.errors.append(f"Test error: {str(e)}")
            logger.warning("Test failed for %s: %s", url, e)

        return result


# 全局单例
config_tester = ConfigTester()
