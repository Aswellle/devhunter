"""
app/api/deps.py
FastAPI 依赖注入：认证中间件
"""
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)

_TOKEN_COOKIE = "devhunter_token"


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token_cookie: str | None = Cookie(None, alias=_TOKEN_COOKIE),
) -> str:
    """
    验证 Token：优先从 Authorization Header 读取，否则从 Cookie 读取。
    返回 subject（用户名）。无 Token 或 Token 无效时抛出 401。
    """
    token = None

    # 优先从 Bearer Header
    if credentials:
        token = credentials.credentials
    # 备选：从 httpOnly Cookie
    elif token_cookie:
        token = token_cookie

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Missing authentication token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        if not sub:
            raise UnauthorizedError("Invalid token payload")
        return sub
    except UnauthorizedError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": str(e)},
            headers={"WWW-Authenticate": "Bearer"},
        )
