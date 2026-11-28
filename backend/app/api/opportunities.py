"""
app/api/opportunities.py
机会板 API（PROD-005）：创建 / 列表 / 详情（含证据与审计）/ 更新 / 删除。
"""
import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import require_auth
from app.services.opportunity_service import opportunity_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])

OpportunityType = Literal[
    "user_problem", "product_launch", "open_source_project",
    "hiring", "collaboration", "trend", "technical_risk", "idea",
]
Status = Literal["inbox", "investigating", "planned", "building", "shipped", "dismissed"]
Priority = Literal["low", "normal", "high"]


class OpportunityCreate(BaseModel):
    origin_type: Literal["item", "thread"]
    origin_id: str
    title: str | None = Field(None, max_length=300)
    opportunity_type: OpportunityType = "idea"
    status: Status = "inbox"
    priority: Priority = "normal"
    value_score: float | None = None
    notes: str = ""
    tags: list[str] = Field(default_factory=list, max_length=20)
    remind_at: str | None = None


class OpportunityUpdate(BaseModel):
    title: str | None = Field(None, max_length=300)
    opportunity_type: OpportunityType | None = None
    status: Status | None = None
    priority: Priority | None = None
    value_score: float | None = None
    notes: str | None = None
    tags: list[str] | None = Field(None, max_length=20)
    remind_at: str | None = None


@router.get("")
def list_opportunities(
    status: str | None = None,
    origin_type: str | None = None,
    limit: int = 200,
    _: str = Depends(require_auth),
):
    return opportunity_service.list(
        status=status, origin_type=origin_type, limit=min(max(limit, 1), 500),
    )


@router.post("", status_code=201)
def create_opportunity(body: OpportunityCreate, _: str = Depends(require_auth)):
    return opportunity_service.create(body.model_dump())


@router.get("/{opportunity_id}")
def get_opportunity(opportunity_id: str, _: str = Depends(require_auth)):
    return opportunity_service.get(opportunity_id)


@router.patch("/{opportunity_id}")
def update_opportunity(
    opportunity_id: str, body: OpportunityUpdate, _: str = Depends(require_auth),
):
    return opportunity_service.update(
        opportunity_id, body.model_dump(exclude_unset=True),
    )


@router.delete("/{opportunity_id}", status_code=204)
def delete_opportunity(opportunity_id: str, _: str = Depends(require_auth)):
    opportunity_service.delete(opportunity_id)
