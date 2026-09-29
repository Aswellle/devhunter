"""
app/core/error_messages.py
内部错误文本 → 面向用户的错误分类与提示。

执行失败时要落库/推送两条不同用途的信息：

- **给用户看的**：分类码（写入 task_executions.last_error_code）+ 中文提示，
  不含异常类名、重试次数、内部路径等实现细节。
- **给排查用的**：原始错误文本只进服务端日志（调用方负责 logger.warning/exception）。

引擎的 error 字段形如::

    "failed after 3 attempt(s), last error: Connection error: RemoteProtocolError: ..."
    "HTTP 403 Forbidden"
    "Timeout after 15.0s"
    "SSRF blocked: ..."
"""
import re

# ── 分类码（与 migrations/015 的注释保持同一套命名）────────
NETWORK = "NETWORK"
TIMEOUT = "TIMEOUT"
SSRF_BLOCKED = "SSRF_BLOCKED"
HTTP_ERROR = "HTTP_ERROR"
RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
CONFIG_INCOMPLETE = "CONFIG_INCOMPLETE"
TASK_NOT_FOUND = "TASK_NOT_FOUND"
TASK_PAUSED = "TASK_PAUSED"
INTERNAL = "INTERNAL"
UNKNOWN = "UNKNOWN"

_HTTP_RE = re.compile(r"HTTP\s+(\d{3})")

# 常见状态码的通俗解释；未覆盖的走兜底文案
_HTTP_HINTS = {
    400: "目标站点拒绝了该请求（400），请检查来源 URL 与请求参数",
    401: "目标站点要求登录（401），该来源需要鉴权",
    403: "目标站点拒绝访问（403），可能需要调整请求头或降低抓取频率",
    404: "目标地址不存在（404），请确认来源 URL 是否正确",
    429: "目标站点限流（429），请降低抓取频率后重试",
}

# 已是对用户友好的固定文案，原样保留
_PASSTHROUGH_PREFIXES = (
    "任务配置不完整",
)


def classify_error(raw: str | None) -> tuple[str, str]:
    """
    返回 (分类码, 面向用户的提示)。

    注意：调用方必须把 `raw` 写进服务端日志，这里只负责"能展示什么"。
    """
    text = (raw or "").strip()
    if not text:
        return UNKNOWN, "抓取失败，详细信息请查看服务端日志"

    for prefix in _PASSTHROUGH_PREFIXES:
        if text.startswith(prefix):
            return CONFIG_INCOMPLETE, text

    lowered = text.lower()

    if "ssrf" in lowered:
        return SSRF_BLOCKED, "目标地址被安全策略拦截：只允许抓取公开的 http/https 地址"

    if "task is paused" in lowered:
        return TASK_PAUSED, "任务已暂停，本次触发已跳过"

    if "task not found" in lowered:
        return TASK_NOT_FOUND, "任务不存在或已被删除，请刷新页面"

    if "too large" in lowered:
        return RESPONSE_TOO_LARGE, (
            "响应体超过大小上限，已中止本次抓取（可通过环境变量 "
            "CRAWLER_MAX_RESPONSE_MB 调整上限）"
        )

    status_match = _HTTP_RE.search(text)
    if status_match:
        code = status_match.group(1)
        hint = _HTTP_HINTS.get(int(code))
        if hint is None:
            hint = (
                "目标站点暂时不可用（HTTP {code}），稍后会自动重试".format(code=code)
                if code.startswith("5")
                else "目标站点返回 HTTP {code}，请检查来源配置".format(code=code)
            )
        return f"HTTP_{code}", hint

    if "timeout" in lowered:
        return TIMEOUT, "连接超时：目标站点响应过慢或被网络阻断"

    if "certificate" in lowered or "ssl" in lowered:
        return NETWORK, "TLS 握手失败（证书校验不通过），无法安全连接目标站点"

    if "connection" in lowered or "disconnected" in lowered or "network" in lowered:
        return NETWORK, "无法连接到目标站点（连接被拒绝或中断）"

    return INTERNAL, "抓取失败，详细信息请查看服务端日志"
