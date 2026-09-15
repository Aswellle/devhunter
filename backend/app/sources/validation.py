"""
app/sources/validation.py
Semantic Validation：抓取结果的三层验证。

验证层级：
1. transport_success: HTTP 可访问
2. parse_success: 解析出条目
3. semantic_success: 必填字段覆盖率达标
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ValidationResult:
    """验证结果"""

    def __init__(
        self,
        transport_success: bool = False,
        parse_success: bool = False,
        semantic_success: bool = False,
        items_found: int = 0,
        field_coverage: float = 0.0,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ):
        self.transport_success = transport_success
        self.parse_success = parse_success
        self.semantic_success = semantic_success
        self.items_found = items_found
        self.field_coverage = field_coverage
        self.errors = errors or []
        self.warnings = warnings or []

    @property
    def is_valid(self) -> bool:
        """是否通过全部验证"""
        return self.transport_success and self.parse_success and self.semantic_success

    @property
    def status(self) -> str:
        """验证状态"""
        if not self.transport_success:
            return "transport_failed"
        if not self.parse_success:
            return "parse_failed"
        if not self.semantic_success:
            return "semantic_failed"
        return "valid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "transport_success": self.transport_success,
            "parse_success": self.parse_success,
            "semantic_success": self.semantic_success,
            "items_found": self.items_found,
            "field_coverage": round(self.field_coverage, 3),
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class SemanticValidator:
    """
    语义验证器：检查抓取结果是否满足最低质量要求。

    配置示例（来自 source_template.config_json）：
    {
        "health": {
            "expected_min_items": 5,
            "required_fields": ["title", "link"]
        }
    }
    """

    def __init__(
        self,
        expected_min_items: int = 1,
        required_fields: list[str] | None = None,
        min_field_coverage: float = 0.9,
    ):
        self.expected_min_items = expected_min_items
        self.required_fields = required_fields or ["title", "link"]
        self.min_field_coverage = min_field_coverage

    def validate(
        self,
        http_status: int,
        items: list[dict[str, Any]],
    ) -> ValidationResult:
        """
        执行三层验证。

        Args:
            http_status: HTTP 状态码
            items: 解析出的条目列表
        """
        # Layer 1: Transport
        transport_success = 200 <= http_status < 300
        if not transport_success:
            return ValidationResult(
                transport_success=False,
                errors=[f"HTTP {http_status}"],
            )

        # Layer 2: Parse
        items_found = len(items)
        parse_success = items_found > 0
        if not parse_success:
            return ValidationResult(
                transport_success=True,
                parse_success=False,
                items_found=0,
                errors=["No items extracted"],
            )

        # Layer 3: Semantic
        field_coverage = self._calc_field_coverage(items)
        semantic_success = (
            items_found >= self.expected_min_items
            and field_coverage >= self.min_field_coverage
        )

        warnings = []
        if items_found < self.expected_min_items:
            warnings.append(
                f"Items found ({items_found}) < expected minimum ({self.expected_min_items})"
            )
        if field_coverage < self.min_field_coverage:
            warnings.append(
                f"Field coverage ({field_coverage:.1%}) < minimum ({self.min_field_coverage:.1%})"
            )

        return ValidationResult(
            transport_success=True,
            parse_success=True,
            semantic_success=semantic_success,
            items_found=items_found,
            field_coverage=field_coverage,
            warnings=warnings,
        )

    def _calc_field_coverage(self, items: list[dict[str, Any]]) -> float:
        """计算必填字段覆盖率"""
        if not items:
            return 0.0
        total = 0
        for item in items:
            for field in self.required_fields:
                if item.get(field):
                    total += 1
        return total / (len(items) * len(self.required_fields))


# 默认验证器
default_validator = SemanticValidator()
