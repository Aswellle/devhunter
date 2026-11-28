"""
tests/test_crawler/test_redirect_semantics.py
重定向安全语义回归（GET / json-post POST）。

旧实现：重定向循环对每一跳重复"同一 method + 同一 body + 全部自定义头"，
完全无视 301/302/303（应降级 GET、丢弃 body）与 307/308（跨域不得携带
请求体/敏感头）的语义差异，站点专用头（referer/api-key/内部标识）会随
重定向泄露到任意第三方主机。
"""
import httpx
import pytest

from app.crawler import engine
from app.crawler.engine import _fetch_page_with_retry


class _RedirectResp:
    """httpx.Response 最小替身：可指定自身 URL 以模拟跨域跳转。"""

    def __init__(self, status_code, url, body=b"{}", location=None):
        self.status_code = status_code
        self.reason_phrase = "Reason"
        self.url = httpx.URL(url)
        self.content = body
        self.encoding = "utf-8"
        self.is_redirect = location is not None
        self.headers = httpx.Headers(
            {"location": location} if location else {}
        )

    def iter_bytes(self, chunk_size: int = 65536):
        yield self.content

    def close(self):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", self.url),
                response=self,  # type: ignore[arg-type]
            )

    def json(self):
        import json as _json
        return _json.loads(self.content.decode("utf-8") or "{}")


class _RecordingClient:
    """记录每次请求的 (method, url, body, headers)，按脚本返回响应。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def build_request(self, method, url, **kwargs):
        kwargs.pop("timeout", None)
        return httpx.Request(method, url, **kwargs)

    def send(self, request, stream=False):
        import json as _json
        body = None
        if request.content:
            try:
                body = _json.loads(request.content)
            except Exception:
                body = request.content
        self.calls.append((request.method, str(request.url), body, dict(request.headers)))
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture(autouse=True)
def _no_net(monkeypatch):
    monkeypatch.setattr(engine.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(engine, "resolve_and_validate_url",
                        lambda url: (True, "", None))
    monkeypatch.setattr(engine, "_get_extra_headers", lambda url: {"x-api-key": "sekret"})


def _run(client, mode="json-post", url="http://example.com/api"):
    outcome = _fetch_page_with_retry(
        client, url, mode, {"post_body": {"q": 1}},
        {"x-api-key": "sekret"}, 5.0, None,
    )
    return outcome, client.calls


class TestPostRedirectSemantics:
    def test_302_downgrades_to_get_without_body_or_secrets(self):
        """POST → 302 跳转：下一跳必须是 GET、无请求体、不携带站点专用头。"""
        client = _RecordingClient([
            _RedirectResp(302, "http://example.com/api", location="http://example.com/v2"),
            _RedirectResp(200, "http://example.com/v2", body=b'{"ok": 1}'),
        ])
        outcome, calls = _run(client)

        assert outcome.error is None
        assert len(calls) == 2
        method, hop_url, body, headers = calls[1]
        assert method == "GET"
        assert hop_url == "http://example.com/v2"
        assert body is None
        assert "x-api-key" not in headers

    def test_303_also_downgrades_to_get(self):
        client = _RecordingClient([
            _RedirectResp(303, "http://example.com/api", location="http://example.com/v2"),
            _RedirectResp(200, "http://example.com/v2"),
        ])
        outcome, calls = _run(client)
        assert outcome.error is None
        assert calls[1][0] == "GET"
        assert calls[1][2] is None

    def test_307_same_origin_keeps_post_body(self):
        """307 同源：保留 POST 方法与请求体。"""
        client = _RecordingClient([
            _RedirectResp(307, "http://example.com/api", location="http://example.com/api2"),
            _RedirectResp(200, "http://example.com/api2"),
        ])
        outcome, calls = _run(client)
        assert outcome.error is None
        method, hop_url, body, headers = calls[1]
        assert method == "POST"
        assert body == {"q": 1}

    def test_307_cross_origin_is_refused(self):
        """跨域 307/308：跟随意味着把请求体和内部头发给第三方——必须拒绝。"""
        client = _RecordingClient([
            _RedirectResp(307, "http://example.com/api",
                          location="http://other.example.net/hook"),
        ])
        outcome, calls = _run(client)

        assert outcome.error is not None
        assert "cross-origin" in outcome.error.lower()
        assert len(calls) == 1, "不得向跨域目标发起第二跳"


class TestGetRedirectHeaders:
    def test_cross_origin_get_hop_drops_custom_headers(self):
        """GET 跨域跳转：站点专用头（含内部 api-key）不得转发给第三方。"""
        client = _RecordingClient([
            _RedirectResp(302, "http://example.com/feed",
                          location="http://cdn.example.net/file"),
            _RedirectResp(200, "http://cdn.example.net/file", body=b"<html/>"),
        ])
        outcome, calls = _run(client, mode="rss", url="http://example.com/feed")

        assert outcome.error is None
        method, hop_url, body, headers = calls[1]
        assert method == "GET"
        assert "x-api-key" not in headers

    def test_same_origin_get_hop_keeps_custom_headers(self):
        """同源跳转保持既有行为：站点专用头继续携带。"""
        client = _RecordingClient([
            _RedirectResp(302, "http://example.com/feed",
                          location="http://example.com/feed2"),
            _RedirectResp(200, "http://example.com/feed2", body=b"<html/>"),
        ])
        outcome, calls = _run(client, mode="rss", url="http://example.com/feed")

        assert outcome.error is None
        assert calls[1][3].get("x-api-key") == "sekret"
