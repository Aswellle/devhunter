"""
tests/test_sources/test_reddit_connector.py
Reddit 官方 OAuth Connector 回归（PROD-004）。

验收：OAuth（application-only）接入；配额与 Retry-After 退避；
TTL 删除同步；数据用途限制在文档/配置中明确。
本环境没有 Reddit 应用凭据，真实 OAuth 端到端标记 NOT RUN，
以脚本化 client 覆盖协议行为。
"""
import json
import uuid

import httpx
import pytest

from app.sources import reddit_connector as rd


class _Resp:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self.reason_phrase = "OK"
        self._payload = payload
        self.content = json.dumps(payload).encode() if payload is not None else b""
        self.headers = httpx.Headers(headers or {"content-type": "application/json"})

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "https://oauth.reddit.com/"),
                response=self,  # type: ignore[arg-type]
            )


class _Client:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, data=None, auth=None, headers=None, timeout=None):
        self.calls.append(("POST", url, data, dl := dict(headers or {}), auth))
        return self._next()

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, params, dict(headers or {}), None))
        return self._next()

    def _next(self):
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture(autouse=True)
def _clear_token(monkeypatch):
    rd._TOKEN_CACHE.clear()


class TestParseSourceUrl:
    def test_subreddit_url(self):
        assert rd.parse_source_url("https://www.reddit.com/r/rust/") == "rust"
        assert rd.parse_source_url("https://reddit.com/r/rust/new") == "rust"

    def test_non_subreddit_rejected(self):
        assert rd.parse_source_url("https://www.reddit.com/user/foo") is None
        assert rd.parse_source_url("https://example.com/r/rust") is None


class TestOAuth:
    def test_client_credentials_token_is_fetched_and_cached(self, monkeypatch):
        client = _Client([
            _Resp(payload={"access_token": "tok", "expires_in": 3600}),
            _Resp(payload={"data": {"children": []}}),
            _Resp(payload={"data": {"children": []}}),
        ])
        monkeypatch.setattr(rd, "get_http_client", lambda: client)
        monkeypatch.setattr(rd.settings, "reddit_client_id", "cid")
        monkeypatch.setattr(rd.settings, "reddit_client_secret", "csecret")

        rd.fetch("https://www.reddit.com/r/rust/", mode="new")
        rd.fetch("https://www.reddit.com/r/rust/", mode="new")

        token_calls = [c for c in client.calls if "access_token" in c[1]]
        assert len(token_calls) == 1, "token 必须缓存复用"
        assert token_calls[0][3].get("User-Agent") or token_calls[0][3].get("user-agent")
        assert token_calls[0][2]["grant_type"] == "client_credentials"

    def test_missing_credentials_returns_actionable_error(self, monkeypatch):
        monkeypatch.setattr(rd.settings, "reddit_client_id", "")
        monkeypatch.setattr(rd.settings, "reddit_client_secret", "")
        result = rd.fetch("https://www.reddit.com/r/rust/")
        assert result.error is not None
        assert "REDDIT_CLIENT_ID" in result.error


class TestListing:
    def _listing(self, children):
        return {"data": {"children": [
            {"kind": "t3", "data": c} for c in children
        ]}}

    def test_posts_map_to_crawl_items(self, monkeypatch):
        client = _Client([
            _Resp(payload={"access_token": "t", "expires_in": 3600}),
            _Resp(payload=self._listing([{
                "id": "abc", "title": "Rust news", "permalink": "/r/rust/comments/abc/x/",
                "selftext": "body text", "created_utc": 1764000000,
                "subreddit": "rust", "stickied": False,
            }])),
        ])
        monkeypatch.setattr(rd, "get_http_client", lambda: client)
        monkeypatch.setattr(rd.settings, "reddit_client_id", "cid")
        monkeypatch.setattr(rd.settings, "reddit_client_secret", "csecret")

        result = rd.fetch("https://www.reddit.com/r/rust/", mode="new")

        assert result.error is None
        item = result.items[0]
        assert item.title == "Rust news"
        assert item.url == "https://www.reddit.com/r/rust/comments/abc/x/"
        assert item.external_id == "abc"
        assert item.published_at == "2025-11-24T16:00:00Z"  # 1764000000 的 UTC 表示
        assert "body text" in item.summary
        # OAuth API 域名
        assert "oauth.reddit.com" in client.calls[1][1]

    def test_stickied_posts_are_skipped(self, monkeypatch):
        client = _Client([
            _Resp(payload={"access_token": "t", "expires_in": 3600}),
            _Resp(payload=self._listing([
                {"id": "s1", "title": "Pinned rules", "permalink": "/r/rust/s1",
                 "created_utc": 1764000000, "stickied": True},
                {"id": "n1", "title": "Real post", "permalink": "/r/rust/n1",
                 "created_utc": 1764000001, "stickied": False},
            ])),
        ])
        monkeypatch.setattr(rd, "get_http_client", lambda: client)
        monkeypatch.setattr(rd.settings, "reddit_client_id", "cid")
        monkeypatch.setattr(rd.settings, "reddit_client_secret", "csecret")

        result = rd.fetch("https://www.reddit.com/r/rust/", mode="new")
        assert [i.external_id for i in result.items] == ["n1"]


