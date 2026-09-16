"""
app/api/auth.py
认证端点：POST /api/auth/login
"""
from fastapi import APIRouter, Depends, Request
from fastapi import HTTPException, Response, status

from app.api.deps import require_auth
from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.rate_limit import limiter
from app.core.security import login
from app.schemas.auth import LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])

TOKEN_COOKIE_NAME = "devhunter_token"


@router.post("/login", status_code=200)
@limiter.limit("5/minute")
def do_login(request: Request, body: LoginRequest, response: Response):
    """单用户登录，写入 httpOnly Cookie"""
    try:
        token = login(body.password)
    except UnauthorizedError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid password"},
        )
    response.set_cookie(
        key=TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=60 * 60 * 24 * 7,
    )
    return {"ok": True}


@router.post("/logout")
def do_logout(response: Response, _: str = Depends(require_auth)):
    """清除 httpOnly Cookie，注销登录"""
    response.delete_cookie(
        key=TOKEN_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
    return {"ok": True}
