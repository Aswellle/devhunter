"""
app/api/events.py
实时执行事件流端点（SSE）：GET /api/tasks/{id}/events

E1: 支持 Last-Event-ID 游标恢复。
客户端重连时携带 Last-Event-ID，服务端从 DB 补发该 ID 之后的事件，
然后继续实时流，防止断线期间的事件丢失。
"""
import asyncio
import json
import queue as queue_module

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import require_auth
from app.core.event_bus import event_bus
from app.core.exceptions import TaskNotFoundError
from app.repositories.execution_event_repo import execution_event_repo
from app.repositories.task_repo import task_repo

router = APIRouter(tags=["events"])

_HEARTBEAT_INTERVAL = 0.4
_MAX_STREAM_MINUTES = 10


@router.get("/tasks/{task_id}/events")
async def stream_task_events(
    task_id: str,
    request: Request,
    _: str = Depends(require_auth),
):
    # F3: wrap blocking sqlite call in executor
    loop = asyncio.get_event_loop()
    task = await loop.run_in_executor(None, task_repo.get, task_id)
    if not task:
        raise TaskNotFoundError(f"Task {task_id} not found")

    q = event_bus.subscribe(task_id)

    # E1: 获取 Last-Event-ID，用于断线补发。
    # 新游标是全局递增 seq（纯数字）；旧客户端仍可能回传事件 uuid
    last_event_id = request.headers.get("Last-Event-ID")
    after_seq: int | None = None
    after_id: str | None = None
    if last_event_id:
        stripped = last_event_id.strip()
        if stripped.isdigit():
            after_seq = int(stripped)
        else:
            after_id = stripped

    async def event_generator():
        max_ticks = int(_MAX_STREAM_MINUTES * 60 / _HEARTBEAT_INTERVAL)
        ticks = 0

        # E1: 如果有 Last-Event-ID，先从 DB 补发断线期间的事件。
        # 按任务维度补发（list_by_task_after）：事件持久化历史上
        # execution_id 落的是 task_id，按执行维度查询永远为空；
        # 重连客户端要的是"该任务我错过的一切"，跨执行补发正合语义
        if last_event_id:
            try:
                missed_events = await loop.run_in_executor(
                    None,
                    lambda: execution_event_repo.list_by_task_after(
                        task_id, after_id=after_id, after_seq=after_seq
                    ),
                )
                for evt in missed_events:
                    payload = {
                        "id":        evt.get("id", ""),
                        "seq":       evt.get("seq"),
                        "type":      evt.get("event_type", ""),
                        "message":   evt.get("message", ""),
                        "data":      evt.get("data", {}),
                        "timestamp": evt.get("created_at", ""),
                    }
                    yield _sse(payload, event_seq=evt.get("seq"))
                    # 不因补发流里出现终态事件而提前结束：
                    # 游标可能落后于上一次执行，其后还有新一轮的事件
            except Exception:
                pass  # 补发失败不影响实时流

        yield _sse({"id": "connected", "type": "connected", "task_id": task_id,
                    "task_name": task.get("name", ""),
                    "message": "已连接，等待任务执行..."})

        try:
            while ticks < max_ticks:
                ticks += 1
                try:
                    event = q.get_nowait()
                    payload = {
                        "id":        _get_event_id(event),
                        "seq":       event.data.get("event_seq"),
                        "type":      event.event_type,
                        "message":   event.message,
                        "data":      event.data,
                        "timestamp": event.timestamp,
                    }
                    yield _sse(payload, event_seq=event.data.get("event_seq"))
                    if event.event_type in ("success", "failure", "warning"):
                        return
                except queue_module.Empty:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(_HEARTBEAT_INTERVAL)

        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(task_id, q)

        yield _sse({"id": "timeout", "type": "timeout", "message": "连接超时，请重新打开"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _get_event_id(event) -> str:
    """从 event_bus 的 ExecutionEvent 获取持久化 ID（存储在 data 中）。"""
    return event.data.get("event_id", "")


def _sse(data: dict, event_seq: int | None = None) -> str:
    """原生 SSE 帧：真实事件带 `id: <seq>`（断线续传游标），connected/
    timeout 等控制帧不带 id，不会污染客户端游标。"""
    id_line = f"id: {event_seq}\n" if event_seq is not None else ""
    return f"{id_line}data: {json.dumps(data, ensure_ascii=False)}\n\n"
