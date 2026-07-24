"""
app/api/items.py
采集结果条目 API 端点：/api/items
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import require_auth
from app.core.exceptions import ItemNotFoundError
from app.schemas.common import PaginatedResponse
from app.schemas.item import ItemBatchPatch, ItemPatch, ItemResponse
from app.services.item_service import item_service

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=PaginatedResponse[ItemResponse])
def list_items(
    task_id: str | None = Query(None),
    search: str | None = Query(None),
    starred: bool | None = Query(None),
    is_read: bool | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: str = Depends(require_auth),
):
    """获取采集结果列表，支持过滤、搜索、分页"""
    items, total = item_service.list_items(
        task_id=task_id,
        search=search,
        starred=starred,
        is_read=is_read,
        page=page,
        per_page=per_page,
    )
    return PaginatedResponse(items=items, total=total, page=page, per_page=per_page)


@router.patch("/batch", response_model=dict)
def batch_patch_items(body: ItemBatchPatch, _: str = Depends(require_auth)):
    """批量更新条目状态（批量标记已读等）"""
    patch_data = body.model_dump(exclude={"ids"}, exclude_none=True)
    count = item_service.batch_patch(body.ids, patch_data)
    return {"updated": count}


@router.post("/batch-delete", response_model=dict)
def batch_delete_items(body: dict, _: str = Depends(require_auth)):
    """批量删除采集结果条目"""
    ids: list[str] = body.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail={"message": "ids list is required"})
    deleted = item_service.batch_delete(ids)
    return {"deleted": deleted}


@router.get("/{item_id}", response_model=ItemResponse)
def get_item(item_id: str, _: str = Depends(require_auth)):
    try:
        from app.repositories.item_repo import item_repo
        item = item_repo.get(item_id)
        if not item:
            raise ItemNotFoundError()
        return item
    except ItemNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.error_code, "message": e.message})


@router.patch("/{item_id}", response_model=ItemResponse)
def patch_item(item_id: str, body: ItemPatch, _: str = Depends(require_auth)):
    """更新单条目状态（已读/收藏）"""
    try:
        updated = item_service.patch_item(item_id, body.model_dump(exclude_none=True))
        return updated
    except ItemNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.error_code, "message": e.message})


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: str, _: str = Depends(require_auth)):
    """删除单条采集结果"""
    try:
        item_service.delete_item(item_id)
    except ItemNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.error_code, "message": e.message})
