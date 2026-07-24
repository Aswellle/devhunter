"""
app/core/exceptions.py
自定义异常类与错误码定义
"""
from typing import Any


class DevHunterError(Exception):
    """所有业务异常的基类"""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred"

    def __init__(self, message: str | None = None, **kwargs: Any):
        self.message = message or self.__class__.message
        self.extra = kwargs
        super().__init__(self.message)


# ── 4xx 客户端错误 ────────────────────────────────────────

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
