"""
app/api/router.py
汇总所有子路由，挂载到主 FastAPI 应用
"""
from fastapi import APIRouter

from app.api import auth, events, executions, items, sources, stats, tasks, threads, user_prefs

api_router = APIRouter(prefix="/api")

api_router.include_router(auth.router)
api_router.include_router(tasks.router)
api_router.include_router(threads.router)  # 必须注册在 items 之前，避免 /items/{id} 的通配符匹配 /items/threads
api_router.include_router(items.router)
api_router.include_router(executions.router)
api_router.include_router(events.router)
api_router.include_router(sources.router)
api_router.include_router(user_prefs.router)
