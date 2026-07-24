"""
app/scheduler/manager.py
SchedulerManager：封装 APScheduler 的初始化、Job 注册/移除/暂停/恢复。
使用 BackgroundScheduler（独立线程），与 FastAPI asyncio event loop 完全隔离。
"""
import datetime
import logging
import threading

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings

logger = logging.getLogger(__name__)


class SchedulerManager:
    """
    封装 APScheduler 操作，对外暴露简洁接口。
    策略：以数据库 tasks 表为 Single Source of Truth，
    启动时清空 JobStore 并重新从 DB 加载所有 active 任务。
    """

    def __init__(self) -> None:
        db_url = f"sqlite:///{settings.db_path}"
        self._scheduler = BackgroundScheduler(
            jobstores={
                "default": SQLAlchemyJobStore(url=db_url)
            },
            executors={
                "default": ThreadPoolExecutor(max_workers=settings.scheduler_max_workers)
            },
            job_defaults={
                "coalesce": True,               # 错过多次只补执行一次
                "max_instances": 1,             # 同一 Job 最多 1 个并发实例
                "misfire_grace_time": settings.scheduler_misfire_grace_time,
            },
        )
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._scheduler.start()
        self._started = True
        logger.info("Scheduler started (max_workers=%d)", settings.scheduler_max_workers)

    def shutdown(self, wait: bool = True) -> None:
        if not self._started:
            return
        self._scheduler.shutdown(wait=wait)
        self._started = False
        logger.info("Scheduler shut down")

    def restore_jobs(self) -> None:
        """
        从 tasks 表重新加载所有 active 任务并注册 Job。
        启动时调用，确保 Scheduler 与 DB 状态一致。
        """
        from app.repositories.task_repo import task_repo

        # 先清空 JobStore（避免旧 Job 与新配置不一致）
        for job in self._scheduler.get_jobs():
            job.remove()

        active_tasks = task_repo.list_active()
        for task in active_tasks:
            try:
                self._add_job(task["id"], task["cron_expression"])
            except Exception as e:
                logger.error("Failed to restore job for task %s: %s", task["id"], e)

        # 注册系统清理 Job：每天凌晨 3:00 UTC 清理 30 天前的软删除数据
        try:
            from app.scheduler.cleanup import cleanup_old_data
            self._scheduler.add_job(
                cleanup_old_data,
                trigger=CronTrigger(hour=3, minute=0, timezone=datetime.timezone.utc),
                id="__system_cleanup__",
                replace_existing=True,
                name="Auto Cleanup (30d)",
            )
        except Exception as e:
            logger.error("Failed to register cleanup job: %s", e)

        logger.info("Restored %d scheduler jobs from DB", len(active_tasks))

    def add_job(self, task_id: str, cron_expression: str) -> None:
        """注册新 Job，若已存在则先移除"""
        with self._lock:
            self._add_job(task_id, cron_expression)

    def _add_job(self, task_id: str, cron_expression: str) -> None:
        """内部：不加锁版本"""
        from app.scheduler.jobs import execute_task

        # 若已存在则先移除（避免重复）
        existing = self._scheduler.get_job(task_id)
        if existing:
            existing.remove()

        trigger = _parse_cron_trigger(cron_expression)
        self._scheduler.add_job(
            execute_task,
            trigger=trigger,
            id=task_id,
            args=[task_id],
            replace_existing=True,
        )
        logger.debug("Job added: %s (cron=%s)", task_id, cron_expression)

    def remove_job(self, task_id: str) -> None:
        with self._lock:
            job = self._scheduler.get_job(task_id)
            if job:
                job.remove()
                logger.debug("Job removed: %s", task_id)

    def pause_job(self, task_id: str) -> None:
        with self._lock:
            job = self._scheduler.get_job(task_id)
            if job:
                job.pause()
                logger.debug("Job paused: %s", task_id)

    def resume_job(self, task_id: str) -> None:
        with self._lock:
            job = self._scheduler.get_job(task_id)
            if job:
                job.resume()
                logger.debug("Job resumed: %s", task_id)

    def reschedule_job(self, task_id: str, cron_expression: str) -> None:
        with self._lock:
            job = self._scheduler.get_job(task_id)
            if job:
                trigger = _parse_cron_trigger(cron_expression)
                job.reschedule(trigger=trigger)
                logger.debug("Job rescheduled: %s → %s", task_id, cron_expression)
            else:
                # Job 不存在则新增
                self._add_job(task_id, cron_expression)

    def trigger_now(self, task_id: str) -> None:
        """立即触发一次执行（手动触发）"""
        from app.scheduler.jobs import execute_task
        from apscheduler.triggers.date import DateTrigger
        from datetime import datetime, timezone, timedelta

        run_at = datetime.now(timezone.utc) + timedelta(seconds=1)
        self._scheduler.add_job(
            execute_task,
            trigger=DateTrigger(run_date=run_at),
            args=[task_id],
            id=f"{task_id}_manual",
            replace_existing=True,
        )
        logger.info("Manual trigger queued for task %s", task_id)

    def is_running(self, task_id: str) -> bool:
        """检查 Job 是否正在执行（通过内存锁判断）"""
        from app.scheduler.jobs import is_task_running
        return is_task_running(task_id)


def _parse_cron_trigger(cron_expression: str) -> CronTrigger:
    """
    将 5 段 Cron 表达式解析为 APScheduler CronTrigger。
    格式：minute hour day month day_of_week
    """
    parts = cron_expression.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Expected 5-field cron, got: {cron_expression!r}")
    minute, hour, day, month, day_of_week = parts
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        timezone=datetime.timezone.utc,  # stdlib UTC: no pytz pickle dependency
    )


# 全局单例
scheduler_manager = SchedulerManager()
