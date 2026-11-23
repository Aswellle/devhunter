"""
app/schemas/star_folder.py
收藏分组（文件夹）请求/响应模型。
"""
from pydantic import BaseModel, Field


class StarFolderResponse(BaseModel):
    id: str
    name: str
    item_count: int = 0
    created_at: str
    updated_at: str


class StarFolderListResponse(BaseModel):
    folders: list[StarFolderResponse]
    total_starred: int
    uncategorized_count: int


class StarFolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)


class StarFolderRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)


class StarFolderAssign(BaseModel):
    """批量把条目移入文件夹；folder_id=None 表示移出到未分类。"""
    item_ids: list[str] = Field(..., min_length=1, max_length=100)
    folder_id: str | None = None
