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

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

logger = logging.getLogger(__name__)

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


# ── 独立命名机器令牌（SEC-002）──────────────────────────────────
# 与 legacy machine_token（SECRET_KEY 派生、无法单独撤销）并存：
# 命名令牌可单独创建/过期/撤销，scope 当前仅 read（RSS/MCP 只读出口），
# 哈希入库（HMAC(secret_key, raw)），明文只在创建响应里出现一次。

_API_TOKEN_DOMAIN = b"devhunter-api-token-v1"


def _hash_api_token(raw: str) -> str:
    """令牌哈希：HMAC-SHA256(secret_key, domain|raw)。

    SECRET_KEY 参与意味着轮换 SECRET_KEY 会同时吊销全部命名令牌
    （与 legacy 行为一致的兜底）；不允许用可逆/无盐哈希落库。"""
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        _API_TOKEN_DOMAIN + raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_api_token(name: str, expires_at: str | None = None) -> tuple[dict, str]:
    """创建命名令牌，返回 (记录, 明文)。明文只在此刻返回一次。"""
    import uuid

    from app.core.database import get_db

    raw = "dh_" + secrets.token_urlsafe(32)
    token_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO api_tokens (id, name, token_hash, scope, created_at, expires_at)
               VALUES (?, ?, ?, 'read', ?, ?)""",
            (token_id, name[:100], _hash_api_token(raw), now, expires_at),
        )
        row = conn.execute("SELECT * FROM api_tokens WHERE id = ?", (token_id,)).fetchone()
    record = dict(row) if row else {"id": token_id, "name": name}
    record.pop("token_hash", None)
    return record, raw


def verify_api_token(raw: str | None) -> dict | None:
    """校验命名令牌；有效返回记录（不含哈希）并更新 last_used_at。

    撤销/过期立即无效：每次校验都查库，不做进程内缓存。"""
    if not raw or not raw.startswith("dh_"):
        return None
    from app.core.database import get_db

    token_hash = _hash_api_token(raw)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM api_tokens WHERE token_hash = ?", (token_hash,)
        ).fetchone()
        if not row:
            return None
        record = dict(row)
        if record.get("revoked_at"):
            return None
        if record.get("expires_at") and record["expires_at"] <= now:
            return None
        conn.execute(
            "UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (now, record["id"])
        )
    record.pop("token_hash", None)
    return record


def list_api_tokens() -> list[dict]:
    from app.core.database import get_db

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM api_tokens ORDER BY created_at DESC"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d.pop("token_hash", None)
        result.append(d)
    return result


def revoke_api_token(token_id: str) -> bool:
    from app.core.database import get_db

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE api_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (now, token_id),
        )
    return cursor.rowcount > 0


def verify_machine_or_api_token(token: str | None) -> str | None:
    """统一的机器访问校验：命名令牌优先，其次 legacy machine token。

    返回主体标识（"token:<name>" / "machine-token"），无效返回 None。"""
    record = verify_api_token(token)
    if record:
        return f"token:{record.get('name') or record.get('id')}"
    if verify_machine_token(token):
        return "machine-token"
    return None
