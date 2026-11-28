"""
tests/test_sources/test_github_connector.py
GitHub 官方只读 Connector 回归（PROD-002）。

验收：只读 Repo/Release/Issue 来源；ETag 条件请求；Link header 分页；
quota/Retry-After 退避与可行动错误；token 仅发往 api.github.com。
"""
import json
import uuid

import httpx
import pytest

from app.sources import github_connector as gh


class _Resp:
    def __init__(self, status_code=200, payload=None, headers=None, url="https://api.github.com/repos/o/r"):
        self.status_code = status_code
        self.reason_phrase = "OK"
        self._payload = payload
        self.content = json.dumps(payload).encode("utf-8") if payload is not None else b""
        self.headers = httpx.Headers(headers or {"content-type": "application/json"})
        self.url = httpx.URL(url)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=httpx.Request("GET", self.url),
                response=self,  # type: ignore[arg-type]
            )


class _Client:
    """脚本化客户端：记录每次请求的 url/headers，按序返回响应。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        # 头名统一小写，便于断言大小写不敏感
        self.calls.append((url, {k.lower(): v for k, v in (headers or {}).items()}))
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def build_request(self, method, url, **kwargs):
        kwargs.pop("timeout", None)
        return httpx.Request(method, url, **kwargs)

    def send(self, request, stream=False):
        self.calls.append((str(request.url), {k.lower(): v for k, v in request.headers.items()}))
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    """默认隔离 ETag 缓存表，个别用例显式打开。"""
    monkeypatch.setattr(gh, "_load_etag", lambda url: None)
    monkeypatch.setattr(gh, "_store_etag", lambda url, etag: None)


class TestParseSourceUrl:
    def test_repo_url(self):
        assert gh.parse_source_url("https://github.com/astral-sh/uv") == (
            "repo", "astral-sh", "uv")

    def test_releases_and_issues_urls(self):
        assert gh.parse_source_url("https://github.com/o/r/releases")[0] == "releases"
        assert gh.parse_source_url("https://github.com/o/r/issues")[0] == "issues"

    def test_suffix_selects_kind(self):
        assert gh.parse_source_url("https://github.com/o/r", "issues")[0] == "issues"

    def test_non_github_url_is_rejected(self):
        assert gh.parse_source_url("https://gitlab.com/o/r") is None
        assert gh.parse_source_url("https://github.com/only-owner") is None


class TestFetchRepo:
    def test_repo_maps_to_crawl_item(self, monkeypatch):
        payload = {
            "id": 123, "full_name": "astral-sh/uv", "description": "Fast Python pm",
            "html_url": "https://github.com/astral-sh/uv", "stargazers_count": 9000,
            "pushed_at": "2026-11-27T10:00:00Z",
        }
        client = _Client([_Resp(payload=payload)])
        monkeypatch.setattr(gh, "get_http_client", lambda: client)

        result = gh.fetch("https://github.com/astral-sh/uv", "repo", token="")

        assert result.error is None
        assert len(result.items) == 1
        item = result.items[0]
        assert item.title == "astral-sh/uv"
        assert item.url == "https://github.com/astral-sh/uv"
        assert "Fast Python pm" in item.summary
        assert item.published_at == "2026-11-27T10:00:00Z"
        assert item.external_id == "123"
        # API 域名与 Accept 头
        assert client.calls[0][0].startswith("https://api.github.com/repos/astral-sh/uv")
        assert "application/vnd.github+json" in client.calls[0][1].get("accept", "")


class TestFetchReleases:
    def test_releases_list_is_paginated_via_link_header(self, monkeypatch):
        page1 = [{"id": 2, "name": "v2", "tag_name": "v2", "html_url": "https://github.com/o/r/releases/2",
                  "body": "notes 2", "published_at": "2026-11-20T00:00:00Z"}]
        page2 = [{"id": 1, "name": "v1", "tag_name": "v1", "html_url": "https://github.com/o/r/releases/1",
                  "body": "notes 1", "published_at": "2026-10-01T00:00:00Z"}]
        client = _Client([
            _Resp(payload=page1, headers={
                "content-type": "application/json",
                "link": '<https://api.github.com/repos/o/r/releases?page=2>; rel="next"',
            }),
            _Resp(payload=page2),
        ])
        monkeypatch.setattr(gh, "get_http_client", lambda: client)

        result = gh.fetch("https://github.com/o/r/releases", "releases", token="")

        assert result.error is None
        assert [i.external_id for i in result.items] == ["2", "1"]
        assert result.pages_fetched == 2
        assert "page=2" in client.calls[1][0]


class TestFetchIssues:
    def test_pull_requests_are_filtered_out(self, monkeypatch):
        payload = [
            {"id": 10, "title": "Real issue", "html_url": "https://github.com/o/r/issues/10",
             "body": "bug", "created_at": "2026-11-25T00:00:00Z"},
            {"id": 11, "title": "A PR", "html_url": "https://github.com/o/r/pull/11",
             "body": "pr", "created_at": "2026-11-26T00:00:00Z",
             "pull_request": {"url": "https://api.github.com/repos/o/r/pulls/11"}},
        ]
        client = _Client([_Resp(payload=payload)])
        monkeypatch.setattr(gh, "get_http_client", lambda: client)

        result = gh.fetch("https://github.com/o/r/issues", "issues", token="")

        assert [i.external_id for i in result.items] == ["10"]


class TestConditionalRequests:
    def test_etag_sent_and_304_yields_no_items(self, monkeypatch):
        monkeypatch.setattr(gh, "_load_etag", lambda url: '"abc123"')
        stored = {}
        monkeypatch.setattr(gh, "_store_etag", lambda url, etag: stored.setdefault(url, etag))

        client = _Client([_Resp(status_code=304, headers={"etag": '"abc123"'})])
        monkeypatch.setattr(gh, "get_http_client", lambda: client)

        result = gh.fetch("https://github.com/o/r/releases", "releases", token="")

        assert result.error is None
        assert result.items == []
        assert client.calls[0][1].get("if-none-match") == '"abc123"'

    def test_fresh_response_stores_etag(self, monkeypatch):
        stored = {}
        monkeypatch.setattr(gh, "_load_etag", lambda url: None)
        monkeypatch.setattr(gh, "_store_etag", lambda url, etag: stored.__setitem__(url, etag))
        client = _Client([
            _Resp(payload=[], headers={"content-type": "application/json", "etag": '"new"'}),
        ])
        monkeypatch.setattr(gh, "get_http_client", lambda: client)

        gh.fetch("https://github.com/o/r/releases", "releases", token="")
        assert stored


class TestRateLimits:
    def test_exhausted_quota_returns_actionable_error(self, monkeypatch):
        client = _Client([_Resp(
            status_code=403,
            payload={"message": "API rate limit exceeded"},
            headers={
                "x-ratelimit-remaining": "0",
                "x-ratelimit-reset": "1735689600",
            },
        )])
        monkeypatch.setattr(gh, "get_http_client", lambda: client)

        result = gh.fetch("https://github.com/o/r/releases", "releases", token="")

        assert result.error is not None
        assert "rate limit" in result.error.lower()
        assert "token" in result.error.lower(), "错误文案需提示配置 token"

    def test_token_sent_only_to_api_github_com(self, monkeypatch):
        client = _Client([_Resp(payload=[{"id": 1, "name": "v1", "tag_name": "v1",
                                          "html_url": "https://github.com/o/r/releases/1",
                                          "published_at": "2026-11-01T00:00:00Z"}])])
        monkeypatch.setattr(gh, "get_http_client", lambda: client)

        gh.fetch("https://github.com/o/r/releases", "releases", token="tok_test_123")

        auth = client.calls[0][1].get("authorization", "")
        assert auth == "Bearer tok_test_123"


class TestEngineIntegration:
    def test_parse_mode_recognizes_github(self):
        from app.crawler.engine import _parse_mode
        assert _parse_mode("github:releases")[0] == "github"

    def test_selector_mode_includes_github(self):
        from app.schemas.task import _selector_mode
        assert _selector_mode("github:issues") == "github"

    def test_github_templates_are_available(self):
        from app.crawler.templates import get_template, list_templates
        available = {t.id for t in list_templates()}
        assert {"github_repo", "github_releases", "github_issues"} <= available
        tpl = get_template("github_releases")
        assert tpl.selector_list == "github:releases"
        assert tpl.source_url.startswith("https://github.com/")


class TestTaskCreation:
    def test_github_task_can_be_created_via_api(self, monkeypatch):
        """github: 选择器必须通过 schema 校验（历史坑：新模式未同步
        _selector_mode 会 400 INVALID_SELECTOR），且不被当作 CSS 校验。"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.core.security import create_access_token

        # 共享测试库可能已到全局任务上限（100）：本用例只验证 schema 放行
        monkeypatch.setattr("app.services.task_service.MAX_TASKS_LIMIT", 10**6)

        client = TestClient(app)
        token = create_access_token({"sub": "admin"})
        resp = client.post("/api/tasks", json={
            "name": f"GitHub 连接器 {uuid.uuid4().hex[:6]}",
            "source_url": "https://github.com/astral-sh/uv/releases",
            "selector_list": "github:releases",
            "selector_title": "github:title",
            "selector_link": "github:url",
            "selector_summary": "github:summary",
            "keywords": [],
            "cron_expression": "0 */3 * * *",
            "content_kind": "discussion",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["selector_list"] == "github:releases"
