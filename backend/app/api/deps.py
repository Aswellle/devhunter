"""
app/api/deps.py
FastAPI 依赖注入：认证中间件
"""
from fastapi import Cookie, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token, verify_machine_token

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


def require_machine_access(
    token: str | None = Query(None, description="机器访问能力令牌（RSS/MCP 客户端用）"),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token_cookie: str | None = Cookie(None, alias=_TOKEN_COOKIE),
) -> str:
    """
    机器出口端点的双重认证：能力令牌 或 标准用户认证。

    能力令牌（派生自 SECRET_KEY）的携带方式：
    - `?token=` —— RSS 阅读器只能带 URL 参数；注意它会进入服务器/代理
      访问日志与浏览器历史，泄露面较大
    - `Authorization: Bearer <token>` —— 可配置 header 的客户端（MCP 等）
      应优先使用，不落日志

    浏览器内已登录的请求（如前端 Profile 页）自然回落到 Bearer/Cookie
    用户认证。

    返回主体标识："machine-token" 或用户名。
    """
    header_token = credentials.credentials if credentials else None
    if verify_machine_token(token) or verify_machine_token(header_token):
        return "machine-token"
    return require_auth(credentials=credentials, token_cookie=token_cookie)
