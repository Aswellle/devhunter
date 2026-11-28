"""
tests/test_sources/test_opml.py
OPML 导入/导出回归（PROD-001）。

验收：导入前解析 + SSRF 校验；预览来源清单与重复项；
导入为 Draft（paused，不启用定时抓取）；导出已启用 Feed。
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.repositories.task_repo import task_repo
from app.sources import opml

client = TestClient(app)


def _auth():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


_OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>My Feeds</title></head>
  <body>
    <outline text="Tech">
      <outline type="rss" text="Hacker News" title="Hacker News"
               xmlUrl="https://news.ycombinator.com/rss" htmlUrl="https://news.ycombinator.com/"/>
      <outline type="rss" text="Lobsters" xmlUrl="https://lobste.rs/rss"/>
    </outline>
    <outline type="rss" text="No URL"/>
  </body>
</opml>"""


class TestParseOpml:
    def test_parses_nested_outlines(self):
        entries = opml.parse_opml(_OPML)
        assert [e["xml_url"] for e in entries] == [
            "https://news.ycombinator.com/rss",
            "https://lobste.rs/rss",
        ]
        assert entries[0]["title"] == "Hacker News"
        # 无 xmlUrl 的 outline 被跳过（不是可订阅来源）
        assert all(e["xml_url"] for e in entries)

    def test_malformed_xml_raises_value_error(self):
        with pytest.raises(ValueError):
            opml.parse_opml("<opml><body><outline")
        with pytest.raises(ValueError):
            opml.parse_opml("")

    def test_outline_without_any_feeds_returns_empty(self):
        xml = '<opml version="2.0"><body><outline text="folder"/></body></opml>'
        assert opml.parse_opml(xml) == []


class TestExportOpml:
    def _task(self, url: str, selectors: str, status: str, name: str) -> str:
        return task_repo.insert({
            "name": f"{name} {uuid.uuid4().hex[:6]}",
            "source_url": url,
            "selector_list": selectors,
            "selector_title": "rss:title" if selectors == "rss:" else "h2",
            "selector_link": "rss:link" if selectors == "rss:" else "a",
            "cron_expression": "0 9 * * *",
            "status": status,
        })["id"]

    def test_export_contains_active_feed_tasks_only(self):
        feed_active = self._task("https://feed.example.com/a.xml", "rss:", "active", "Active Feed")
        feed_paused = self._task("https://feed.example.com/b.xml", "rss:", "paused", "Paused Feed")
        html_active = self._task("https://site.example.com/list", "div", "active", "HTML")

        xml_text = opml.export_opml(task_repo.list_all_tasks())

        assert "https://feed.example.com/a.xml" in xml_text
        assert "https://feed.example.com/b.xml" not in xml_text, "草稿/暂停的 Feed 不导出"
        assert "https://site.example.com/list" not in xml_text, "非 feed 任务不导出"
        # 合法 OPML
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        assert root.tag == "opml"
        outlines = [o.get("xmlUrl") for o in root.iter("outline") if o.get("xmlUrl")]
        # 共享测试库还有本文件/其他用例创建的 active feed，只断言本用例的
        # 归属：active 在、paused 与 HTML 不在
        assert "https://feed.example.com/a.xml" in outlines
        assert "https://feed.example.com/b.xml" not in outlines
        assert "https://site.example.com/list" not in outlines


