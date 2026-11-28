"""
tests/test_api/test_opportunities_api.py
机会板回归（PROD-005）。

验收：可关联 Item 或 Thread；状态流转有审计记录；笔记/标签/提醒可写；
任何操作都能回到原始证据。
"""
import uuid

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.thread_repo import thread_repo

client = TestClient(app)


def _auth():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


def _item() -> str:
    task_id = task_repo.insert({
        "name": f"机会源 {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })["id"]
    item_id = str(uuid.uuid4())
    item_repo.bulk_insert([{
        "id": item_id, "task_id": task_id,
        "title": "Pain point: no CLI for X",
        "url": f"https://example.com/opp/{item_id}",
        "url_hash": f"opp-{item_id}", "summary": "users complain",
    }])
    return item_id


def _thread() -> str:
    item_id = _item()
    thread_id = thread_repo.create("Cross-platform event", item_id, "HN")
    return thread_id


class TestCreateFromOrigin:
    def test_create_from_item_returns_evidence(self):
        item_id = _item()
        resp = client.post("/api/opportunities", json={
            "origin_type": "item", "origin_id": item_id,
            "opportunity_type": "user_problem", "priority": "high",
        }, headers=_auth())
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["origin_type"] == "item"
        assert body["status"] == "inbox"
        assert body["evidence"]["type"] == "item"
        assert body["evidence"]["url"].startswith("https://example.com/opp/")
        assert body["title"], "未给标题时应继承证据标题"

    def test_create_from_thread(self):
        thread_id = _thread()
        resp = client.post("/api/opportunities", json={
            "origin_type": "thread", "origin_id": thread_id,
            "opportunity_type": "trend",
        }, headers=_auth())
        assert resp.status_code == 201
        body = resp.json()
        assert body["evidence"]["type"] == "thread"
        assert body["evidence"]["id"] == thread_id

    def test_unknown_origin_is_rejected(self):
        resp = client.post("/api/opportunities", json={
            "origin_type": "item", "origin_id": "missing-id",
        }, headers=_auth())
        assert resp.status_code == 400


class TestAuditTrail:
    def test_status_transition_writes_audit_event(self):
        item_id = _item()
        opp = client.post("/api/opportunities", json={
            "origin_type": "item", "origin_id": item_id,
        }, headers=_auth()).json()

        resp = client.patch(f"/api/opportunities/{opp['id']}",
                            json={"status": "investigating"}, headers=_auth())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "investigating"

        events = body["events"]
        status_events = [e for e in events if e["event_type"] == "status_change"]
        assert status_events, "状态流转必须有审计记录"
        evt = status_events[-1]
        assert evt["from_value"] == "inbox"
        assert evt["to_value"] == "investigating"

    def test_notes_tags_remind_are_recorded(self):
        item_id = _item()
        opp = client.post("/api/opportunities", json={
            "origin_type": "item", "origin_id": item_id,
        }, headers=_auth()).json()

        body = client.patch(f"/api/opportunities/{opp['id']}", json={
            "notes": "validate with 5 users",
            "tags": ["cli", "devtools"],
            "remind_at": "2026-12-01T09:00:00Z",
        }, headers=_auth()).json()

        assert body["notes"] == "validate with 5 users"
        assert body["tags"] == ["cli", "devtools"]
        assert body["remind_at"] == "2026-12-01T09:00:00Z"
        kinds = {e["event_type"] for e in body["events"]}
        assert {"note", "tags", "remind"} <= kinds

    def test_priority_change_audited(self):
        item_id = _item()
        opp = client.post("/api/opportunities", json={
            "origin_type": "item", "origin_id": item_id,
        }, headers=_auth()).json()
        body = client.patch(f"/api/opportunities/{opp['id']}",
                            json={"priority": "high"}, headers=_auth()).json()
        evt = [e for e in body["events"] if e["event_type"] == "priority_change"][-1]
        assert (evt["from_value"], evt["to_value"]) == ("normal", "high")


class TestListing:
    def test_list_filters_by_status(self):
        item_id = _item()
        opp = client.post("/api/opportunities", json={
            "origin_type": "item", "origin_id": item_id, "status": "planned",
        }, headers=_auth()).json()

        planned = client.get("/api/opportunities?status=planned", headers=_auth()).json()
        assert any(o["id"] == opp["id"] for o in planned)
        inbox = client.get("/api/opportunities?status=inbox", headers=_auth()).json()
        assert not any(o["id"] == opp["id"] for o in inbox)

    def test_list_includes_evidence(self):
        item_id = _item()
        client.post("/api/opportunities", json={
            "origin_type": "item", "origin_id": item_id,
        }, headers=_auth())
        rows = client.get("/api/opportunities", headers=_auth()).json()
        row = next(o for o in rows if o["origin_id"] == item_id)
        assert row["evidence"]["id"] == item_id


class TestDelete:
    def test_delete_opportunity(self):
        item_id = _item()
        opp = client.post("/api/opportunities", json={
            "origin_type": "item", "origin_id": item_id,
        }, headers=_auth()).json()
        assert client.delete(f"/api/opportunities/{opp['id']}",
                             headers=_auth()).status_code == 204
        assert client.get(f"/api/opportunities/{opp['id']}",
                          headers=_auth()).status_code == 404
