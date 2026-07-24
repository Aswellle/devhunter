"""
app/api/events.py
实时执行事件流端点（SSE）：GET /api/tasks/{id}/events
客户端使用 fetch + ReadableStream 消费（支持 Authorization header）。
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

# SSE 心跳间隔（秒）
_HEARTBEAT_INTERVAL = 0.4
# 单次连接最大等待时间（分钟），超时后客户端自动重连
_MAX_STREAM_MINUTES = 10


@router.get("/tasks/{task_id}/events")
async def stream_task_events(
    task_id: str,
    _: str = Depends(require_auth),
):
    """
    SSE 端点：订阅任务执行事件流。
    - 任务开始执行时推送步骤事件
    - success / failure / warning 为终止事件，推送后关闭流
    - 每 400ms 推送一次心跳保持连接
    """
    task = task_repo.get(task_id)
    if not task:
        raise TaskNotFoundError(f"Task {task_id} not found")

    q = event_bus.subscribe(task_id)

    async def event_generator():
        max_ticks = int(_MAX_STREAM_MINUTES * 60 / _HEARTBEAT_INTERVAL)
        ticks = 0

        # 推送连接成功事件
        yield _sse({"type": "connected", "task_id": task_id,
                    "task_name": task.get("name", ""),
                    "message": "已连接，等待任务执行..."})

        # Emit a diagnostic event 5s after connect if nothing happened — helps
        # distinguish "worker not yet started" from "worker started but no events yet"
        import asyncio
        await asyncio.sleep(5)
        yield _sse({"type": "diagnostic", "message": "5秒内未收到执行事件，Worker 可能尚未启动。请检查任务状态（需为 active）并确认任务未被卡在并发锁中。",
                    "data": {"hint": "worker_not_started"}})

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

                    # 终止事件：流结束
                    if event.event_type in ("success", "failure", "warning"):
                        return

                except queue_module.Empty:
                    # 无事件时发送心跳注释（不触发客户端 onmessage）
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(_HEARTBEAT_INTERVAL)

        except asyncio.CancelledError:
            # 客户端断连
            pass
        finally:
            event_bus.unsubscribe(task_id, q)

        # 超时关闭
        yield _sse({"type": "timeout", "message": "连接超时，请重新打开"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",      # 禁用 Nginx 缓冲
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


def _sse(data: dict) -> str:
    """格式化为 SSE data 帧"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