class TestOpmlPreviewApi:
    def test_preview_lists_entries_with_duplicate_flags(self, monkeypatch):
        # 已存在同名来源 → 标记重复
        task_repo.insert({
            "name": f"已存在 {uuid.uuid4().hex[:6]}",
            "source_url": "https://news.ycombinator.com/rss",
            "selector_list": "rss:",
            "selector_title": "rss:title",
            "selector_link": "rss:link",
            "cron_expression": "0 9 * * *",
        })
        monkeypatch.setattr(opml, "_validate_url_safe", lambda url: (True, ""))

        resp = client.post("/api/sources/opml/preview",
                           json={"content": _OPML}, headers=_auth())
        assert resp.status_code == 200
        body = resp.json()
        by_url = {e["xml_url"]: e for e in body["entries"]}
        assert by_url["https://news.ycombinator.com/rss"]["duplicate"] is True
        assert by_url["https://lobste.rs/rss"]["duplicate"] is False
        assert body["duplicates"] == 1

    def test_preview_flags_ssrf_blocked_entries(self, monkeypatch):
        monkeypatch.setattr(
            opml, "_validate_url_safe",
            lambda url: (False, "private network") if "192.168" in url else (True, ""),
        )
        xml_text = (
            '<opml version="2.0"><body>'
            '<outline type="rss" text="Internal" xmlUrl="http://192.168.1.5/feed"/>'
            "</body></opml>"
        )
        resp = client.post("/api/sources/opml/preview",
                           json={"content": xml_text}, headers=_auth())
        body = resp.json()
        assert body["entries"][0]["safe"] is False
        assert "private network" in body["entries"][0]["error"]

    def test_preview_rejects_malformed_opml(self):
        resp = client.post("/api/sources/opml/preview",
                           json={"content": "not xml"}, headers=_auth())
        assert resp.status_code == 400


class TestOpmlImportApi:
    def test_import_creates_paused_draft_tasks(self, monkeypatch):
        monkeypatch.setattr(opml, "_validate_url_safe", lambda url: (True, ""))
        # 共享测试库累积的任务可能已到全局上限（100）：本用例验证导入
        # 映射与草稿语义，限流本身由 task_service 测试覆盖
        monkeypatch.setattr(
            "app.services.task_service.MAX_TASKS_LIMIT", 10**6)
        urls = [
            f"https://feed.example.com/{uuid.uuid4().hex[:6]}.xml",
            f"https://feed.example.com/{uuid.uuid4().hex[:6]}.xml",
        ]
        resp = client.post("/api/sources/opml/import", json={
            "entries": [
                {"xml_url": urls[0], "title": "导入 A"},
                {"xml_url": urls[1], "title": "导入 B"},
            ],
        }, headers=_auth())
        assert resp.status_code == 201
        body = resp.json()
        assert body["created"] == 2

        tasks = {t["source_url"]: t for t in task_repo.list_all_tasks()}
        for url in urls:
            task = tasks[url]
            assert task["status"] == "paused", "导入必须是草稿，不启用定时抓取"
            assert task["selector_list"] == "rss:"
            assert task["template_id"] is None

    def test_import_skips_duplicate_and_unsafe_urls(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.task_service.MAX_TASKS_LIMIT", 10**6)
        existing_url = f"https://feed.example.com/{uuid.uuid4().hex[:6]}.xml"
        task_repo.insert({
            "name": "已存在来源",
            "source_url": existing_url,
            "selector_list": "rss:",
            "selector_title": "rss:title",
            "selector_link": "rss:link",
            "cron_expression": "0 9 * * *",
        })
        monkeypatch.setattr(
            opml, "_validate_url_safe",
            lambda url: (False, "blocked") if "10." in url else (True, ""),
        )
        new_url = f"https://feed.example.com/{uuid.uuid4().hex[:6]}.xml"
        resp = client.post("/api/sources/opml/import", json={
            "entries": [
                {"xml_url": existing_url, "title": "重复"},
                {"xml_url": "http://10.0.0.1/rss", "title": "内网"},
                {"xml_url": new_url, "title": "新来源"},
            ],
        }, headers=_auth())
        assert resp.status_code == 201
        body = resp.json()
        assert body["created"] == 1
        assert body["skipped_duplicate"] == 1
        assert body["skipped_unsafe"] == 1
        assert any(t["source_url"] == new_url for t in task_repo.list_all_tasks())


class TestOpmlExportApi:
    def test_export_endpoint_returns_opml(self):
        task_repo.insert({
            "name": f"导出源 {uuid.uuid4().hex[:6]}",
            "source_url": f"https://feed.example.com/export/{uuid.uuid4().hex[:6]}.xml",
            "selector_list": "rss:",
            "selector_title": "rss:title",
            "selector_link": "rss:link",
            "cron_expression": "0 9 * * *",
            "status": "active",
        })
        resp = client.get("/api/sources/opml/export", headers=_auth())
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/x-opml")
        assert "<opml" in resp.text
