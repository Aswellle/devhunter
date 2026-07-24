"""
app/schemas/user_prefs.py
用户偏好与推荐的 Pydantic 模型
"""
from pydantic import BaseModel, Field


class UserTopicResponse(BaseModel):
    """用户主题偏好响应"""
    id: str
    topic: str
    category: str
    weight: float
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class UserTopicCreate(BaseModel):
    """创建用户主题偏好"""
    topic: str = Field(..., min_length=1, max_length=50)
    category: str = Field(default="custom")
    weight: float = Field(default=1.0, ge=0.5, le=2.0)


class UserTopicUpdate(BaseModel):
    """更新用户主题偏好"""
    weight: float = Field(..., ge=0.5, le=2.0)


class InteractionRecord(BaseModel):
    """记录用户交互"""
    item_id: str = Field(..., min_length=1)
    interaction_type: str = Field(..., pattern="^(view|click|dwell|star|share)$")
    dwell_seconds: int | None = Field(default=None, ge=0)


class InteractionResponse(BaseModel):
    """交互记录响应"""
    id: str
    item_id: str
    interaction_type: str
    dwell_seconds: int | None
    created_at: str

    model_config = {"from_attributes": True}


class RecommendedTopicResponse(BaseModel):
    """推荐主题响应"""
    topic: str
    category: str
    score: float


class RecommendedItemResponse(BaseModel):
    """推荐内容响应（带推荐得分）"""
    id: str
    task_id: str
    task_name: str | None
    thread_id: str | None
    title: str
    url: str
    summary: str | None
    is_read: bool
    is_starred: bool
    fetched_at: str
    created_at: str
    recommendation_score: float = 0.0


class UserPrefsResponse(BaseModel):
    """用户偏好完整响应"""
    topics: list[UserTopicResponse]
    recommended_topics: list[RecommendedTopicResponse]
    interaction_count_24h: int
    top_affinities: list[dict]
