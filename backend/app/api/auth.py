"""
app/api/auth.py
认证端点：POST /api/auth/login
"""
from fastapi import APIRouter
from fastapi import HTTPException, Response, status

from app.core.exceptions import UnauthorizedError
from app.core.security import login
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

TOKEN_COOKIE_NAME = "devhunter_token"


@router.post("/login", response_model=TokenResponse)
def do_login(body: LoginRequest, response: Response):
    """单用户登录，返回 JWT access token（同时写入 httpOnly Cookie）"""
    try:
        token = login(body.password)
    except UnauthorizedError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid password"},
        )
    # 写入 httpOnly Cookie（Secure 在生产环境应开启）
    response.set_cookie(
        key=TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        # 生产环境应添加: secure=True
        max_age=60 * 60 * 24 * 7,  # 7 days
    )
    return TokenResponse(access_token=token)


@router.post("/logout")
def do_logout(response: Response):
    """清除 httpOnly Cookie，注销登录"""
    response.delete_cookie(key=TOKEN_COOKIE_NAME)
    return {"ok": True}
