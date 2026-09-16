"""
app/core/request_id.py
A1: X-Request-ID 中间件 — 为每个请求生成/透传关联 ID，
用于日志、错误响应、execution event 的全链路追踪。
"""
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_current_request_id() -> str:
    """获取当前异步上下文的 request_id，无上下文时返回 'system'。"""
    return _request_id_ctx.get() or "system"


def set_current_request_id(request_id: str) -> None:
    """设置当前异步上下文的 request_id。"""
    _request_id_ctx.set(request_id)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    读取客户端传入的 X-Request-ID，若无则生成 UUID v4。
    将 ID 注入 request.state.request_id，供日志和错误处理使用。
    同时在响应头中回传 X-Request-ID，便于客户端关联。
    同时设置 contextvars，使异步日志能自动关联 request_id。
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        token = _request_id_ctx.set(request_id)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            _request_id_ctx.reset(token)