class TestRateLimits:
    def test_retry_after_is_honored_once(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr(rd.time, "sleep", lambda s: sleeps.append(s))
        client = _Client([
            _Resp(payload={"access_token": "t", "expires_in": 3600}),
            _Resp(status_code=429, headers={"retry-after": "3"}),
            _Resp(payload={"data": {"children": []}}),
        ])
        monkeypatch.setattr(rd, "get_http_client", lambda: client)
        monkeypatch.setattr(rd.settings, "reddit_client_id", "cid")
        monkeypatch.setattr(rd.settings, "reddit_client_secret", "csecret")

        result = rd.fetch("https://www.reddit.com/r/rust/", mode="new")

        assert result.error is None
        assert sleeps and sleeps[0] == 3.0

    def test_deleted_or_forbidden_returns_clear_error(self, monkeypatch):
        client = _Client([
            _Resp(payload={"access_token": "t", "expires_in": 3600}),
            _Resp(status_code=403, payload={"message": "Forbidden"}),
        ])
        monkeypatch.setattr(rd, "get_http_client", lambda: client)
        monkeypatch.setattr(rd.settings, "reddit_client_id", "cid")
        monkeypatch.setattr(rd.settings, "reddit_client_secret", "csecret")

        result = rd.fetch("https://www.reddit.com/r/private/", mode="new")
        assert result.error is not None
        assert "403" in result.error


class TestRetentionJob:
    def test_ttl_job_deletes_only_reddit_items(self, monkeypatch):
        """TTL 删除同步：按任务来源删除超期 Reddit 条目，不影响其他来源。"""
        from app.core.database import get_db
        from app.repositories.item_repo import item_repo
        from app.repositories.task_repo import task_repo
        from app.scheduler import reddit_retention

        monkeypatch.setattr("app.services.task_service.MAX_TASKS_LIMIT", 10**6)
        reddit_task = task_repo.insert({
            "name": f"r/rust {uuid.uuid4().hex[:6]}",
            "source_url": "https://www.reddit.com/r/rust/",
            "selector_list": "reddit:new",
            "selector_title": "reddit:title",
            "selector_link": "reddit:url",
            "cron_expression": "0 * * * *",
        })["id"]
        other_task = task_repo.insert({
            "name": f"HN {uuid.uuid4().hex[:6]}",
            "source_url": "https://news.ycombinator.com/",
            "selector_list": "div",
            "selector_title": "h2",
            "selector_link": "a",
            "cron_expression": "0 * * * *",
        })["id"]

        old_reddit = str(uuid.uuid4())
        old_other = str(uuid.uuid4())
        item_repo.bulk_insert([
            {"id": old_reddit, "task_id": reddit_task, "title": "old reddit",
             "url": f"https://reddit.com/{old_reddit}", "url_hash": f"rr-{old_reddit}",
             "fetched_at": "2026-01-01T00:00:00Z"},
            {"id": old_other, "task_id": other_task, "title": "old hn",
             "url": f"https://example.com/{old_other}", "url_hash": f"rr-{old_other}",
             "fetched_at": "2026-01-01T00:00:00Z"},
        ])

        monkeypatch.setattr(rd.settings, "reddit_item_ttl_days", 30)
        deleted = reddit_retention.purge_expired_reddit_items()

        assert deleted >= 1
        assert item_repo.get(old_reddit) is None
        assert item_repo.get(old_other) is not None, "非 Reddit 来源不得清理"


class TestEngineIntegration:
    def test_parse_mode_and_selector_mode(self):
        from app.crawler.engine import _parse_mode
        from app.schemas.task import _selector_mode
        assert _parse_mode("reddit:new")[0] == "reddit"
        assert _selector_mode("reddit:new") == "reddit"

    def test_template_available(self):
        from app.crawler.templates import get_template
        tpl = get_template("reddit_official")
        assert tpl is not None
        assert tpl.selector_list.startswith("reddit:")
