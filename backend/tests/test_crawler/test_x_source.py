"""
tests/test_crawler/test_x_source.py
X（推特）公开时间线适配器与内置模板测试。
"""
import json
import uuid
from datetime import datetime, timezone

import httpx

from app.crawler.engine import (
    _parse_mode,
    _parse_one_page,
    _rate_limit_delay,
    MAX_429_RETRY_DELAY_SECONDS,
)
from app.crawler.x_source import (
    normalize_x_source_url,
    parse_x_timeline,
)
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo


def _tweet(
    tweet_id: str,
    text: str,
    *,
    reply_to: str | None = None,
    retweet: bool = False,
    media: bool = False,
    video: bool = False,
    screen_name: str = "BBCWorld",
) -> dict:
    entities: dict = {"urls": [{
        "url": "https://t.co/abc",
        "display_url": "bbc.in/storm",
        "expanded_url": "https://bbc.in/storm",
    }]}
    if media:
        entities["media"] = [{
            "url": "https://t.co/media",
            "type": "video" if video else "photo",
        }]
    tweet = {
        "id_str": tweet_id,
        "full_text": text,
        "created_at": "Wed Nov 25 17:00:00 +0000 2026",
        "user": {"screen_name": screen_name, "name": screen_name},
        "entities": entities,
        "favorite_count": 1200,
        "retweet_count": 30,
        "reply_count": 5,
        "lang": "en",
    }
    if reply_to:
        tweet["in_reply_to_status_id_str"] = reply_to
    if retweet:
        tweet["retweeted_status"] = {"id_str": "parent"}
    return tweet


def _syndication_html(tweets: list[dict]) -> str:
    payload = {
        "props": {
            "pageProps": {
                "timeline": {
                    "entries": [
                        {"type": "tweet", "content": {"tweet": tweet}}
                        for tweet in tweets
                    ]
                }
            }
        }
    }
    return (
        "<html><body>"
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script></body></html>"
    )


class TestXUrlNormalization:
    def test_profile_hosts_are_rewritten_to_syndication(self):
        for url in (
            "https://x.com/BBCWorld",
            "https://twitter.com/BBCWorld",
            "https://x.com/@BBCWorld/",
        ):
            assert normalize_x_source_url(url) == (
                "https://syndication.twitter.com/srv/timeline-profile/"
                "screen-name/BBCWorld?showReplies=false"
            )

    def test_existing_syndication_url_is_kept(self):
        url = (
            "https://syndication.twitter.com/srv/timeline-profile/"
            "screen-name/BBCWorld?showReplies=false"
        )
        assert normalize_x_source_url(url) == url

    def test_status_search_and_reserved_paths_are_rejected(self):
        for url in (
            "https://x.com/BBCWorld/status/123",
            "https://x.com/search?q=OpenAI",
            "https://x.com/i/lists/1",
            "https://example.com/BBCWorld",
        ):
            assert normalize_x_source_url(url) is None


class TestParseXTimeline:
    def test_parses_original_posts_and_filters_replies_retweets(self):
        html = _syndication_html([
            _tweet("1001", "Breaking &amp; live: storm hits https://t.co/abc https://t.co/media",
                   media=True),
            _tweet("1002", "reply text", reply_to="1001"),
            _tweet("1003", "retweet text", retweet=True),
            _tweet("1004", "Video only", media=True, video=True),
        ])

        posts, raw_count = parse_x_timeline(
            html, "https://syndication.twitter.com/srv/timeline-profile/screen-name/BBCWorld",
        )

        assert raw_count == 4
        assert [p["title"] for p in posts] == [
            "Breaking & live: storm hits bbc.in/storm [图片]",
            "Video only [视频]",
        ]
        assert posts[0]["url"] == "https://x.com/BBCWorld/status/1001"
        assert posts[0]["external_id"] == "1001"
        assert posts[0]["published_at"] == "2026-11-25T17:00:00Z"
        assert "@BBCWorld" in posts[0]["summary"]
        assert "1.2k 赞" in posts[0]["summary"]
        assert "2026-11-25 17:00 UTC" in posts[0]["summary"]

    def test_malformed_or_missing_next_data_returns_empty(self):
        assert parse_x_timeline("", "https://x.com/BBCWorld") == ([], 0)
        assert parse_x_timeline("<html>no data</html>", "https://x.com/BBCWorld") == ([], 0)
        assert parse_x_timeline(
            '<script id="__NEXT_DATA__" type="application/json">{bad}</script>',
            "https://x.com/BBCWorld",
        ) == ([], 0)

    def test_engine_x_mode_parses_syndication_html(self):
        html = _syndication_html([_tweet("2001", "Hello from X")])
        response = httpx.Response(
            200,
            content=html.encode("utf-8"),
            request=httpx.Request("GET", "https://x.com/BBCWorld"),
        )

        parsed, raw_count, anchor = _parse_one_page(
            response,
            mode="x",
            list_path="",
            selectors={"title": "x:text", "link": "x:url", "summary": "x:meta"},
            base_url="https://x.com/BBCWorld",
            on_progress=None,
            parse_start=0.0,
        )

        assert raw_count == 1
        assert anchor is None
        assert parsed[0].title == "Hello from X"
        assert parsed[0].url == "https://x.com/BBCWorld/status/2001"
        assert parsed[0].external_id == "2001"
        assert parsed[0].published_at == "2026-11-25T17:00:00Z"

    def test_x_mode_detection(self):
        assert _parse_mode("x:") == ("x", "", {})
        assert _parse_mode("x:profile") == ("x", "", {})

    def test_rate_limit_delay_uses_retry_after_and_caps_reset(self):
        retry_after = httpx.Response(
            429, headers={"retry-after": "7"},
            request=httpx.Request("GET", "https://x.com/BBCWorld"),
        )
        assert _rate_limit_delay(retry_after) == 7.0

        far_reset = httpx.Response(
            429, headers={"x-rate-limit-reset": str(int(datetime.now(timezone.utc).timestamp()) + 3600)},
            request=httpx.Request("GET", "https://x.com/BBCWorld"),
        )
        assert _rate_limit_delay(far_reset) == MAX_429_RETRY_DELAY_SECONDS


class TestXPublishedAtPersistence:
    def test_bulk_insert_persists_published_at(self):
        task_id = task_repo.insert({
            "name": f"X published_at {uuid.uuid4().hex[:6]}",
            "source_url": "https://example.com/",
            "template_id": None,
            "selector_list": "x:",
            "selector_title": "x:text",
            "selector_link": "x:url",
            "selector_summary": "x:meta",
            "selector_next_page": None,
            "keywords": [],
            "cron_expression": "0 9 * * *",
        })["id"]
        item_id = str(uuid.uuid4())
        item_repo.bulk_insert([{
            "id": item_id,
            "task_id": task_id,
            "title": "tweet",
            "url": "https://x.com/BBCWorld/status/3001",
            "url_hash": f"x-published-{item_id}",
            "summary": "@BBCWorld",
            "published_at": "2026-11-25T17:00:00Z",
            "fetched_at": "2026-11-27T10:00:00Z",
        }])

        item = item_repo.get(item_id)
        assert item is not None
        assert item["published_at"] == "2026-11-25T17:00:00Z"
        assert item["fetched_at"] == "2026-11-27T10:00:00Z"
