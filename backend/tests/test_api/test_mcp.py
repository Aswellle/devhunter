"""
tests/test_api/test_mcp.py
MCP server API 测试：POST /api/mcp（Streamable HTTP + 机器令牌认证）

MCP 传输层要求应用 lifespan 已运行（session manager），
因此这里用 `with TestClient(app)` 触发完整生命周期，
并把调度器启停 mock 掉以避免测试库上的后台线程。
"""
import json
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import machine_token
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo

PROTOCOL_VERSION = "2025-06-18"


def _rpc(method: str, params: dict | None = None, rpc_id: int | None = 1) -> dict:
    payload: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    if rpc_id is not None:
        payload["id"] = rpc_id
    return payload


@pytest.fixture(scope="module")
def mcp_client():
    """
    带 lifespan 的 TestClient（调度器 mock，避免后台线程）。

    module 级：StreamableHTTPSessionManager.run() 每实例只能执行一次，
    每个测试都进出 lifespan 会让第二个及之后的用例拿到已关闭的 task group。
    """
    from app.main import app

    with patch("app.main.scheduler_manager.start"), \
         patch("app.main.scheduler_manager.restore_jobs"), \
         patch("app.main.scheduler_manager.shutdown"):
        with TestClient(app) as c:
            yield c


def _post(client: TestClient, payload: dict) -> object:
    return client.post(
        "/api/mcp",
        content=json.dumps(payload),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        },
        params={"token": machine_token()},
    )


def _seed_item(title: str) -> None:
    task_id = task_repo.insert({
        "name": f"mcp 任务 {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })["id"]
    token = uuid.uuid4().hex[:8]
    item_repo.bulk_insert([{
        "task_id": task_id,
        "title": title,
        "url": f"https://example.com/mcp/{token}",
        "url_hash": f"mcp-hash-{token}",
        "summary": f"summary of {title}",
        "fetched_at": "2026-10-07T08:00:00Z",
    }])


class TestMcpAuth:
    """MCP 端点认证"""

    def test_rejects_without_token(self, mcp_client):
        """无令牌 → 401"""
        response = mcp_client.post(
            "/api/mcp",
            content=json.dumps(_rpc("initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            })),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        assert response.status_code == 401

    def test_rejects_wrong_token(self, mcp_client):
        """错误令牌 → 401"""
        response = mcp_client.post(
            "/api/mcp?token=wrong",
            content=json.dumps(_rpc("initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            })),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        assert response.status_code == 401


class TestMcpTools:
    """MCP 工具调用"""

    def test_initialize_and_list_tools(self, mcp_client):
        """initialize 握手 + tools/list 返回全部六只读工具"""
        resp = _post(mcp_client, _rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1"},
        }))
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["protocolVersion"] == PROTOCOL_VERSION
        assert data["result"]["serverInfo"]["name"] == "devhunter"

        resp = _post(mcp_client, _rpc("tools/list"))
        tools = {t["name"] for t in resp.json()["result"]["tools"]}
        assert tools == {
            "latest_items", "search_items", "list_threads",
            "get_thread", "get_stats", "list_tasks",
        }

    def test_call_search_items(self, mcp_client):
        """tools/call search_items 返回结构化内容"""
        _seed_item("MCP searchable payload xyzq")
        resp = _post(mcp_client, _rpc("tools/call", {
            "name": "search_items",
            "arguments": {"query": "xyzq", "limit": 5},
        }))
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert not result.get("isError", False)
        texts = [c["text"] for c in result["content"] if c["type"] == "text"]
        assert texts and "xyzq" in texts[0]

    def test_call_latest_items(self, mcp_client):
        """tools/call latest_items 返回最新条目"""
        _seed_item("MCP latest item abcw")
        resp = _post(mcp_client, _rpc("tools/call", {
            "name": "latest_items",
            "arguments": {"limit": 5},
        }))
        assert resp.status_code == 200
        texts = [c["text"] for c in resp.json()["result"]["content"]]
        assert any("latest item abcw" in t for t in texts)

    def test_call_get_stats(self, mcp_client):
        """tools/call get_stats 返回统计结构"""
        resp = _post(mcp_client, _rpc("tools/call", {"name": "get_stats", "arguments": {}}))
        assert resp.status_code == 200
        texts = [c["text"] for c in resp.json()["result"]["content"]]
        stats = json.loads(texts[0])
        assert "total_items" in stats and "tasks_by_status" in stats
