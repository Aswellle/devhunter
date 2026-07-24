"""
app/schemas/item.py
采集结果条目 Pydantic 模型
"""
from pydantic import BaseModel, Field


class ItemResponse(BaseModel):
    """单个采集结果响应"""
    id: str
    task_id: str
    task_name: str | None = None  # JOIN 查询时填充
    thread_id: str | None = None  # 所属 Thread（多平台聚合）
    title: str
    url: str
    summary: str | None
    is_read: bool
    is_starred: bool
    fetched_at: str
    created_at: str

    model_config = {"from_attributes": True}


class ItemPatch(BaseModel):
    """更新单个条目状态（PATCH）"""
    is_read: bool | None = None
    is_starred: bool | None = None


class ItemBatchPatch(BaseModel):
    """批量更新条目状态"""
    ids: list[str] = Field(..., min_length=1, max_length=100)
    is_read: bool | None = None
    is_starred: bool | None = None
