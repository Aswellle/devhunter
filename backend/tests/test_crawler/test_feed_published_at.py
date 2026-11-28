"""
tests/test_crawler/test_feed_published_at.py
RSS/Atom 原发时间解析测试。

旧实现完全不解析 pubDate/published/updated：原发时间丢失，一周前的
报道刚被抓到就被推荐/Thread 当成全新事件（时间语义全线以 fetched_at
为准）。解析失败必须只损失该字段的时间，绝不能让整个 Feed 失败。
"""
import httpx

from app.crawler.engine import _parse_one_page, _parse_rss_items


def _rss(pub_date: str | None, dc_date: str | None = None) -> str:
    tags = ""
    if pub_date is not None:
        tags += f"<pubDate>{pub_date}</pubDate>"
    if dc_date is not None:
        tags += f"<dc:date>{dc_date}</dc:date>"
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        f"<item><title>storm</title><link>https://e.com/1</link>"
        f"<description>d</description>{tags}</item>"
        "</channel></rss>"
    )


def _atom(published: str | None, updated: str | None = None) -> str:
    pub = f"<published>{published}</published>" if published else ""
    upd = f"<updated>{updated}</updated>" if updated else ""
    return (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
        '<entry><title>t</title><link href="https://e.com/1"/>'
        f"<summary>s</summary>{pub}{upd}</entry></feed>"
    )


class TestRssPubDate:
    def test_rfc822_gmt_is_parsed_to_utc_iso(self):
        items, _ = _parse_rss_items(_rss("Wed, 25 Nov 2026 17:00:00 GMT"), "https://e.com/feed")
        assert items[0].published_at == "2026-11-25T17:00:00Z"

    def test_numeric_timezone_offset_is_normalized_to_utc(self):
        items, _ = _parse_rss_items(_rss("Thu, 26 Nov 2026 01:00:00 +0800"), "https://e.com/feed")
        assert items[0].published_at == "2026-11-25T17:00:00Z"

    def test_missing_pub_date_leaves_published_at_empty(self):
        items, _ = _parse_rss_items(_rss(None), "https://e.com/feed")
        assert items[0].published_at == ""

    def test_invalid_pub_date_does_not_fail_the_feed(self):
        items, count = _parse_rss_items(_rss("not-a-date"), "https://e.com/feed")
        assert count == 1
        assert items[0].title == "storm"
        assert items[0].published_at == ""

    def test_dc_date_iso_is_fallback_when_no_pub_date(self):
        items, _ = _parse_rss_items(
            _rss(None, dc_date="2026-11-25T17:00:00Z"), "https://e.com/feed",
        )
        assert items[0].published_at == "2026-11-25T17:00:00Z"


class TestAtomTimes:
    def test_published_is_parsed(self):
        items, _ = _parse_rss_items(
            _atom("2026-11-25T17:00:00Z"), "https://e.com/feed",
        )
        assert items[0].published_at == "2026-11-25T17:00:00Z"

    def test_updated_is_fallback_when_published_missing(self):
        items, _ = _parse_rss_items(
            _atom(None, updated="2026-11-24T10:00:00Z"), "https://e.com/feed",
        )
        assert items[0].published_at == "2026-11-24T10:00:00Z"

    def test_offset_is_normalized_to_utc(self):
        items, _ = _parse_rss_items(
            _atom("2026-11-25T19:00:00+02:00"), "https://e.com/feed",
        )
        assert items[0].published_at == "2026-11-25T17:00:00Z"

    def test_invalid_atom_date_keeps_entry(self):
        items, count = _parse_rss_items(_atom("garbage"), "https://e.com/feed")
        assert count == 1
        assert items[0].published_at == ""


class TestEngineRssMode:
    def test_parse_one_page_carries_published_at(self):
        response = httpx.Response(
            200,
            content=_rss("Wed, 25 Nov 2026 17:00:00 GMT").encode("utf-8"),
            request=httpx.Request("GET", "https://e.com/feed"),
        )
        parsed, raw_count, _anchor = _parse_one_page(
            response,
            mode="rss",
            list_path="",
            selectors={},
            base_url="https://e.com/feed",
            on_progress=None,
            parse_start=0.0,
        )
        assert raw_count == 1
        assert parsed[0].published_at == "2026-11-25T17:00:00Z"
