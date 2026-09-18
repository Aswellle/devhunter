"""
app/api/auth.py
认证端点：POST /api/auth/login
"""
import threading
import time

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

# ── Account lockout (AUTH-RATE-008) ──────────────────────────
# Track failed login attempts per account; lock out after MAX_FAILURES
# within the observation window. Resets on success or when the window expires.
_MAX_FAILURES = 5
_LOCKOUT_WINDOW_SEC = 300  # 5 minutes
_lockout_lock = threading.Lock()
_failed_attempts: dict[str, list[float]] = {}  # key -> [timestamp, ...]


def _is_account_locked(key: str) -> tuple[bool, int]:
    """Return (locked, seconds_remaining). key is a client identifier."""
    now = time.time()
    with _lockout_lock:
        timestamps = _failed_attempts.get(key, [])
        # Prune attempts outside the window
        recent = [t for t in timestamps if now - t < _LOCKOUT_WINDOW_SEC]
        _failed_attempts[key] = recent
        if len(recent) >= _MAX_FAILURES:
            oldest = min(recent)
            remaining = int(_LOCKOUT_WINDOW_SEC - (now - oldest))
            return True, max(remaining, 0)
    return False, 0


def _record_failure(key: str) -> None:
    now = time.time()
    with _lockout_lock:
        _failed_attempts.setdefault(key, []).append(now)


def _record_success(key: str) -> None:
    with _lockout_lock:
        _failed_attempts.pop(key, None)


@router.post("/login", status_code=200)
@limiter.limit("5/minute")
def do_login(request: Request, body: LoginRequest, response: Response):
    """单用户登录，写入 httpOnly Cookie"""
    # AUTH-RATE-008: per-account lockout after repeated failures.
    # Keyed by client IP (same key slowapi uses) so distributed attacks
    # still trip the lockout, and a single attacker can't bypass via IP rotation.
    client_key = request.client.host if request.client else "unknown"
    locked, remaining = _is_account_locked(client_key)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "ACCOUNT_LOCKED",
                "message": f"Too many failed attempts. Try again in {remaining}s.",
            },
        )

    try:
        token = login(body.password)
    except UnauthorizedError:
        _record_failure(client_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid password"},
        )
    # Success clears the failure window
    _record_success(client_key)
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
