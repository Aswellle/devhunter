"""
app/api/user_prefs.py
用户偏好与个性化推荐 API 端点
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import require_auth
from app.repositories.item_repo import item_repo
from app.repositories.user_prefs_repo import (
    recommendation_config_repo,
    user_interaction_repo,
)
from app.schemas.common import PaginatedResponse
from app.schemas.item import ItemResponse
from app.schemas.user_prefs import (
    AffinityResponse,
    FeedbackRequest,
    FeedbackResponse,
    InteractionRecord,
    InteractionResponse,
    RecommendationConfigResponse,
    RecommendationConfigUpdate,
    RecommendedItemResponse,
    RecommendedTopicResponse,
    RelevanceLabelRequest,
    RelevanceLabelResponse,
    RelevanceLabelSampleItem,
    RelevanceLabelSummary,
    UserTopicCreate,
    UserTopicResponse,
    UserTopicUpdate,
)
from app.services.recommendation_service import recommendation_service

logger = logging.getLogger(__name__)

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
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Topic not found"})
    return updated


@router.delete("/topics/{topic}")
def remove_topic(topic: str, _: str = Depends(require_auth)):
    """删除用户主题偏好"""
    removed = recommendation_service.remove_user_topic(topic=topic)
    if not removed:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Topic not found"})
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
    return user_interaction_repo.get_recent_interactions(hours=hours, limit=limit)


# ── 阅读亲缘度（画像页）───────────────────────────────────

@router.get("/affinities", response_model=list[AffinityResponse])
def list_affinities(
    limit: int = Query(50, ge=1, le=200),
    _: str = Depends(require_auth),
):
    """
    获取阅读亲缘度，按得分倒序。

    「我的画像」页的"阅读偏好"区块读取该接口；数据由阅读行为累积
    （record_interaction → update_affinity）。返回的 display_value /
    display_type 是解析合并后的展示字段：task 行的原始值是 task_id、
    platform 行按历史约定存的是任务名称，展示层不应直接读原始值。
    """
    return recommendation_service.get_reading_affinities(limit=limit)


# ── 推荐配置 ──────────────────────────────────────────────

# 前端字段名 → recommendation_config 表的配置键
_WEIGHT_KEYS: dict[str, str] = {
    "topic_match": "topic_match_weight",
    "affinity": "affinity_weight",
    "recency": "recency_weight",
    "engagement": "engagement_weight",
}

# preference_mode → 四因子权重预设（与前端 RecommendationSettings 一致）。
# 客户端只提交模式时由服务端展开成实际权重，避免"模式存了但权重没生效"。
_MODE_WEIGHTS: dict[str, dict[str, float]] = {
    "interest_first":    {"topic_match": 0.5, "affinity": 0.3, "recency": 0.1, "engagement": 0.1},
    "balanced":          {"topic_match": 0.4, "affinity": 0.3, "recency": 0.2, "engagement": 0.1},
    "fresh_first":       {"topic_match": 0.2, "affinity": 0.1, "recency": 0.5, "engagement": 0.2},
    "exploration_first": {"topic_match": 0.2, "affinity": 0.1, "recency": 0.2, "engagement": 0.1},
}

# 从未保存过配置时打分引擎使用的默认权重（services/recommendation_service.py）
_DEFAULT_WEIGHTS = _MODE_WEIGHTS["balanced"]


@router.get("/recommendations/config", response_model=RecommendationConfigResponse)
def get_recommendation_config(_: str = Depends(require_auth)):
    """
    读取当前生效的推荐评分权重（四因子）。

    - weights：`recommendation_config` 表中的实际生效值；从未保存过时返回
      与打分引擎一致的默认值（balanced 预设）
    - preference_mode：与预设权重精确比对推断；手动调节过权重则可能为 null
    """
    stored = recommendation_config_repo.get_all()
    effective = {field: stored.get(key, _DEFAULT_WEIGHTS[field]) for field, key in _WEIGHT_KEYS.items()}

    mode: str | None = None
    for candidate, preset in _MODE_WEIGHTS.items():
        if all(abs(preset[f] - effective[f]) < 1e-9 for f in _WEIGHT_KEYS):
            mode = candidate
            break

    return {"preference_mode": mode, "weights": effective}


@router.post("/recommendations/config", response_model=RecommendationConfigResponse)
def update_recommendation_config(
    body: RecommendationConfigUpdate,
    _: str = Depends(require_auth),
):
    """
    更新推荐评分权重（四因子）。

    - 只传 `preference_mode`：使用该模式的预设权重
    - 传 `weights`：在模式预设之上逐项覆盖（高级模式的手动调节）
    - 两者至少提供一个，否则 400

    权重即推荐引擎的实际打分参数（见 services/recommendation_service.py），
    写入 `recommendation_config` 表后立即生效。
    """
    if body.preference_mode is None and body.weights is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "BAD_REQUEST", "message": "需提供 preference_mode 或 weights"},
        )

    effective = dict(_MODE_WEIGHTS[body.preference_mode or "balanced"])
    if body.weights is not None:
        # 只覆盖提交了的字段（未提交的沿用模式预设）
        effective.update(body.weights.model_dump(exclude_none=True))

    for field, config_key in _WEIGHT_KEYS.items():
        recommendation_config_repo.set(config_key, effective[field])

    logger.info("Recommendation config updated: mode=%s weights=%s", body.preference_mode, effective)
    return {"preference_mode": body.preference_mode, "weights": effective}


# ── 推荐质量打标（金标）───────────────────────────────────

@router.get("/recommendations/labels/sample", response_model=list[RelevanceLabelSampleItem])
def get_label_sample(
    limit: int = Query(8, ge=1, le=20),
    _: str = Depends(require_auth),
):
    """
    打标采样：在通过最低分阈值的候选中按排名等距取样（头/中/尾都覆盖），
    只返回未打标过的条目，并附采样时的推荐得分快照。

    打标仅用于评估推荐排序质量，不影响推荐结果与画像。
    """
    return recommendation_service.sample_for_labeling(limit=limit)


@router.post("/recommendations/labels", response_model=RelevanceLabelResponse,
             status_code=status.HTTP_201_CREATED)
def submit_relevance_label(body: RelevanceLabelRequest, _: str = Depends(require_auth)):
    """记录/改判一条金标（感兴趣 / 不感兴趣）；同一 item 重复提交视为改判"""
    if not item_repo.get(body.item_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ITEM_NOT_FOUND", "message": f"Item {body.item_id} not found"},
        )
    return recommendation_service.record_label(
        item_id=body.item_id,
        label=body.label,
        sampled_score=body.sampled_score,
    )


@router.get("/recommendations/labels/summary", response_model=RelevanceLabelSummary)
def get_relevance_label_summary(_: str = Depends(require_auth)):
    """
    打标汇总：已标数量（正/负）与排序贴合度——正例得分高于负例的比例。

    win_rate 为 null 表示正负样本至少各 1 条后才可计算。
    """
    return recommendation_service.get_label_summary()


# ── 负反馈 ────────────────────────────────────────────────

@router.post("/feedback", response_model=FeedbackResponse,
             status_code=status.HTTP_201_CREATED)
def record_feedback(body: FeedbackRequest, _: str = Depends(require_auth)):
    """
    记录负反馈（not_interested / hide_source / mute_topic）。

    目标统一取 item_id：推荐引擎后续会依据 `get_negative_feedback_map()`
    把对应条目标记为已反馈，避免重复推荐用户已经明确拒绝的内容。
    """
    if not item_repo.get(body.item_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ITEM_NOT_FOUND", "message": f"Item {body.item_id} not found"},
        )

    feedback_id = user_interaction_repo.record_negative_feedback(
        feedback_type=body.feedback_type,
        target_value=body.item_id,
        reason=body.reason or "",
    )
    return {"id": feedback_id, "feedback_type": body.feedback_type, "target_value": body.item_id}
