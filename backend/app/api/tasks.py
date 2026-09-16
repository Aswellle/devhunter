"""
app/api/tasks.py
采集任务 API 端点：/api/tasks
"""
from typing import Literal
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import require_auth
from app.core.exceptions import (
    ConflictError,
    DevHunterError,
    TaskAlreadyRunningError,
    TaskNotFoundError,
)
from app.crawler.templates import list_templates
from app.schemas.common import PaginatedResponse
from app.schemas.task import (
    ExecuteTriggerResponse,
    TaskCreate,
    TaskListItem,
    TaskResponse,
    TaskUpdate,
)
from app.services.task_service import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


@router.get("/templates")
def get_templates(_: str = Depends(require_auth)):
    """获取所有预设模板（供前端「使用模板」功能展示）"""
    templates = list_templates()
    return [
        {
            "id": t.id,
            "name": t.name,
            "source_url": t.source_url,
            "selector_list": t.selector_list,
            "selector_title": t.selector_title,
            "selector_link": t.selector_link,
            "selector_summary": t.selector_summary,
            "description": t.description,
            "recommended_cron": t.recommended_cron,
            "category": t.category,
            "subcategory": t.subcategory,
        }
        for t in templates
    ]



@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreate, _: str = Depends(require_auth)):
    """创建新采集任务"""
    try:
        task = task_service.create(body.model_dump())
        return task
    except DevHunterError as e:
        raise HTTPException(status_code=e.status_code,
                            detail={"code": e.error_code, "message": e.message})


@router.get("", response_model=PaginatedResponse[TaskListItem])
def list_tasks(
    status_filter: Literal["active", "paused", "error"] | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: str = Depends(require_auth),
):
    """获取任务列表（支持 status 过滤 + 分页）"""
    items, total = task_service.list_all(
        status=status_filter, page=page, per_page=per_page
    )
    return PaginatedResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: uuid.UUID, _: str = Depends(require_auth)):
    try:
        return task_service.get(str(task_id))
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.error_code, "message": e.message})


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: uuid.UUID, body: TaskUpdate, _: str = Depends(require_auth)):
    """更新任务配置（部分更新）"""
    try:
        task = task_service.update(str(task_id), body.model_dump(exclude_none=True))
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found")
        return task
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.error_code, "message": e.message})
    except DevHunterError as e:
        raise HTTPException(status_code=e.status_code,
                            detail={"code": e.error_code, "message": e.message})


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, _: str = Depends(require_auth)):
    """软删除任务"""
    try:
        task_service.delete(str(task_id))
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.error_code, "message": e.message})


@router.post("/{task_id}/execute", response_model=ExecuteTriggerResponse,
             status_code=status.HTTP_202_ACCEPTED)
def trigger_execute(task_id: uuid.UUID, _: str = Depends(require_auth)):
    """手动触发任务立即执行"""
    try:
        exec_id = task_service.trigger_execute(str(task_id))
        return ExecuteTriggerResponse(
            execution_id=exec_id,
            message="Task queued for execution",
        )
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.error_code, "message": e.message})
    except TaskAlreadyRunningError as e:
        raise HTTPException(status_code=409, detail={"code": e.error_code, "message": e.message})
