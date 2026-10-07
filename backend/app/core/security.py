"""
app/core/security.py
MVP 极简认证：单用户密码 + JWT Token
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 用户名可通过 AUTH_USERNAME 环境变量配置（默认 "admin"）
_ADMIN_USERNAME = settings.auth_username

# 机器访问令牌的派生域（换域 = 全量吊销重发）
_MACHINE_TOKEN_DOMAIN = b"devhunter-machine-access-v1"


def verify_password(plain_password: str) -> bool:
    """验证明文密码是否与配置密码一致（timing-safe 比较）"""
    return secrets.compare_digest(plain_password, settings.auth_password)


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


def machine_token() -> str:
    """
    机器访问能力令牌（RSS 阅读器 / MCP 等无法携带 httpOnly cookie 的客户端用）。

    由 SECRET_KEY 经 HMAC-SHA256 确定性派生：
    - SECRET_KEY 稳定（生产环境强制非默认值）则令牌在重启间稳定，订阅地址不会失效；
    - 轮换 SECRET_KEY 即吊销全部机器访问；
    - 开发环境若 .env 仍是占位符，每次启动自动生成随机 SECRET_KEY，令牌随之变化（预期行为）。
    """
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        _MACHINE_TOKEN_DOMAIN,
        hashlib.sha256,
    ).hexdigest()[:32]


def verify_machine_token(token: str | None) -> bool:
    """timing-safe 校验机器访问令牌。空值直接 False。"""
    if not token:
        return False
    return secrets.compare_digest(token, machine_token())
