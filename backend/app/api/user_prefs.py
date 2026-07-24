"""
app/api/user_prefs.py
用户偏好与个性化推荐 API 端点
"""
from fastapi import APIRouter, Depends, Query

from app.api.deps import require_auth
from app.schemas.common import PaginatedResponse
from app.schemas.item import ItemResponse
from app.schemas.user_prefs import (
    InteractionRecord,
    InteractionResponse,
    RecommendedItemResponse,
    RecommendedTopicResponse,
    UserTopicCreate,
    UserTopicResponse,
    UserTopicUpdate,
)
from app.services.recommendation_service import recommendation_service

router = APIRouter(prefix="/user-prefs", tags=["user-prefs"])


@router.get("/recommendations", response_model=PaginatedResponse[RecommendedItemResponse])
def get_recommendations(
    limit: int = Query(20, ge=1, le=50),
    exclude_read: bool = Query(True),
    _: str = Depends(require_auth),
):
    """
    获取个性化推荐内容（For You）。
    按推荐得分倒序返回用户可能感兴趣的内容。
    """
    items = recommendation_service.get_recommended_items(limit=limit, exclude_read=exclude_read)
    return PaginatedResponse(items=items, total=len(items), page=1, per_page=limit)


@router.get("/topics", response_model=list[UserTopicResponse])
def list_topics(_: str = Depends(require_auth)):
    """获取用户已设置的主题偏好列表"""
    return recommendation_service.get_user_topics()


@router.post("/topics", response_model=UserTopicResponse)
def add_topic(body: UserTopicCreate, _: str = Depends(require_auth)):
    """添加用户主题偏好"""
    return recommendation_service.add_user_topic(
        topic=body.topic,
        category=body.category,
        weight=body.weight,
    )


@router.patch("/topics/{topic}", response_model=UserTopicResponse)
def update_topic_weight(topic: str, body: UserTopicUpdate, _: str = Depends(require_auth)):
    """更新主题偏好权重"""
    updated = recommendation_service.update_user_topic_weight(topic=topic, weight=body.weight)
    if not updated:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail={"message": "Topic not found"})
    return updated


@router.delete("/topics/{topic}")
def remove_topic(topic: str, _: str = Depends(require_auth)):
    """删除用户主题偏好"""
    removed = recommendation_service.remove_user_topic(topic=topic)
    if not removed:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail={"message": "Topic not found"})
    return {"deleted": True}


@router.get("/topics/recommended", response_model=list[RecommendedTopicResponse])
def get_recommended_topics(
    limit: int = Query(10, ge=1, le=30),
    _: str = Depends(require_auth),
):
    """
    获取推荐主题列表（基于用户阅读历史智能推荐）。
    """
    return recommendation_service.get_recommended_topics(limit=limit)


@router.post("/interactions", response_model=InteractionResponse)
def record_interaction(body: InteractionRecord, _: str = Depends(require_auth)):
    """记录用户交互行为（view/click/dwell/star/share）"""
    return recommendation_service.record_interaction(
        item_id=body.item_id,
        interaction_type=body.interaction_type,
        dwell_seconds=body.dwell_seconds,
    )


@router.get("/interactions/recent", response_model=list[InteractionResponse])
def get_recent_interactions(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=200),
    _: str = Depends(require_auth),
):
    """获取最近的用户交互记录"""
    from app.repositories.user_prefs_repo import user_interaction_repo
    return user_interaction_repo.get_recent_interactions(hours=hours, limit=limit)
