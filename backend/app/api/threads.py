"""
app/api/threads.py
Thread API 端点：/api/items/threads
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_auth
from app.schemas.common import PaginatedResponse
from app.schemas.item import ItemResponse
from app.services.thread_service import thread_service

router = APIRouter(prefix="/items/threads", tags=["threads"])


class ThreadResponse:
    """Thread 列表项（不含 Items）"""
    pass


@router.get("", response_model=PaginatedResponse)
def list_threads(
    task_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: str = Depends(require_auth),
):
    """
    获取 Thread 列表，支持按数据源过滤。
    Threads 按最新事件倒序（first_seen_at DESC）。
    """
    threads, total = thread_service.list_threads(
        task_id=task_id,
        page=page,
        per_page=per_page,
    )
    return PaginatedResponse(
        items=threads,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{thread_id}")
def get_thread(thread_id: str, _: str = Depends(require_auth)):
    """
    获取 Thread 详情，包含其所有 Items。
    """
    thread = thread_service.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Thread not found"})
    return thread
