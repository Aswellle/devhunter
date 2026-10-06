"""
app/schemas/user_prefs.py
用户偏好与推荐的 Pydantic 模型
"""
from typing import Literal

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


class RecommendationReason(BaseModel):
    """推荐原因"""
    type: str
    label: str


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
    recommendation_reasons: list[RecommendationReason] = []


class UserPrefsResponse(BaseModel):
    """用户偏好完整响应"""
    topics: list[UserTopicResponse]
    recommended_topics: list[RecommendedTopicResponse]
    interaction_count_24h: int
    top_affinities: list[dict]


# ── 阅读亲缘度（画像页展示）───────────────────────────────

class AffinityResponse(BaseModel):
    """任务 / 平台 / 关键词维度的阅读亲缘度"""
    id: str
    affinity_type: str
    affinity_value: str
    affinity_score: float
    interaction_count: int
    last_interacted_at: str
    updated_at: str
    # 画像页展示用：task 行的原始值是 task_id、platform 行按历史约定存的是
    # 任务名称，展示层统一解析为可读名称（display_value）与归一维度（display_type）
    display_value: str | None = None
    display_type: str | None = None

    model_config = {"from_attributes": True}


# ── 推荐配置 ──────────────────────────────────────────────

class RecommendationWeights(BaseModel):
    """
    推荐四因子权重（可只提交其中若干项，其余沿用模式预设）。

    字段名与前端保持一致，落库时映射为
    topic_match_weight / affinity_weight / recency_weight / engagement_weight。
    """
    topic_match: float | None = Field(None, ge=0.0, le=1.0)
    affinity: float | None = Field(None, ge=0.0, le=1.0)
    recency: float | None = Field(None, ge=0.0, le=1.0)
    engagement: float | None = Field(None, ge=0.0, le=1.0)


class RecommendationConfigUpdate(BaseModel):
    """更新推荐配置：可只给 preference_mode（用服务端预设权重）"""
    preference_mode: Literal["interest_first", "balanced", "fresh_first", "exploration_first"] | None = None
    weights: RecommendationWeights | None = None


class RecommendationConfigResponse(BaseModel):
    """推荐配置响应：回显本次生效的模式与实际权重"""
    preference_mode: str | None = None
    weights: dict[str, float]


# ── 负反馈 ────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    """负反馈请求，目标统一为该条目"""
    item_id: str = Field(..., min_length=1, max_length=64)
    feedback_type: Literal["not_interested", "hide_source", "mute_topic"]
    reason: str | None = Field(None, max_length=200)


class FeedbackResponse(BaseModel):
    id: str
    feedback_type: str
    target_value: str
