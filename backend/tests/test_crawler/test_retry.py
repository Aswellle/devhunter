"""
test_retry.py — Unit tests for _fetch_page_with_retry (Fetch Resilience).

Covers:
- 500x2 then 200 → success with retries_used=2
- 500x3 → failure, error mentions attempts, retries_used=2
- 404 → no retry (terminal), immediate failure, retries_used=0
- network error (RequestError) then 200 → retries_used=1
"""
import httpx
import pytest

from app.crawler import engine
from app.crawler.engine import _fetch_page_with_retry, _FetchOutcome


class _FakeResponse:
    """Minimal stand-in for httpx.Response for status-based tests."""

    def __init__(self, status_code: int, reason_phrase: str = "Reason", json_body=None):
        self.status_code = status_code
        self.reason_phrase = reason_phrase
        self._json_body = json_body
        self.content = b"{}" if json_body is not None else b"<html></html>"
        self.encoding = "utf-8"
        self.headers = httpx.Headers()

    def iter_bytes(self, chunk_size: int = 65536):
        yield self.content

    def close(self):
        pass

    def raise_for_status(self):
        if 400 <= self.status_code:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "http://x/"),
                response=self,  # type: ignore[arg-type]
            )

    def json(self):
        if self._json_body is None:
            raise ValueError("no json")
        return self._json_body


class _ScriptedClient:
    """httpx.Client stand-in that returns a scripted sequence of responses.

    Exception instances in the script are raised; _FakeResponse instances
    are returned. Supports both the high-level get/post and the low-level
    build_request/send interface used by _fetch_bounded.
    """

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls = 0

    def get(self, url, headers=None, timeout=None):
        return self._next()

    def post(self, url, json=None, headers=None, timeout=None):
        return self._next()

    def build_request(self, method, url, **kwargs):
        return httpx.Request(method, url)

    def send(self, request, stream=False):
        return self._next()

    def _next(self):
        self.calls += 1
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make retry delays instant so tests run fast."""
    monkeypatch.setattr(engine.time, "sleep", lambda *_a, **_k: None)


def _make_client(responses):
    return _ScriptedClient(responses)


def test_retry_succeeds_after_two_500s():
    """500, 500, 200 → success, retries_used=2 (two extra attempts)."""
    client = _make_client([
        _FakeResponse(500), _FakeResponse(500), _FakeResponse(200, json_body={}),
    ])
    outcome = _fetch_page_with_retry(
        client, "http://example.com/", "json", {}, {}, timeout=5.0, on_progress=None,
    )
    assert outcome.error is None
    assert outcome.retries_used == 2
    assert outcome.http_status == 200


def test_retry_exhausted_on_three_500s():
    """500, 500, 500 → failure after 3 attempts, retries_used=2."""
    client = _make_client([_FakeResponse(500)] * 3)
    outcome = _fetch_page_with_retry(
        client, "http://example.com/", "json", {}, {}, timeout=5.0, on_progress=None,
    )
    assert outcome.error is not None
    assert "3 attempt(s)" in outcome.error
    assert outcome.retries_used == 2


def test_404_is_terminal_no_retry():
    """404 → terminal, no retry, immediate failure."""
    client = _make_client([_FakeResponse(404)])
    outcome = _fetch_page_with_retry(
        client, "http://example.com/", "json", {}, {}, timeout=5.0, on_progress=None,
    )
    assert outcome.error is not None
    assert outcome.retries_used == 0
    assert outcome.http_status == 404


def test_network_error_then_success():
    """RequestError then 200 → retries_used=1."""
    client = _make_client([
        httpx.ConnectError("connection refused"),
        _FakeResponse(200, json_body={}),
    ])
    outcome = _fetch_page_with_retry(
        client, "http://example.com/", "json", {}, {}, timeout=5.0, on_progress=None,
    )
    assert outcome.error is None
    assert outcome.retries_used == 1


def test_retry_exhausted_on_network_errors():
    """3 x ConnectError → failure after 3 attempts."""
    client = _make_client([httpx.ConnectError("refused")] * 3)
    outcome = _fetch_page_with_retry(
        client, "http://example.com/", "json", {}, {}, timeout=5.0, on_progress=None,
    )
    assert outcome.error is not None
    assert "3 attempt(s)" in outcome.error
