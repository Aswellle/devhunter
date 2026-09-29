"""
app/schemas/task.py
采集任务 Pydantic 模型：TaskCreate / TaskUpdate / TaskResponse
"""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator
import soupsieve as sv

from app.core.exceptions import InvalidSelectorError
from app.utils.url import is_valid_url

# ── 预设模板标识常量 ──────────────────────────────────────
PRESET_TEMPLATES = {
    # 开发趋势
    "hackernews",
    "hackernews_show",
    "hackernews_ask",
    "github_trending",
    "trending_github_repos",
    "lobsters",
    # 创意发现
    "producthunt",
    "indiehackers",
    "v2ex_create",
    "reddit_sideproject",
    # 社区讨论
    "v2ex",
    "v2ex_jobs",
    "reddit_webdev",
    "reddit_startups",
    # 技术博客
    "devto",
    "hashnode",
    "juejin",
    "sspai",
    "medium_programming",
    # 内容创作（UP主/内容创作者素材）
    "bilibili_comprehensive",
    "bilibili_music",
    "douyin_trending",
    "zhihu_hot",
    # 需求分享
    "reddit_forhire",
    "reddit_ideas",
}


_MAX_SELECTOR_LEN = 500


def _selector_mode(selector_list: str | None) -> str:
    """
    解析模式判定，必须与 engine._parse_mode 保持一致（只看 selector_list 前缀）。

    模式决定 selector_title/link/summary 的语义：
    - html     → CSS 选择器（soupsieve 校验）
    - json     → JSON 路径，link 支持 PREF:prefix|path
    - rss      → 由 feed 自带标题/链接，这三个字段不参与解析
    """
    sl = (selector_list or "").strip()
    if sl.startswith("json-post:"):
        return "json-post"
    if sl.startswith("json:"):
        return "json"
    if sl.startswith("rss:"):
        return "rss"
    return "html"


def _validate_selector_value(v: str, field_name: str, mode: str | None = "html") -> str:
    """
    非空 selector 值校验：长度上限对所有模式生效，仅 html 模式做 CSS 语法校验。

    把 JSON 路径（如 item_info.article_id）或 rss: 模板送进 soupsieve 会误判为
    非法 CSS —— 25 个预设模板里有 10 个会因为这种误判而无法创建（422）。
    mode=None 表示模式未知（局部更新未提交 selector_list），跳过语法校验。
    """
    if len(v) > _MAX_SELECTOR_LEN:
        raise InvalidSelectorError(f"{field_name} 长度超过 {_MAX_SELECTOR_LEN}")
    if mode != "html" or v.startswith("PREF:"):
        return v
    try:
        sv.compile(v)
    except sv.SelectorSyntaxError as e:
        raise InvalidSelectorError(f"{field_name} 不是合法的 CSS 选择器: {e}")
    return v


def _require_selector(v: str | None, field_name: str, mode: str | None = "html") -> str:
    """必填 selector 校验：空值抛 400（而不是让 NULL 一路打到数据库约束）。"""
    if v is None or not v.strip():
        raise InvalidSelectorError(f"{field_name} 不能为空，请先完成自动发现或手动填写")
    return _validate_selector_value(v.strip(), field_name, mode)


def _validate_selector(v: str | None, field_name: str = "selector", mode: str | None = "html") -> str | None:
    """可选 selector 校验：允许 None/空，其余按模式校验。"""
    if v is None or not v.strip():
        return None
    return _validate_selector_value(v.strip(), field_name, mode)


def _validate_next_page_selector(v: str | None, mode: str | None = "html") -> str | None:
    """
    selector_next_page 校验：允许 None/空；JSON/RSS 模式下是 JSON 路径（跳过
    soupsieve），HTML 模式下是 CSS 选择器。json:/json-post: 前缀在任意模式下都放行。
    """
    if v is None or not v.strip():
        return None
    v = v.strip()
    if len(v) > _MAX_SELECTOR_LEN:
        raise InvalidSelectorError(f"selector_next_page 长度超过 {_MAX_SELECTOR_LEN}")
    if mode in ("json", "json-post", "rss") or v.startswith("json:"):
        return v
    if v.startswith("json-post:"):
        return v
    return _validate_selector_value(v, "selector_next_page", "html")


# ── 频率快捷选项 → Cron 表达式映射 ───────────────────────
FREQUENCY_PRESETS: dict[str, str] = {
    "every_30min": "*/30 * * * *",
    "every_hour":  "0 * * * *",
    "every_6h":    "0 */6 * * *",
    "every_day":   "0 9 * * *",
}


def _validate_cron_expression(v: str) -> str:
    """
    C8: 校验 5 段格式 + 字段取值范围（如 "99 * * * *" 应在此处被拒绝为 400，
    而不是让错误一路冒泡到 scheduler_manager.add_job() 才被发现并静默吞掉）。
    复用 APScheduler 的 CronTrigger 做取值范围校验，避免自己重新实现一套规则。
    """
    parts = v.strip().split()
    if len(parts) != 5:
        from app.core.exceptions import InvalidCronError
        raise InvalidCronError(f"Cron must have 5 fields, got: {v!r}")

    from apscheduler.triggers.cron import CronTrigger
    from app.core.exceptions import InvalidCronError
    minute, hour, day, month, day_of_week = parts
    try:
        CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)
    except ValueError as e:
        raise InvalidCronError(f"Invalid cron field value: {e}") from e
    return v.strip()


class TaskBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="任务名称")
    source_url: str = Field(..., max_length=2048, description="目标页面 URL")
    template_id: str | None = Field(None, description="预设模板 ID，None 表示自定义")
    selector_list: str = Field(..., max_length=500, description="列表项 CSS Selector")
    selector_title: str = Field(..., max_length=500, description="标题 CSS Selector")
    selector_link: str = Field(..., max_length=500, description="链接 CSS Selector")
    selector_summary: str | None = Field(None, max_length=500, description="摘要 CSS Selector（可选）")
    selector_next_page: str | None = Field(None, max_length=500, description="下一页 Selector（可选，CSS 或 json: 路径）")
    keywords: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="关键词列表（最多 20 个），空列表 = 全量采集",
    )
    cron_expression: str = Field(..., max_length=100, description="Cron 表达式（5 段）")
    config_snapshot: dict | None = Field(None, description="创建时的模板配置快照（JSON）")

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: list[str]) -> list[str]:
        """验证关键词列表长度和总字符数"""
        if len(v) > 20:
            raise ValueError("关键词数量不能超过 20 个")
        total_chars = sum(len(k) for k in v)
        if total_chars > 500:
            raise ValueError("关键词总字符数不能超过 500")
        return [k.strip() for k in v if k.strip()]

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
        """验证 Cron 表达式格式（5 段 + 字段取值范围，不含秒）"""
        if v in FREQUENCY_PRESETS:
            return FREQUENCY_PRESETS[v]
        return _validate_cron_expression(v)

    @field_validator("template_id")
    @classmethod
    def validate_template(cls, v: str | None) -> str | None:
        if v is not None and v not in PRESET_TEMPLATES:
            raise ValueError(f"Unknown template_id: {v!r}. Valid: {PRESET_TEMPLATES}")
        return v

    @field_validator("selector_list")
    @classmethod
    def validate_selector_list(cls, v: str) -> str:
        """列表 selector 决定解析模式（json: / json-post: / rss: / HTML）。"""
        return _require_selector(v, "selector_list", _selector_mode(v))

    @field_validator("selector_title", "selector_link")
    @classmethod
    def validate_required_selectors(cls, v: str, info: ValidationInfo) -> str:
        return _require_selector(v, info.field_name, _selector_mode(info.data.get("selector_list")))

    @field_validator("selector_summary")
    @classmethod
    def validate_summary_selector(cls, v: str | None, info: ValidationInfo) -> str | None:
        return _validate_selector(v, "selector_summary",
                                  _selector_mode(info.data.get("selector_list")))

    @field_validator("selector_next_page")
    @classmethod
    def validate_next_page(cls, v: str | None, info: ValidationInfo) -> str | None:
        return _validate_next_page_selector(v, _selector_mode(info.data.get("selector_list")))


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
    keywords: list[str] | None = Field(None, max_length=20)
    cron_expression: str | None = Field(None, max_length=100)
    status: Literal["active", "paused"] | None = None

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: list[str] | None) -> list[str] | None:
        """验证关键词列表长度和总字符数"""
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError("关键词数量不能超过 20 个")
        total_chars = sum(len(k) for k in v)
        if total_chars > 500:
            raise ValueError("关键词总字符数不能超过 500")
        return [k.strip() for k in v if k.strip()]

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
        return _validate_cron_expression(v)

    @field_validator("template_id")
    @classmethod
    def validate_template(cls, v: str | None) -> str | None:
        if v is not None and v not in PRESET_TEMPLATES:
            raise ValueError(f"Unknown template_id: {v!r}. Valid: {PRESET_TEMPLATES}")
        return v

    @field_validator("selector_list")
    @classmethod
    def validate_selector_list(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _require_selector(v, "selector_list", _selector_mode(v))

    @field_validator("selector_title", "selector_link")
    @classmethod
    def validate_required_selectors(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is None:
            return None
        # 未同时提交 selector_list 时无法判定解析模式 → 只做非空校验
        mode = _selector_mode(info.data["selector_list"]) if "selector_list" in info.data else None
        return _require_selector(v, info.field_name, mode)

    @field_validator("selector_summary")
    @classmethod
    def validate_summary_selector(cls, v: str | None, info: ValidationInfo) -> str | None:
        mode = _selector_mode(info.data["selector_list"]) if "selector_list" in info.data else None
        return _validate_selector(v, "selector_summary", mode)

    @field_validator("selector_next_page")
    @classmethod
    def validate_next_page(cls, v: str | None, info: ValidationInfo) -> str | None:
        mode = _selector_mode(info.data["selector_list"]) if "selector_list" in info.data else None
        return _validate_next_page_selector(v, mode)


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
    config_snapshot: dict | None = None
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
    selector_list: str
    keywords: list[str]
    cron_expression: str
    status: str
    consecutive_failures: int
    consecutive_empty: int
    last_executed_at: str | None
    created_at: str

    model_config = {"from_attributes": True}


class ExecuteTriggerResponse(BaseModel):
    execution_id: str
    message: str
