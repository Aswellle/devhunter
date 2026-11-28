"""
app/api/api_tokens.py
独立命名机器令牌管理（SEC-002）。

命名令牌 scope 固定 read（RSS/MCP 只读出口），哈希入库；明文只在创建
响应中出现一次。撤销立即生效（每次校验都查库）。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import require_auth
from app.core.security import (
    create_api_token,
    list_api_tokens,
    revoke_api_token,
)

router = APIRouter(prefix="/tokens", tags=["tokens"])


class TokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    expires_at: str | None = Field(
        None, description="ISO8601 UTC 过期时间；留空表示长期有效",
    )


@router.get("")
def list_tokens(_: str = Depends(require_auth)):
    """列出令牌元数据（绝不含明文或哈希）。"""
    return list_api_tokens()


@router.post("", status_code=201)
def create_token(body: TokenCreate, _: str = Depends(require_auth)):
    """创建命名令牌；响应中的 token 字段只返回这一次。"""
    record, raw = create_api_token(body.name, body.expires_at)
    return {**record, "token": raw}


@router.delete("/{token_id}", status_code=204)
def revoke_token(token_id: str, _: str = Depends(require_auth)):
    if not revoke_api_token(token_id):
        raise HTTPException(status_code=404, detail="Token not found or already revoked")
