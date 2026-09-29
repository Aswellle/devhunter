"""
tests/test_core/test_error_messages.py
错误分类器：面向用户的提示不得泄漏实现细节。

执行历史面板直接渲染 task_executions.error_message，所以落库的必须是
分类后的中文文案；异常类名（RemoteProtocolError）、重试细节（attempt(s)）、
堆栈等只允许出现在服务端日志里。
"""
import pytest

from app.core import error_messages as em


class TestClassifyError:
    def test_empty_error_falls_back_to_generic(self):
        assert em.classify_error(None) == (em.UNKNOWN, "抓取失败，详细信息请查看服务端日志")
        assert em.classify_error("   ")[0] == em.UNKNOWN

    def test_http_status_is_classified_with_code(self):
        code, message = em.classify_error("HTTP 403 Forbidden")
        assert code == "HTTP_403"
        assert "403" in message and "拒绝访问" in message

    def test_http_5xx_suggests_retry(self):
        code, message = em.classify_error("HTTP 503 Service Unavailable")
        assert code == "HTTP_503"
        assert "稍后" in message

    def test_unknown_http_code_still_gives_status(self):
        code, message = em.classify_error("HTTP 418 I'm a teapot")
        assert code == "HTTP_418"
        assert "418" in message

    def test_timeout(self):
        code, message = em.classify_error("failed after 3 attempt(s), last error: Timeout after 15.0s")
        assert code == em.TIMEOUT
        assert "超时" in message

    def test_connection_error_hides_exception_class(self):
        raw = ("failed after 3 attempt(s), last error: Connection error: "
               "RemoteProtocolError: Server disconnected without sending a response.")
        code, message = em.classify_error(raw)

        assert code == em.NETWORK
        for leaked in ("RemoteProtocolError", "attempt", "disconnected", "Connection error"):
            assert leaked not in message, f"用户文案泄漏了内部细节: {leaked}"

    def test_ssl_failure_is_network(self):
        code, message = em.classify_error("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        assert code == em.NETWORK
        assert "证书" in message

    def test_ssrf_block(self):
        code, message = em.classify_error("SSRF blocked: 禁止访问私有网段")
        assert code == em.SSRF_BLOCKED
        assert "安全策略" in message

    def test_response_too_large_mentions_env_var(self):
        code, message = em.classify_error("Response too large: Content-Length 999 exceeds limit")
        assert code == em.RESPONSE_TOO_LARGE
        assert "CRAWLER_MAX_RESPONSE_MB" in message

    def test_config_incomplete_passes_through(self):
        code, message = em.classify_error("任务配置不完整，缺少：列表项 Selector")
        assert code == em.CONFIG_INCOMPLETE
        assert message == "任务配置不完整，缺少：列表项 Selector"

    def test_internal_exception_hides_type_and_value(self):
        code, message = em.classify_error("ValueError: secret internal path C:/x/y/z")
        assert code == em.INTERNAL
        assert "ValueError" not in message
        assert "C:/x/y/z" not in message

    @pytest.mark.parametrize("raw", [
        "HTTP 403 Forbidden",
        "Timeout after 15.0s",
        "Connection error: ReadTimeout: ...",
        "SSRF blocked: x",
    ])
    def test_messages_are_user_facing_chinese(self, raw):
        _, message = em.classify_error(raw)
        assert message and any("\u4e00" <= ch <= "\u9fff" for ch in message)
