"""
app/schemas/task.py
采集任务 Pydantic 模型：TaskCreate / TaskUpdate / TaskResponse
"""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator
import soupsieve as sv

from app.utils.url import is_valid_url

# ── 预设模板标识常量 ──────────────────────────────────────
PRESET_TEMPLATES = {
    "hackernews",
    "v2ex",
    "github_trending",
    "juejin",
    "indiehackers",
    # Stage 2/3 新增模板（与 templates/sources.json 保持同步）
    "devto",
    "reddit_webdev",
    "sspai",
    "bilibili_comprehensive",
    "bilibili_music",
}

# ── Selector 复杂度限制（ReDoS 防护）──────────────────────
_MAX_SELECTOR_LEN = 300
_MAX_COMBINATORS = 5   # 防止深层嵌套
_MAX_ATTR_SELECTORS = 3  # 防止复杂属性链


def _validate_selector(v: str | None, field_name: str) -> str | None:
    if v is None:
        return v
    if len(v) > _MAX_SELECTOR_LEN:
        raise ValueError(f"{field_name} exceeds max length {_MAX_SELECTOR_LEN}")
    # 限制 combinator 数量
    combinator_count = v.count(">") + v.count("+") + v.count("~")
    if combinator_count > _MAX_COMBINATORS:
        raise ValueError(f"{field_name} has too many combinators (> + ~), max {_MAX_COMBINATORS}")
    # 限制属性选择器数量
    attr_count = len(re.findall(r"\[.*?\]", v))
    if attr_count > _MAX_ATTR_SELECTORS:
        raise ValueError(f"{field_name} has too many attribute selectors, max {_MAX_ATTR_SELECTORS}")
    # 使用 soupsieve 验证语法，结构检查已足够防止 ReDoS
    # NotImplementedError: soupsieve 不支持某些 CSS4 选择器（如 :data()、:is() 嵌套等）
    try:
        sv.compile(v)
    except sv.SelectorSyntaxError as e:
        raise ValueError(f"Invalid CSS selector in {field_name}: {e}")
    except NotImplementedError:
        # soupsieve 无法解析的选择器（如 :data()），结构检查已做 ReDoS 防护，放行
        pass
    return v


def _validate_next_page_selector(v: str | None) -> str | None:
    """
    selector_next_page 校验：允许 None/空，允许 json:/json-post: 前缀路径，
    仅对纯 CSS 值运行 soupsieve 校验。
    """
    if v is None or not v.strip():
        return None
    v = v.strip()
    if v.startswith("json:") or v.startswith("json-post:"):
        # JSON 路径，跳过 soupsieve；复用长度上限
        if len(v) > _MAX_SELECTOR_LEN:
            raise ValueError(f"selector_next_page exceeds max length {_MAX_SELECTOR_LEN}")
        return v
    # 纯 CSS：走标准 selector 校验
    return _validate_selector(v, "selector_next_page")


# ── 频率快捷选项 → Cron 表达式映射 ───────────────────────
FREQUENCY_PRESETS: dict[str, str] = {
    "every_30min": "*/30 * * * *",
    "every_hour":  "0 * * * *",
    "every_6h":    "0 */6 * * *",
    "every_day":   "0 9 * * *",
}


class TaskBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="任务名称")
    source_url: str = Field(..., max_length=2048, description="目标页面 URL")
    template_id: str | None = Field(None, description="预设模板 ID，None 表示自定义")
    selector_list: str = Field(..., max_length=500, description="列表项 CSS Selector")
    selector_title: str = Field(..., max_length=500, description="标题 CSS Selector")
    selector_link: str = Field(..., max_length=500, description="链接 CSS Selector")
    selector_summary: str | None = Field(None, max_length=500, description="摘要 CSS Selector（可选）")
    selector_next_page: str | None = Field(None, max_length=500, description="下一页 Selector（可选，CSS 或 json: 路径）")
    keywords: list[str] = Field(default_factory=list, description="关键词列表，空列表 = 全量采集")
    cron_expression: str = Field(..., max_length=100, description="Cron 表达式（5 段）")

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not is_valid_url(v):
            from app.core.exceptions import InvalidURLError
            raise InvalidURLError(f"Invalid URL: {v}")
        return v

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        """验证 Cron 表达式格式（5 段，不含秒）"""
        # 先检查是否是快捷键
        if v in FREQUENCY_PRESETS:
            return FREQUENCY_PRESETS[v]
        parts = v.strip().split()
        if len(parts) != 5:
            from app.core.exceptions import InvalidCronError
            raise InvalidCronError(f"Cron must have 5 fields, got: {v!r}")
        return v.strip()

    @field_validator("template_id")
    @classmethod
    def validate_template(cls, v: str | None) -> str | None:
        if v is not None and v not in PRESET_TEMPLATES:
            raise ValueError(f"Unknown template_id: {v!r}. Valid: {PRESET_TEMPLATES}")
        return v

    @field_validator("selector_list", "selector_title", "selector_link", "selector_summary")
    @classmethod
    def validate_selectors(cls, v: str | None) -> str | None:
        return _validate_selector(v, v or "selector")

    @field_validator("selector_next_page")
    @classmethod
    def validate_next_page(cls, v: str | None) -> str | None:
        return _validate_next_page_selector(v)


class TaskCreate(TaskBase):
    """创建任务请求体"""
    pass


class TaskUpdate(BaseModel):
    """更新任务请求体（所有字段可选，仅提交需要修改的字段）"""
    name: str | None = Field(None, min_length=1, max_length=100)
    source_url: str | None = Field(None, max_length=2048)
    template_id: str | None = None
    selector_list: str | None = Field(None, max_length=500)
    selector_title: str | None = Field(None, max_length=500)
    selector_link: str | None = Field(None, max_length=500)
    selector_summary: str | None = Field(None, max_length=500)
    selector_next_page: str | None = Field(None, max_length=500)
    keywords: list[str] | None = None
    cron_expression: str | None = Field(None, max_length=100)
    status: Literal["active", "paused"] | None = None

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is not None and not is_valid_url(v):
            from app.core.exceptions import InvalidURLError
            raise InvalidURLError(f"Invalid URL: {v}")
        return v

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v in FREQUENCY_PRESETS:
            return FREQUENCY_PRESETS[v]
        parts = v.strip().split()
        if len(parts) != 5:
            from app.core.exceptions import InvalidCronError
            raise InvalidCronError(f"Cron must have 5 fields, got: {v!r}")
        return v.strip()

    @field_validator("template_id")
    @classmethod
    def validate_template(cls, v: str | None) -> str | None:
        if v is not None and v not in PRESET_TEMPLATES:
            raise ValueError(f"Unknown template_id: {v!r}. Valid: {PRESET_TEMPLATES}")
        return v

    @field_validator("selector_list", "selector_title", "selector_link", "selector_summary")
    @classmethod
    def validate_selectors(cls, v: str | None) -> str | None:
        return _validate_selector(v, v or "selector")

    @field_validator("selector_next_page")
    @classmethod
    def validate_next_page(cls, v: str | None) -> str | None:
        return _validate_next_page_selector(v)


class TaskResponse(BaseModel):
    """任务响应体"""
    id: str
    name: str
    source_url: str
    template_id: str | None
    selector_list: str
    selector_title: str
    selector_link: str
    selector_summary: str | None
    selector_next_page: str | None
    keywords: list[str]
    cron_expression: str
    status: str
    consecutive_failures: int
    consecutive_empty: int
    last_executed_at: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class TaskListItem(BaseModel):
    """任务列表摘要（卡片视图用）"""
    id: str
    name: str
    source_url: str
    template_id: str | None
    status: str
    consecutive_failures: int
    consecutive_empty: int
    last_executed_at: str | None
    created_at: str

    model_config = {"from_attributes": True}


class ExecuteTriggerResponse(BaseModel):
    execution_id: str
    message: str
