"""
app/api/mcp_server.py
MCP (Model Context Protocol) server：让 Claude 等 LLM 客户端直接查询 DevHunter 的聚合库。

- 传输：Streamable HTTP，挂载到 /api/mcp（main.py 中 app.mount）
- 工具集（只读）：latest_items / search_items / list_threads / get_thread /
  get_stats / list_tasks——全部复用现有服务层，与 Web API 同一套数据语义
- 认证：与 RSS 共用的机器能力令牌（?token= 或 Authorization: Bearer），
  在 ASGI 包装层校验；令牌派生见 core/security.machine_token
"""
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl

from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.core.database import get_db
from app.core.security import verify_machine_token
from app.repositories.task_repo import task_repo
from app.services.item_service import item_service
from app.services.thread_service import thread_service

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "devhunter",
    json_response=True,
    stateless_http=True,
    # 关闭 SDK 的 DNS rebinding 防护：该防护只放行 localhost Host，会破坏
    # 反向代理（域名 Host）部署；本端点的访问控制由 ASGI 包装层的
    # 机器能力令牌承担（浏览器跨站请求拿不到令牌，等价于 CSRF 防线）。
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


# ── 工具实现 ─────────────────────────────────────────────
# 注意：工具函数保持同步——SQLite 服务层非线程安全依赖 get_db 的每调用连接，
# FastMCP 会把同步工具放入工作线程执行。


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), 100))


def _compact_item(item: dict[str, Any]) -> dict[str, Any]:
    """条目的对外紧凑视图（不暴露内部状态字段）"""
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "url": item.get("url"),
        "summary": item.get("summary") or "",
        "task_name": item.get("task_name"),
        "fetched_at": item.get("fetched_at"),
        "is_read": bool(item.get("is_read", 0)),
        "is_starred": bool(item.get("is_starred", 0)),
    }


@mcp.tool()
def latest_items(limit: int = 20, task_id: str | None = None) -> dict[str, Any]:
    """获取最新采集的内容条目，可按数据源 task_id 过滤。"""
    items, total = item_service.list_items(
        task_id=task_id, page=1, per_page=_clamp_limit(limit)
    )
    return {"total": total, "items": [_compact_item(i) for i in items]}


@mcp.tool()
def search_items(query: str, limit: int = 20) -> dict[str, Any]:
    """全文搜索采集内容（FTS5，查询失败自动回退 LIKE）。"""
    items, total = item_service.list_items(
        search=query, page=1, per_page=_clamp_limit(limit)
    )
    return {"query": query, "total": total, "items": [_compact_item(i) for i in items]}


@mcp.tool()
def list_threads(limit: int = 20) -> dict[str, Any]:
    """列出跨平台事件 Thread（多平台聚合），按最新事件倒序。"""
    threads, total = thread_service.list_threads(page=1, per_page=_clamp_limit(limit))
    compact = [
        {
            "id": t.get("id"),
            "title": t.get("title"),
            "item_count": t.get("item_count"),
            "platforms": t.get("platforms") or [],
            "first_seen_at": t.get("first_seen_at"),
            "last_seen_at": t.get("last_seen_at"),
        }
        for t in threads
    ]
    return {"total": total, "threads": compact}


@mcp.tool()
def get_thread(thread_id: str) -> dict[str, Any]:
    """获取单个 Thread 详情：事件条目时间线与聚合画像（stats）。"""
    thread = thread_service.get_thread(thread_id)
    if not thread:
        return {"error": "thread not found"}
    items = [
        {
            "id": it.get("id"),
            "title": it.get("title"),
            "url": it.get("url"),
            "task_name": it.get("task_name"),
            "fetched_at": it.get("fetched_at"),
            "similarity": it.get("similarity"),
        }
        for it in thread.get("items", [])
    ]
    return {
        "id": thread.get("id"),
        "title": thread.get("title"),
        "first_seen_at": thread.get("first_seen_at"),
        "last_seen_at": thread.get("last_seen_at"),
        "platforms": thread.get("platforms") or [],
        "stats": thread.get("stats"),
        "items": items,
    }


@mcp.tool()
def get_stats() -> dict[str, Any]:
    """获取系统概览统计：总条目数、今日采集、Thread 总数、任务状态分布。"""
    with get_db() as conn:
        total_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        items_today = conn.execute(
            "SELECT COUNT(*) FROM items WHERE date(fetched_at) = date('now')"
        ).fetchone()[0]
        total_threads = conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
        task_rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM tasks WHERE deleted_at IS NULL GROUP BY status"
        ).fetchall()
    return {
        "total_items": total_items,
        "items_today": items_today,
        "total_threads": total_threads,
        "tasks_by_status": {r["status"]: r["c"] for r in task_rows},
    }


@mcp.tool()
def list_tasks(limit: int = 50) -> dict[str, Any]:
    """列出爬取任务及其运行配置（名称、状态、Cron、最近执行）。"""
    tasks, total = task_repo.list_all(page=1, per_page=_clamp_limit(limit))
    compact = [
        {
            "id": t.get("id"),
            "name": t.get("name"),
            "status": t.get("status"),
            "cron_expression": t.get("cron_expression"),
            "last_executed_at": t.get("last_executed_at"),
        }
        for t in tasks
    ]
    return {"total": total, "tasks": compact}


# ── ASGI 挂载层 ──────────────────────────────────────────


class MachineTokenMiddleware:
    """
    MCP 子应用的认证包装：?token= 或 Authorization: Bearer 必须匹配机器令牌。

    MCP 客户端无法走 httpOnly cookie；令牌与 RSS 出口共用（GET /api/rss/feeds 获取）。
    """

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] == "http":
            params = dict(parse_qsl(scope.get("query_string", b"").decode("utf-8")))
            auth_header = ""
            for key, value in scope.get("headers", []):
                if key == b"authorization":
                    auth_header = value.decode("latin-1")
                    break
            bearer = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
            if not verify_machine_token(params.get("token")) and not verify_machine_token(bearer):
                response = JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "code": "UNAUTHORIZED",
                            "message": "Invalid or missing machine token (get it from GET /api/rss/feeds)",
                        }
                    },
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def get_mcp_asgi_app() -> Callable:
    """返回带认证层的 MCP ASGI 子应用（挂载到 /api/mcp）。"""
    return MachineTokenMiddleware(mcp.streamable_http_app())


# 模块级构建一次：streamable_http_app() 同时惰性创建 session_manager，
# main.py 的 lifespan 需要在整个服务生命周期内运行它。
mcp_asgi_app = get_mcp_asgi_app()
