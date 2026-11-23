"""
app/api/star_folders.py
收藏分组（文件夹）API：/api/star-folders
"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_auth
from app.core.exceptions import DevHunterError
from app.schemas.star_folder import (
    StarFolderAssign,
    StarFolderCreate,
    StarFolderListResponse,
    StarFolderRename,
    StarFolderResponse,
)
from app.services.star_folder_service import star_folder_service

router = APIRouter(prefix="/star-folders", tags=["star-folders"])


def _raise_devhunter(e: DevHunterError) -> None:
    raise HTTPException(
        status_code=e.status_code,
        detail={"code": e.error_code, "message": e.message},
    )


@router.get("", response_model=StarFolderListResponse)
def list_folders(_: str = Depends(require_auth)):
    """列出收藏文件夹（含每个文件夹的收藏数与未分类数量）。"""
    return star_folder_service.list_folders()


@router.post("", response_model=StarFolderResponse, status_code=201)
def create_folder(body: StarFolderCreate, _: str = Depends(require_auth)):
    try:
        return star_folder_service.create_folder(body.name)
    except DevHunterError as e:
        _raise_devhunter(e)


# /assign 必须在 /{folder_id} 之前注册，避免被动态路径吞掉
@router.patch("/assign")
def assign_items(body: StarFolderAssign, _: str = Depends(require_auth)):
    """单个或批量把条目移入文件夹；folder_id=null 表示移出到未分类。"""
    try:
        updated = star_folder_service.assign_items(body.item_ids, body.folder_id)
    except DevHunterError as e:
        _raise_devhunter(e)
    return {"updated": updated}


@router.patch("/{folder_id}", response_model=StarFolderResponse)
def rename_folder(folder_id: str, body: StarFolderRename, _: str = Depends(require_auth)):
    try:
        return star_folder_service.rename_folder(folder_id, body.name)
    except DevHunterError as e:
        _raise_devhunter(e)


@router.delete("/{folder_id}", status_code=204)
def delete_folder(folder_id: str, _: str = Depends(require_auth)):
    """删除文件夹：其中条目回落到未分类，收藏状态不变。"""
    try:
        star_folder_service.delete_folder(folder_id)
    except DevHunterError as e:
        _raise_devhunter(e)
