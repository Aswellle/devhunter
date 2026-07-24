"""
test_pagination.py — Unit tests for pagination orchestration (_paginate / fetch_and_parse).

Covers:
- 3-page mock site → pages_fetched=3, items merged, 3 page_fetched events
- duplicate page (page 3 == page 2) → loop guard stops at page 3
- no selector_next_page → pages_fetched=1 (no regression)
- page cap: 11 pages available but MAX_PAGES=10 → stops at 10
- retry per page: page 2 transient 500 then 200 → continues to page 3
- any page exhausts retries → whole crawl failure, no items
"""
import httpx
import pytest

from app.crawler import engine
from app.crawler.engine import fetch_and_parse, CrawlResult


def _html_page(items: list[tuple[str, str]], next_href: str | None = None) -> bytes:
    """Build a tiny HTML page with list items and an optional next-page link.

    items: list of (title, url). The selector list is `.item`, title `.t`, link `a`.
    """
    rows = "".join(
        f'<div class="item"><span class="t">{t}</span><a href="{u}">{t}</a></div>'
        for t, u in items
    )
    next_link = f'<a class="next" href="{next_href}">next</a>' if next_href else ""
    return f"<html><body>{rows}{next_link}</body></html>".encode("utf-8")


class _FakeResponse:
    def __init__(self, status_code: int, body: bytes, content_type: str = "text/html"):
        self.status_code = status_code
        self.reason_phrase = "OK"
        self.content = body
        self.encoding = "utf-8"
        self.headers = httpx.Headers({"content-type": content_type})

    def raise_for_status(self):
        if 400 <= self.status_code:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "http://x/"),
                response=self,  # type: ignore[arg-type]
            )

    def json(self):
        raise ValueError("not json")


