"""
app/services/task_service.py
采集任务业务层：CRUD 编排 + 调度器联动
"""
import logging

from app.core.exceptions import TaskAlreadyRunningError, TaskLimitExceededError, TaskNotFoundError
from app.repositories.task_repo import task_repo
from app.scheduler.manager import scheduler_manager

# Maximum number of scheduled tasks to prevent resource exhaustion (INPUT-TASK-LIMIT-009)
MAX_TASKS_LIMIT = 100

logger = logging.getLogger(__name__)


class TaskService:

    def create(self, data: dict) -> dict:
        """
        创建任务：
        1. 校验任务数量上限，防止资源耗尽
        2. 应用预设模板（若有 template_id）
        3. 写入数据库
        4. 注册调度 Job
        """
        # INPUT-TASK-LIMIT-009: reject creation beyond the cap
        current_count = task_repo.count_all()
        if current_count >= MAX_TASKS_LIMIT:
            raise TaskLimitExceededError(
                f"Task limit reached ({current_count}/{MAX_TASKS_LIMIT}). "
                f"Delete unused tasks before creating new ones."
            )

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
    ) -> list[dict]:
        return task_repo.list_all(status=status, page=page, per_page=per_page)

    def count_all(self) -> int:
        """获取任务总数"""
        return task_repo.count_all()

    def update(self, task_id: str, data: dict) -> dict:
        """
       更新任务：

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
        手动触发执行，返回 exec_id。
        若任务正在执行中，抛出 TaskAlreadyRunningError。

        F8: acquire_task_lock 是唯一的原子检查-占用操作（内部持锁）。
        直接尝试获取锁，成功即视为"未运行且已占用"，避免
        「先检查 is_running 再启动线程」两步之间的竞态窗口。
        """
        self.get(task_id)

        from app.scheduler.jobs import acquire_task_lock, execute_task, release_task_lock
        import uuid, threading

        if not acquire_task_lock(task_id):
            raise TaskAlreadyRunningError(f"Task {task_id} is already running")

        from app.repositories.execution_repo import execution_repo
        from datetime import datetime, timezone

        exec_id = str(uuid.uuid4())
        executed_at_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # F14: 同步创建 'running' 占位行，确保客户端立即轮询该 exec_id 不会 404
        # F15: create_running 失败时必须释放已持有的锁，否则任务会永久卡在
        # "running" 状态（内存中的 _running_tasks 字典），直到进程重启。
        try:
            execution_repo.create_running(exec_id, task_id, executed_at_iso)
        except Exception:
            release_task_lock(task_id)
            raise

        def _run():
            try:
                execute_task(task_id, exec_id=exec_id, _skip_lock=True)
            finally:
                release_task_lock(task_id)

        t = threading.Thread(target=_run, daemon=True, name=f"manual-{task_id[:8]}")
        t.start()

        return exec_id


# 全局单例
task_service = TaskService()
