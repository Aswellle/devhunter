"""
app/api/threads.py
Thread API 端点：/api/items/threads
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import require_auth
from app.core.exceptions import ConflictError
from app.schemas.common import PaginatedResponse
from app.schemas.item import ItemResponse
from app.services.thread_service import thread_service

router = APIRouter(prefix="/items/threads", tags=["threads"])


class ThreadResponse:
    """Thread 列表项（不含 Items）"""
    pass


class ThreadRecomputeRequest(BaseModel):
    """Thread 重建参数"""
    window_hours: int = Field(24, ge=1, le=720, description="候选 Thread 的活动窗口（小时）")


@router.post("/recompute")
def recompute_threads(body: ThreadRecomputeRequest, _: str = Depends(require_auth)):
    """
    重建全部 Thread：清空现有聚合后按时间正序重放所有条目的聚类。

    同步执行（个人规模秒级到分钟级）；已有重建进行中返回 409。
    """
    try:
        return thread_service.recompute_all_threads(window_hours=body.window_hours)
    except ConflictError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"code": e.error_code, "message": e.message},
        )


@router.get("", response_model=PaginatedResponse)
def list_threads(
    task_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    sort: str = Query("first_seen", pattern="^(first_seen|hotness)$"),
    _: str = Depends(require_auth),
):
    """
    获取 Thread 列表，支持按数据源过滤。

    sort:
    - first_seen（默认）：最新事件优先
    - hotness：热度优先（每个独立来源只计一次、24h 半衰期、48h 窗口），
      返回行带 hotness 字段
    """
    threads, total = thread_service.list_threads(
        task_id=task_id,
        page=page,
        per_page=per_page,
        sort=sort,
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
