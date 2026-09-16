"""
app/api/items.py
采集结果条目 API 端点：/api/items
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import require_auth
from app.core.exceptions import ItemNotFoundError
from app.schemas.common import PaginatedResponse
from app.schemas.item import ItemBatchPatch, ItemPatch, ItemResponse
from app.services.item_service import item_service

router = APIRouter(prefix="/items", tags=["items"])


class ItemCountResponse(BaseModel):
    total: int
    by_task: dict[str, dict[str, int]]


@router.get("/counts", response_model=ItemCountResponse)
def get_counts(_: str = Depends(require_auth)):
    """Get item counts per task for filter bar badges"""
    counts = item_service.get_counts_by_task()
    total = item_service.get_total_count()
    return ItemCountResponse(total=total, by_task=counts)


class ItemBatchDelete(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=500)


@router.get("", response_model=PaginatedResponse[ItemResponse])
def list_items(
    task_id: str | None = Query(None),
    search: Annotated[str | None, Query(max_length=200)] = None,
    starred: bool | None = Query(None),
    is_read: bool | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: str = Depends(require_auth),
):
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
    patch_data = body.model_dump(exclude={"ids"}, exclude_none=True)
    count = item_service.batch_patch(body.ids, patch_data)
    return {"updated": count}


@router.post("/batch-delete", response_model=dict)
def batch_delete_items(body: ItemBatchDelete, _: str = Depends(require_auth)):
    deleted = item_service.batch_delete(body.ids)
    return {"deleted": deleted}


@router.get("/{item_id}", response_model=ItemResponse)
def get_item(item_id: str, _: str = Depends(require_auth)):
    try:
        item = item_service.get_item(item_id)
        return item
    except ItemNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.error_code, "message": e.message})


@router.patch("/{item_id}", response_model=ItemResponse)
def patch_item(item_id: str, body: ItemPatch, _: str = Depends(require_auth)):
    try:
        updated = item_service.patch_item(item_id, body.model_dump(exclude_none=True))
        return updated
    except ItemNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.error_code, "message": e.message})


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: str, _: str = Depends(require_auth)):
    try:
        item_service.delete_item(item_id)
    except ItemNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.error_code, "message": e.message})
