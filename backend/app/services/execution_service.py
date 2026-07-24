"""
app/services/execution_service.py
任务执行记录业务层
"""
import logging

from app.core.exceptions import TaskNotFoundError
from app.repositories.execution_repo import execution_repo
from app.repositories.task_repo import task_repo

logger = logging.getLogger(__name__)


class ExecutionService:

    def list_by_task(
        self,
        task_id: str,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[dict], int]:
        # 确认任务存在
        if not task_repo.get(task_id):
            raise TaskNotFoundError(f"Task {task_id} not found")
        return execution_repo.list_by_task(task_id, page=page, per_page=per_page)


# 全局单例
execution_service = ExecutionService()
