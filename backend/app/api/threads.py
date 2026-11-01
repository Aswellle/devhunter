"""
app/api/threads.py
Thread API 端点：/api/items/threads
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import require_auth
from app.core.exceptions import ConflictError, DevHunterError
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


@router.post("/recompute", status_code=202)
def recompute_threads(body: ThreadRecomputeRequest, _: str = Depends(require_auth)):
    """
    重建全部 Thread：清空现有聚合后按时间正序重放所有条目的聚类。

    后台执行，立即返回 202；进度经 GET /items/threads/recompute/status
    查询。已有重建进行中返回 409。
    """
    try:
        thread_service.start_recompute(window_hours=body.window_hours)
    except ConflictError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"code": e.error_code, "message": e.message},
        )
    return {"message": "Thread 重建已在后台开始", "window_hours": body.window_hours}


@router.get("/recompute/status")
def recompute_threads_status(_: str = Depends(require_auth)):
    """查询后台重建状态：{running, result, error}"""
    return thread_service.recompute_status()


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
    获取 Thread 详情，包含其所有 Items、聚合画像与"同一故事线"关联层。
    """
    thread = thread_service.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Thread not found"})
    return thread


@router.delete("/{thread_id}/relations/{related_thread_id}", status_code=204)
def unlink_related_thread(
    thread_id: str,
    related_thread_id: str,
    _: str = Depends(require_auth),
):
    """解除一条"同一故事线"关联（拆除误关联）"""
    if not thread_service.unlink_related_thread(thread_id, related_thread_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "RELATION_NOT_FOUND", "message": "关联不存在"},
        )


class ThreadMergeRequest(BaseModel):
    """人工合并参数：源（路径）Thread 的全部条目并入目标后删除源"""
    target_thread_id: str = Field(..., description="合并目标 Thread ID")
    reason: str = Field("", max_length=200, description="合并原因（审计记录）")


@router.post("/{thread_id}/merge")
def merge_thread(thread_id: str, body: ThreadMergeRequest, _: str = Depends(require_auth)):
    """把当前 Thread 人工合并进目标 Thread（多来源同事件被误拆时使用）"""
    if thread_id == body.target_thread_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_MERGE", "message": "源 Thread 与目标 Thread 不能相同"},
        )
    try:
        merged = thread_service.merge_threads(thread_id, body.target_thread_id, body.reason)
    except DevHunterError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"code": e.error_code, "message": e.message},
        )
    if not merged:
        raise HTTPException(
            status_code=404,
            detail={"code": "THREAD_NOT_FOUND", "message": "Thread 不存在"},
        )
    return merged


class ThreadSplitRequest(BaseModel):
    """人工拆分参数：把指定条目移出当前 Thread，创建新 Thread"""
    item_ids: list[str] = Field(..., min_length=1, description="要移出的条目 ID 列表")
    new_thread_title: str | None = Field(None, max_length=300, description="新 Thread 标题（缺省取首个条目标题）")


@router.post("/{thread_id}/split")
def split_thread(thread_id: str, body: ThreadSplitRequest, _: str = Depends(require_auth)):
    """把指定条目从当前 Thread 拆出并创建新 Thread（误聚合时使用）"""
    try:
        new_thread = thread_service.split_thread(thread_id, body.item_ids, body.new_thread_title)
    except DevHunterError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"code": e.error_code, "message": e.message},
        )
    if not new_thread:
        raise HTTPException(
            status_code=404,
            detail={"code": "THREAD_NOT_FOUND", "message": "Thread 不存在"},
        )
    return new_thread


class ThreadDigestRequest(BaseModel):
    """综述生成参数：force=True 时重新生成（相同材料会命中结果复用，不重复付费）"""
    force: bool = False


@router.post("/{thread_id}/digest")
def generate_thread_digest(thread_id: str, body: ThreadDigestRequest | None = None, _: str = Depends(require_auth)):
    """
    手动生成/更新该 Thread 的 AI 综述。

    - 无既有综述 → 生成
    - force=True（或综述落后于最新内容）→ 重新生成
    - 未接入 AI / 熔断 / 预算用尽 / 单条内容 → 相应业务错误码
    """
    try:
        return thread_service.generate_thread_digest(
            thread_id, force=bool(body and body.force),
        )
    except DevHunterError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"code": e.error_code, "message": e.message},
        )