class _ScriptedClient:
    """Returns a scripted sequence of responses, one per HTTP call."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls = 0

    def get(self, url, headers=None, timeout=None):
        self.calls += 1
        return self._responses.pop(0)

    def post(self, url, json=None, headers=None, timeout=None):
        return self.get(url, headers, timeout)


def _selectors(next_page: str | None = None) -> dict:
    s = {"list": ".item", "title": ".t", "link": "a", "summary": None}
    if next_page is not None:
        s["next_page"] = next_page
    return s


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    """No real sleeping; no real network."""
    monkeypatch.setattr(engine.time, "sleep", lambda *_a, **_k: None)
    # SSRF: allow http://example.com/* (resolves to a real public IP in CI, but
    # to be deterministic, stub the SSRF check to always pass for these tests).
    monkeypatch.setattr(engine, "_is_ssrf_safe_url", lambda url: (True, ""))
    # Site-specific headers: keep empty for the fake domain.
    monkeypatch.setattr(engine, "_get_extra_headers", lambda url: {})


def _install_client(monkeypatch, responses):
    client = _ScriptedClient(responses)
    monkeypatch.setattr(engine, "get_http_client", lambda: client)
    return client


def test_three_pages_merge_and_events(monkeypatch):
    """3 pages, each with 2 distinct items + a next link → pages_fetched=3, 6 items, 3 events."""
    pages = [
        _FakeResponse(200, _html_page([("a1", "http://example.com/a1"), ("a2", "http://example.com/a2")], "/p2")),
        _FakeResponse(200, _html_page([("b1", "http://example.com/b1"), ("b2", "http://example.com/b2")], "/p3")),
        _FakeResponse(200, _html_page([("c1", "http://example.com/c1")], None)),
    ]
    client = _install_client(monkeypatch, pages)

    events: list[tuple] = []
    def cb(et, msg, data):
        events.append((et, data))

    result = fetch_and_parse(
        "http://example.com/p1", _selectors(".next"), keywords=[],
        on_progress=cb,
    )
    assert result.success
    assert result.pages_fetched == 3
    assert len(result.items) == 5  # 2 + 2 + 1, all distinct
    assert client.calls == 3
    page_events = [e for e in events if e[0] == "page_fetched"]
    # 3 page_fetched events (one per page) — the 4th would be the loop-guard one,
    # but here pagination stops on empty next selector, so exactly 3.
    assert len(page_events) == 3
    # event data carries page number + retries_used
    assert page_events[0][1]["page"] == 1
    assert page_events[0][1]["retries_used"] == 0
    assert page_events[2][1]["page"] == 3


def test_loop_guard_stops_on_duplicate_page(monkeypatch):
    """Page 3 returns the same items as page 2 → loop guard stops at page 3."""
    dup_items = [("x1", "http://example.com/x1"), ("x2", "http://example.com/x2")]
    pages = [
        _FakeResponse(200, _html_page([("a1", "http://example.com/a1")], "/p2")),
        _FakeResponse(200, _html_page(dup_items, "/p3")),
        _FakeResponse(200, _html_page(dup_items, "/p4")),  # same items as page 2
        _FakeResponse(200, _html_page([("never", "http://example.com/never")], None)),
    ]
    client = _install_client(monkeypatch, pages)

    result = fetch_and_parse("http://example.com/p1", _selectors(".next"), keywords=[])
    assert result.success
    assert result.pages_fetched == 3  # stopped at page 3 (duplicate of page 2)
    assert client.calls == 3  # page 4 never fetched


def test_no_next_page_selector_single_page(monkeypatch):
    """No selector_next_page → pages_fetched=1, only one fetch (no regression)."""
    pages = [_FakeResponse(200, _html_page([("a1", "http://example.com/a1")], "/p2"))]
    client = _install_client(monkeypatch, pages)

    result = fetch_and_parse("http://example.com/p1", _selectors(next_page=None), keywords=[])
    assert result.success
    assert result.pages_fetched == 1
    assert client.calls == 1
    assert len(result.items) == 1


def test_page_cap_at_max_pages(monkeypatch):
    """11 pages available but MAX_PAGES=10 → stops at 10 pages."""
    # Each page links to the next; all distinct items.
    pages = []
    for i in range(11):
        pages.append(_FakeResponse(
            200,
            _html_page([(f"item{i}", f"http://example.com/item{i}")], f"/p{i+2}"),
        ))
    client = _install_client(monkeypatch, pages)

    result = fetch_and_parse("http://example.com/p1", _selectors(".next"), keywords=[])
    assert result.success
    assert result.pages_fetched == 10
    assert client.calls == 10  # 11th page never fetched
    assert len(result.items) == 10


def test_retry_per_page_then_continue(monkeypatch):
    """Page 2 transient 500 then 200 → page 2 retries, then page 3 continues."""
    pages = [
        _FakeResponse(200, _html_page([("a1", "http://example.com/a1")], "/p2")),
        _FakeResponse(500, b""),  # page 2 attempt 1 fails
        _FakeResponse(200, _html_page([("b1", "http://example.com/b1")], "/p3")),  # page 2 retry succeeds
        _FakeResponse(200, _html_page([("c1", "http://example.com/c1")], None)),
    ]
    client = _install_client(monkeypatch, pages)

    result = fetch_and_parse("http://example.com/p1", _selectors(".next"), keywords=[])
    assert result.success
    assert result.pages_fetched == 3
    assert result.retries_used == 1  # one retry on page 2
    assert client.calls == 4  # 1 (p1) + 2 (p2: 500 then 200) + 1 (p3)


def test_page_exhaustion_whole_crawl_failure(monkeypatch):
    """Page 2 exhausts all 3 retries → whole crawl failure, no items saved."""
    pages = [
        _FakeResponse(200, _html_page([("a1", "http://example.com/a1")], "/p2")),
        _FakeResponse(500, b""), _FakeResponse(500, b""), _FakeResponse(500, b""),  # page 2 ×3
    ]
    client = _install_client(monkeypatch, pages)

    result = fetch_and_parse("http://example.com/p1", _selectors(".next"), keywords=[])
    assert not result.success
    assert result.error is not None
    assert "attempt" in result.error.lower()
    assert result.pages_fetched == 2  # failure happened on page 2
    assert result.retries_used == 2
    assert len(result.items) == 0  # no partial save
