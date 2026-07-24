"""
app/core/security.py
MVP 极简认证：单用户密码 + JWT Token
"""
import logging
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 用户名可通过 AUTH_USERNAME 环境变量配置（默认 "admin"）
_ADMIN_USERNAME = settings.auth_username


def verify_password(plain_password: str) -> bool:
    """验证明文密码是否与配置密码一致（MVP：直接字符串比较）"""
    return plain_password == settings.auth_password


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """生成 JWT access token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """解码并验证 JWT token，失败抛出 UnauthorizedError"""
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError as e:
        logger.debug("JWT decode failed: %s", e)
        raise UnauthorizedError("Invalid or expired token") from e


def login(password: str) -> str:
    """验证密码并返回 access token"""
    if not verify_password(password):
        raise UnauthorizedError("Invalid password")
    return create_access_token({"sub": _ADMIN_USERNAME})
