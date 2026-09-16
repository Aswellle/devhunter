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

    # E1: 获取 Last-Event-ID，用于断线补发
    last_event_id = request.headers.get("Last-Event-ID")

    async def event_generator():
        max_ticks = int(_MAX_STREAM_MINUTES * 60 / _HEARTBEAT_INTERVAL)
        ticks = 0

        # E1: 如果有 Last-Event-ID，先从 DB 补发断线期间的事件
        if last_event_id:
            try:
                missed_events = await loop.run_in_executor(
                    None,
                    lambda: execution_event_repo.list_by_execution(
                        _latest_execution_id(task_id), after_id=last_event_id
                    ),
                )
                for evt in missed_events:
                    payload = {
                        "id":        evt.get("id", ""),
                        "type":      evt.get("event_type", ""),
                        "message":   evt.get("message", ""),
                        "data":      evt.get("data", {}),
                        "timestamp": evt.get("created_at", ""),
                    }
                    yield _sse(payload)
                    # 如果补发的事件中包含终态事件，直接结束
                    if evt.get("event_type") in ("success", "failure", "warning"):
                        event_bus.unsubscribe(task_id, q)
                        return
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
                        "type":      event.event_type,
                        "message":   event.message,
                        "data":      event.data,
                        "timestamp": event.timestamp,
                    }
                    yield _sse(payload)
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


def _latest_execution_id(task_id: str) -> str:
    """获取任务最近一次执行的 ID（用于断线补发查询）。"""
    from app.repositories.execution_repo import execution_repo
    latest = execution_repo.get_latest_by_task(task_id)
    return latest["id"] if latest else ""


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
