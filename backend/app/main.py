"""
app/main.py
FastAPI 应用入口：lifespan 管理 + 路由挂载 + 异常处理 + CORS
"""
import logging
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
from app.scheduler.manager import scheduler_manager

logger = logging.getLogger(__name__)


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 全局异常处理器 ────────────────────────────────────
    @app.exception_handler(DevHunterError)
    async def devhunter_error_handler(request: Request, exc: DevHunterError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.error_code, "message": exc.message}},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """
        统一 HTTPException 响应格式。
        路由层 raise HTTPException(detail={"code":..., "message":...})
        统一包装为 {"error": {"code":..., "message":...}}
        """
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            content = {"error": detail}
        else:
            content = {"error": {"code": "HTTP_ERROR", "message": str(detail)}}
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
        )

    # ── 挂载路由 ─────────────────────────────────────────
    app.include_router(api_router)

    # ── 健康检查 ─────────────────────────────────────────
    @app.get("/health", tags=["system"])
    async def health_check():
        return {"status": "ok", "version": "1.0.0"}

    return app


app = create_app()
