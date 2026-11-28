"""
app/api/notifications.py
通知渠道 / 规则 / 投递管理 API（PROD-003）。
"""
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import require_auth
from app.notifications import repo as notif_repo
from app.notifications import service as notif_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., min_length=1, max_length=2048)
    enabled: bool = True


class ChannelUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    url: str | None = Field(None, max_length=2048)
    enabled: bool | None = None


class RuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    trigger_type: Literal["keyword", "thread", "health"]
    config: dict = Field(default_factory=dict)
    channel_id: str
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    config: dict | None = None
    channel_id: str | None = None
    enabled: bool | None = None


@router.get("/channels")
def list_channels(_: str = Depends(require_auth)):
    return notif_repo.list_channels()


@router.post("/channels", status_code=201)
def create_channel(body: ChannelCreate, _: str = Depends(require_auth)):
    from app.core.ssrf import resolve_and_validate_url
    ok, msg, _ip = resolve_and_validate_url(body.url)
    if not ok:
        # URL 受 SSRF 限制：私网/回环/元数据地址直接拒绝（不落库）
        raise HTTPException(status_code=400, detail={
            "code": "UNSAFE_WEBHOOK_URL", "message": f"Webhook 地址被安全策略拦截：{msg}",
        })
    return notif_repo.create_channel(body.name, body.url, body.enabled)


@router.patch("/channels/{channel_id}")
def update_channel(channel_id: str, body: ChannelUpdate, _: str = Depends(require_auth)):
    if not notif_repo.get_channel(channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    if body.url:
        from app.core.ssrf import resolve_and_validate_url
        ok, msg, _ip = resolve_and_validate_url(body.url)
        if not ok:
            raise HTTPException(status_code=400, detail={
                "code": "UNSAFE_WEBHOOK_URL", "message": f"Webhook 地址被安全策略拦截：{msg}",
            })
    return notif_repo.update_channel(channel_id, body.model_dump(exclude_none=True))


@router.delete("/channels/{channel_id}", status_code=204)
def delete_channel(channel_id: str, _: str = Depends(require_auth)):
    if not notif_repo.delete_channel(channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")


@router.get("/rules")
def list_rules(trigger_type: str | None = None, _: str = Depends(require_auth)):
    return notif_repo.list_rules(trigger_type)


@router.post("/rules", status_code=201)
def create_rule(body: RuleCreate, _: str = Depends(require_auth)):
    if not notif_repo.get_channel(body.channel_id):
        raise HTTPException(status_code=400, detail="Channel not found")
    if body.trigger_type == "keyword" and not (body.config or {}).get("keywords"):
        raise HTTPException(status_code=400, detail="keyword 规则必须提供 config.keywords")
    return notif_repo.create_rule(
        body.name, body.trigger_type, body.config, body.channel_id, body.enabled,
    )


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: str, body: RuleUpdate, _: str = Depends(require_auth)):
    updated = notif_repo.update_rule(rule_id, body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Rule not found")
    return updated


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str, _: str = Depends(require_auth)):
    if not notif_repo.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")


@router.get("/deliveries")
def list_deliveries(limit: int = 100, _: str = Depends(require_auth)):
    return notif_repo.list_recent_deliveries(min(max(limit, 1), 500))


@router.post("/deliveries/{delivery_id}/retry")
def retry_delivery(delivery_id: str, _: str = Depends(require_auth)):
    if not notif_service.retry_delivery(delivery_id):
        raise HTTPException(status_code=404, detail="Delivery not found")
    return {"status": "pending", "delivery_id": delivery_id}


@router.post("/deliveries/run")
def run_deliveries(_: str = Depends(require_auth)):
    """手动触发一次投递（调试/补发用）。"""
    return notif_service.deliver_pending()
