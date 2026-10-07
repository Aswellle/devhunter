"""
app/core/exceptions.py
自定义异常类与错误码定义
"""
from typing import Any




# ── 4xx 客户端错误 ────────────────────────────────────────


class DevHunterError(Exception):
    """所有业务异常的基类"""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred"

    def __init__(self, message: str | None = None, **kwargs: Any):
        self.message = message or self.__class__.message
        self.extra = kwargs
        super().__init__(self.message)

    @property
    def details(self) -> dict:
        """A2: 额外错误详情，会出现在统一错误响应中。"""
        return dict(self.extra) if self.extra else {}

class BadRequestError(DevHunterError):
    status_code = 400
    error_code = "BAD_REQUEST"
    message = "Bad request"


class InvalidCronError(BadRequestError):
    error_code = "INVALID_CRON"
    message = "Invalid cron expression"


class InvalidSelectorError(BadRequestError):
    error_code = "INVALID_SELECTOR"
    message = "Invalid CSS selector"


class InvalidTaskConfigError(BadRequestError):
    error_code = "INVALID_TASK_CONFIG"
    message = "Task configuration is incomplete"


class InvalidURLError(BadRequestError):
    error_code = "URL_INVALID"
    message = "Invalid URL format"


class UnauthorizedError(DevHunterError):
    status_code = 401
    error_code = "UNAUTHORIZED"
    message = "Authentication required"


class NotFoundError(DevHunterError):
    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found"


class TaskNotFoundError(NotFoundError):
    error_code = "TASK_NOT_FOUND"
    message = "Task not found"


class ItemNotFoundError(NotFoundError):
    error_code = "ITEM_NOT_FOUND"
    message = "Item not found"


class ConflictError(DevHunterError):
    status_code = 409
    error_code = "CONFLICT"
    message = "Resource conflict"


class TaskAlreadyRunningError(ConflictError):
    error_code = "TASK_ALREADY_RUNNING"
    message = "Task is already running, please wait"


class TaskLimitExceededError(ConflictError):
    error_code = "TASK_LIMIT_EXCEEDED"
    message = "Maximum number of tasks reached"


# ── LLM 功能 ─────────────────────────────────────────────

class LLMNotConfiguredError(ConflictError):
    error_code = "LLM_NOT_CONFIGURED"
    message = "尚未接入 AI，请先在「我的画像 → AI 接入」完成配置"


class LLMUnavailableError(ConflictError):
    error_code = "LLM_UNAVAILABLE"
    message = "AI 暂不可用（预算已用尽或连续失败熔断），请稍后再试"


class DigestTooFewItemsError(ConflictError):
    error_code = "TOO_FEW_ITEMS"
    message = "该热点只有一条内容，暂不生成综述"


class DigestGenerationFailedError(DevHunterError):
    status_code = 503
    error_code = "DIGEST_GENERATION_FAILED"
    message = "综述生成失败，请稍后重试"
