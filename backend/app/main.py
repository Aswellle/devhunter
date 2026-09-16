"""
app/main.py
FastAPI 应用入口：lifespan 管理 + 路由挂载 + 异常处理 + CORS
"""
import uuid

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.router import api_router
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.database import close_database, init_database
from app.core.exceptions import DevHunterError
from app.core.http_client import close_http_client
from app.core.logging import setup_logging
from app.core.request_id import RequestIdMiddleware
from app.scheduler.manager import scheduler_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动 → 提供服务 → 关闭"""
    setup_logging()
    logger.info("DevHunter starting up (env=%s)", settings.app_env)
    settings.validate_production_secrets()

    init_database()
    scheduler_manager.start()
    scheduler_manager.restore_jobs()

    logger.info("DevHunter ready on port %d", settings.app_port)
    yield

    logger.info("DevHunter shutting down...")
    scheduler_manager.shutdown(wait=True)
    close_http_client()
    close_database()
    logger.info("DevHunter shutdown complete")


def create_app() -> FastAPI:
    # F10: docs/redoc 在生产环境关闭，避免未认证暴露完整 API schema
    docs_url = None if settings.is_production else "/docs"
    redoc_url = None if settings.is_production else "/redoc"

    app = FastAPI(
        title="DevHunter API",
        description="全网开发需求与创意自动采集系统",
        version="1.0.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )

    # ── 限流（登录接口专用，见 api/auth.py 的 @limiter.limit）──
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── CORS ────────────────────────────────────────────
    # S3: 生产环境 CORS 不允许 wildcard methods/headers，显式声明所需集合。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept"],
    )

    # ── A1: Request ID ──────────────────────────────────
    # 最外层中间件：为每个请求生成/透传 X-Request-ID，用于全链路关联。
    app.add_middleware(RequestIdMiddleware)

    # ── 全局异常处理器 ────────────────────────────────────
    def _get_request_id(request: Request) -> str:
        """安全获取 request_id，中间件未匹配时（如测试）返回 unknown。"""
        return getattr(request.state, "request_id", "unknown")

    @app.exception_handler(DevHunterError)
    async def devhunter_error_handler(request: Request, exc: DevHunterError):
        # A2: 统一错误格式包含 details 和 request_id
        error_body = {
            "code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "request_id": _get_request_id(request),
        }
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": error_body},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """
        统一 HTTPException 响应格式。
        路由层 raise HTTPException(detail={"code":..., "message":...})
        统一包装为 {"error": {"code":..., "message":..., "details":..., "request_id":...}}
        """
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            error_body = {
                "code": detail.get("code", "HTTP_ERROR"),
                "message": detail.get("message", str(detail)),
                "details": detail.get("details", {}),
                "request_id": _get_request_id(request),
            }
        else:
            error_body = {
                "code": "HTTP_ERROR",
                "message": str(detail),
                "details": {},
                "request_id": _get_request_id(request),
            }
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": error_body},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error",
                    "details": {},
                    "request_id": _get_request_id(request),
                }
            },
        )

    # ── 挂载路由 ─────────────────────────────────────────
    app.include_router(api_router)

    # ── 健康检查 ─────────────────────────────────────────
    @app.get("/health", tags=["system"])
    async def health_check():
        return {"status": "ok", "version": "1.0.0"}

    return app


app = create_app()
