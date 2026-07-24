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
        # engine reads response.content (truncation) — provide a tiny body
        self.content = b"{}" if json_body is not None else b"<html></html>"
        self.encoding = "utf-8"

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

    Raises are produced by the response's raise_for_status(), so the retry
    wrapper sees the same exceptions it would in production.
    """

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls = 0

    def get(self, url, headers=None, timeout=None):
        return self._next()

    def post(self, url, json=None, headers=None, timeout=None):
        return self._next()

    def _next(self):
        self.calls += 1
        return self._responses.pop(0)


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
    assert outcome.response is not None
    assert outcome.response.status_code == 200
    assert outcome.retries_used == 2
    assert client.calls == 3


def test_retry_exhausted_on_three_500s():
    """500, 500, 500 → failure, error mentions attempts, retries_used=2."""
    client = _make_client([_FakeResponse(500), _FakeResponse(500), _FakeResponse(500)])
    outcome = _fetch_page_with_retry(
        client, "http://example.com/", "json", {}, {}, timeout=5.0, on_progress=None,
    )
    assert outcome.error is not None
    assert outcome.response is None
    assert "attempt" in outcome.error.lower()
    assert "500" in outcome.error
    assert outcome.retries_used == 2  # 2 extra attempts beyond the first
    assert client.calls == 3


def test_404_is_terminal_no_retry():
    """404 → immediate failure, NO retry, retries_used=0, only 1 call."""
    client = _make_client([_FakeResponse(404)])
    outcome = _fetch_page_with_retry(
        client, "http://example.com/", "json", {}, {}, timeout=5.0, on_progress=None,
    )
    assert outcome.error is not None
    assert "404" in outcome.error
    # 4xx must not be framed as retry exhaustion
    assert "attempt" not in outcome.error.lower()
    assert outcome.retries_used == 0
    assert client.calls == 1  # terminal — no retries issued


def test_network_error_then_success():
    """RequestError then 200 → success with retries_used=1."""
    class _BoomResponse(_FakeResponse):
        def raise_for_status(self):
            raise httpx.RequestError("connection reset", request=httpx.Request("GET", "http://x/"))

    client = _make_client([_BoomResponse(200), _FakeResponse(200, json_body={})])
    outcome = _fetch_page_with_retry(
        client, "http://example.com/", "json", {}, {}, timeout=5.0, on_progress=None,
    )
    assert outcome.error is None
    assert outcome.retries_used == 1
    assert client.calls == 2


def test_retry_exhausted_on_network_errors():
    """Three RequestErrors → failure with attempt wording."""
    class _BoomResponse(_FakeResponse):
        def raise_for_status(self):
            raise httpx.RequestError("connection reset", request=httpx.Request("GET", "http://x/"))

    client = _make_client([_BoomResponse(200), _BoomResponse(200), _BoomResponse(200)])
    outcome = _fetch_page_with_retry(
        client, "http://example.com/", "json", {}, {}, timeout=5.0, on_progress=None,
    )
    assert outcome.error is not None
    assert "attempt" in outcome.error.lower()
    assert outcome.retries_used == 2
