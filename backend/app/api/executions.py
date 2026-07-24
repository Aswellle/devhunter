"""
app/api/executions.py
任务执行记录端点：GET /api/tasks/{id}/executions
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_auth
from app.core.exceptions import TaskNotFoundError
from app.schemas.common import PaginatedResponse
from app.schemas.execution import ExecutionResponse
from app.services.execution_service import execution_service

router = APIRouter(tags=["executions"])


@router.get("/tasks/{task_id}/executions",
            response_model=PaginatedResponse[ExecutionResponse])
def list_executions(
    task_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    _: str = Depends(require_auth),
):
    """获取任务执行历史（最近 50 次，分页）"""
    try:
        items, total = execution_service.list_by_task(
            task_id, page=page, per_page=per_page
        )
        return PaginatedResponse(items=items, total=total, page=page, per_page=per_page)
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.error_code, "message": e.message})
