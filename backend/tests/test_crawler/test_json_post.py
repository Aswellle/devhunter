"""
test_json_post.py — json-post 抓取模式测试。

覆盖：
- POST 请求体来自 mode_extra["post_body"]（回归：曾引用未定义变量导致模式整体坏死）
- json-post 5xx 终态不重试（S6）
"""
import httpx

from app.crawler import engine
from app.crawler.engine import _fetch_page_with_retry, _parse_mode


class _FakeResp:
    """httpx.Response 最小替身：支持状态码 / JSON 体 / 重定向。"""

    def __init__(self, status_code=200, json_body=None, redirect_to=None):
        self.status_code = status_code
        self.reason_phrase = "Reason"
        self._json_body = json_body
        self.content = b"{}" if json_body is not None else b""
        self.encoding = "utf-8"
        self.is_redirect = redirect_to is not None
        self.headers = {"location": redirect_to} if redirect_to else {}
        self.url = "http://example.com/api"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", self.url),
                response=self,  # type: ignore[arg-type]
            )

    def json(self):
        return self._json_body


class _RecordingClient:
    """记录每次调用的 (method, url, json_body)，按脚本返回响应。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url, None))
        return self._responses.pop(0)

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json))
        return self._responses.pop(0)


def test_parse_mode_json_post_extracts_body():
    """json-post:<path>|||<body> 正确拆出路径与请求体。"""
    mode, list_path, extra = _parse_mode('json-post:data.items|||{"page":2}')
    assert mode == "json-post"
    assert list_path == "data.items"
    assert extra == {"post_body": {"page": 2}}


def test_json_post_sends_body_from_mode_extra():
    """POST 请求体取自 mode_extra["post_body"]，成功返回响应。"""
    client = _RecordingClient([_FakeResp(200, json_body={"ok": True})])
    outcome = _fetch_page_with_retry(
        client, "http://example.com/api", "json-post",
        {"post_body": {"page": 2}}, {}, timeout=5.0, on_progress=None,
    )
    assert outcome.error is None
    assert outcome.http_status == 200
    assert client.calls == [("POST", "http://example.com/api", {"page": 2})]


def test_json_post_5xx_is_terminal_no_retry():
    """json-post 5xx 不重试（防重复副作用），单次调用即失败。"""
    client = _RecordingClient([_FakeResp(500)])
    outcome = _fetch_page_with_retry(
        client, "http://example.com/api", "json-post",
        {"post_body": {}}, {}, timeout=5.0, on_progress=None,
    )
    assert outcome.error is not None
    assert "POST 5xx not retried" in outcome.error
    assert len(client.calls) == 1
