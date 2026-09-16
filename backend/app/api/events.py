"""
app/api/events.py
实时执行事件流端点（SSE）：GET /api/tasks/{id}/events
"""
import asyncio
import json
import queue as queue_module

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import require_auth
from app.core.event_bus import event_bus
from app.core.exceptions import TaskNotFoundError
from app.repositories.task_repo import task_repo

router = APIRouter(tags=["events"])

_HEARTBEAT_INTERVAL = 0.4
_MAX_STREAM_MINUTES = 10


@router.get("/tasks/{task_id}/events")
async def stream_task_events(
    task_id: str,
    _: str = Depends(require_auth),
):
    # F3: wrap blocking sqlite call in executor
    loop = asyncio.get_event_loop()
    task = await loop.run_in_executor(None, task_repo.get, task_id)
    if not task:
        raise TaskNotFoundError(f"Task {task_id} not found")

    q = event_bus.subscribe(task_id)

    async def event_generator():
        max_ticks = int(_MAX_STREAM_MINUTES * 60 / _HEARTBEAT_INTERVAL)
        ticks = 0

        yield _sse({"type": "connected", "task_id": task_id,
                    "task_name": task.get("name", ""),
                    "message": "已连接，等待任务执行..."})

        # F9: removed unconditional 5s sleep

        try:
            while ticks < max_ticks:
                ticks += 1
                try:
                    event = q.get_nowait()
                    payload = {
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

        yield _sse({"type": "timeout", "message": "连接超时，请重新打开"})

    # F4: removed hardcoded "Access-Control-Allow-Origin: *" — let CORSMiddleware handle it
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
