"""
app/core/logging.py
结构化日志配置 - 支持 JSON 格式和 text 格式
"""
import logging
import re
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


# SEC-002：URL query 里的机器令牌不得进入日志（RSS 阅读器/分享链接常带
# ?token=...）。只对消息与参数做模式替换，保留其余诊断信息。
_TOKEN_QUERY_RE = re.compile(r"(token=)[A-Za-z0-9_\-\.]{4,}")


class _TokenRedactionFilter(logging.Filter):
    """把 `token=xxxx` 替换为 `token=***`（消息与 args 都处理）。"""

    @staticmethod
    def _redact(value):
        if isinstance(value, str):
            return _TOKEN_QUERY_RE.sub(lambda m: m.group(1) + "***", value)
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self._redact(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: self._redact(v) for k, v in record.args.items()}
        return True


class JSONFormatter(logging.Formatter):
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
    handler.addFilter(_TokenRedactionFilter())
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
