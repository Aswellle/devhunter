"""
app/core/logging.py
结构化日志配置 - 支持 JSON 格式和 text 格式
"""
import logging
import sys
from typing import Any

from app.core.config import settings


class _RequestIdFilter(logging.Filter):
    """
    A1: 从 contextvars 注入 request_id 到 log record。
    由 RequestIdMiddleware 在请求处理前设置，确保全链路日志可关联。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        from app.core.request_id import get_current_request_id
        record.request_id = get_current_request_id()
        return True

    """将日志格式化为 JSON 单行输出"""

    def format(self, record: logging.LogRecord) -> str:
        import json
        import traceback

        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 注入上下文字段（task_id, execution_id, request_id 等）
        for key in ("task_id", "execution_id", "request_id", "url"):
            if hasattr(record, key):
                log_data[key] = getattr(record, key)

        if record.exc_info:
            log_data["exc_info"] = traceback.format_exception(*record.exc_info)

        if record.stack_info:
            log_data["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging() -> None:
    """初始化全局日志配置，在 lifespan 启动时调用一次"""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除已有 handler，避免重复
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.addFilter(_RequestIdFilter())
    if settings.log_format == "json":
        handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)

    # 降低第三方库的噪声
    for noisy in ("apscheduler", "httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger"""
    return logging.getLogger(name)
