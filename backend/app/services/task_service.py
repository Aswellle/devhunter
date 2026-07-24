"""
app/services/task_service.py
采集任务业务层：CRUD 编排 + 调度器联动
"""
import logging

from app.core.exceptions import TaskAlreadyRunningError, TaskNotFoundError
from app.repositories.task_repo import task_repo
from app.scheduler.manager import scheduler_manager

logger = logging.getLogger(__name__)


class TaskService:

    def create(self, data: dict) -> dict:
        """
        创建任务：
        1. 应用预设模板（若有 template_id）
        2. 写入数据库
        3. 注册调度 Job
        """
        # 应用预设模板填充字段
        if data.get("template_id"):
            from app.crawler.templates import apply_template
            data = apply_template(data["template_id"], data)

        task = task_repo.insert(data)

        # 注册调度 Job
        try:
            scheduler_manager.add_job(task["id"], task["cron_expression"])
        except Exception as e:
            logger.error("Failed to add scheduler job for task %s: %s", task["id"], e)
            # 不影响任务创建，Job 会在下次服务重启时 restore

        return task

    def get(self, task_id: str) -> dict:
        task = task_repo.get(task_id)
        if not task:
            raise TaskNotFoundError(f"Task {task_id} not found")
        return task

    def list_all(
        self,
        status: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict], int]:
        return task_repo.list_all(status=status, page=page, per_page=per_page)

    def update(self, task_id: str, data: dict) -> dict:
        """
        更新任务：
        - 若更新了 cron_expression → 重新调度
        - 若 status 改为 paused → 暂停 Job
        - 若 status 改为 active → 恢复 Job（先从 error/paused 恢复）
        """
        existing = self.get(task_id)

        # 提取关键字段变化
        new_cron = data.get("cron_expression")
        new_status = data.get("status")

        updated = task_repo.update(task_id, data)
        if not updated:
            raise TaskNotFoundError(f"Task {task_id} not found")

        # 同步调度器状态
        try:
            if new_status == "paused":
                scheduler_manager.pause_job(task_id)
            elif new_status == "active":
                cron = new_cron or existing["cron_expression"]
                scheduler_manager.reschedule_job(task_id, cron)
                scheduler_manager.resume_job(task_id)
            elif new_cron and new_cron != existing["cron_expression"]:
                scheduler_manager.reschedule_job(task_id, new_cron)
        except Exception as e:
            logger.error("Scheduler sync failed for task %s: %s", task_id, e)

        return updated

    def delete(self, task_id: str) -> None:
        """软删除任务，同时移除调度 Job"""
        self.get(task_id)  # 确认存在（不存在则抛异常）
        task_repo.soft_delete(task_id)
        try:
            scheduler_manager.remove_job(task_id)
        except Exception as e:
            logger.error("Failed to remove scheduler job for task %s: %s", task_id, e)

    def trigger_execute(self, task_id: str) -> str:
        """
        手动触发执行，返回 exec_id 占位符。
        若任务正在执行中，抛出 TaskAlreadyRunningError。
        """
        task = self.get(task_id)
        if scheduler_manager.is_running(task_id):
            raise TaskAlreadyRunningError(f"Task {task_id} is already running")

        from app.scheduler.jobs import execute_task
        import uuid, threading

        exec_id_holder = {"id": str(uuid.uuid4())}

        def _run():
            execute_task(task_id)

        t = threading.Thread(target=_run, daemon=True, name=f"manual-{task_id[:8]}")
        t.start()

        return exec_id_holder["id"]


# 全局单例
task_service = TaskService()
