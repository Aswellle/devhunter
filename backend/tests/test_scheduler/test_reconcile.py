"""
tests/test_scheduler/test_reconcile.py
Task/Scheduler 对账回归：DB 期望状态与 JobStore 实际投影的漂移必须
能被发现、收敛和观测。

旧实现只在启动时 restore，add/reschedule/remove 失败仅记日志——
DB 里 active 的任务可能长期没有 Job（永不执行），删除的任务可能
残留幽灵 Job，且没有任何可观测途径。
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.repositories.task_repo import task_repo
from app.scheduler.manager import SchedulerManager

client = TestClient(app)


class _FakeJob:
    def __init__(self, job_id, trigger, store=None):
        self.id = job_id
        self.trigger = trigger
        self._store = store

    def remove(self):
        if self._store is not None:
            self._store.pop(self.id, None)

    def reschedule(self, trigger):
        self.trigger = trigger


class _FakeScheduler:
    """调度器最小替身：记录 add/remove/reschedule。"""

    def __init__(self):
        self.jobs: dict[str, _FakeJob] = {}
        self.added: list[str] = []

    def get_jobs(self):
        return list(self.jobs.values())

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def add_job(self, func, trigger=None, id=None, **kwargs):
        self.jobs[id] = _FakeJob(id, trigger, store=self.jobs)
        self.added.append(id)


def _fresh_manager() -> SchedulerManager:
    """真实 manager + 替身调度器：测对账逻辑，不启动真调度器。"""
    m = SchedulerManager()
    m._scheduler = _FakeScheduler()
    return m

    # m._scheduler 引用在旧版测试中使用，现已由 _FakeJob(store=...) 取代


def _task(cron: str = "0 9 * * *", status: str = "active") -> str:
    return task_repo.insert({
        "name": f"对账 {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "template_id": None,
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "selector_next_page": None,
        "keywords": [],
        "cron_expression": cron,
        "status": status,
    })["id"]


class TestReconcile:
    def test_reconcile_adds_missing_job(self):
        """DB active 但 JobStore 无 Job → 对账补注册。"""
        m = _fresh_manager()
        task_id = _task()

        report = m.reconcile()

        assert task_id in report["added"]
        assert task_id in m._scheduler.jobs

    def test_reconcile_removes_orphan_job(self):
        """JobStore 有 Job 但 DB 无对应 active 任务 → 对账移除幽灵 Job。"""
        m = _fresh_manager()
        m._scheduler.jobs["ghost-id"] = _FakeJob(
            "ghost-id", "cron[x]", store=m._scheduler.jobs)

        report = m.reconcile()

        assert "ghost-id" in report["removed"]
        assert "ghost-id" not in m._scheduler.jobs

    def test_reconcile_preserves_system_and_manual_jobs(self):
        """系统 Job 与手动触发残留 Job 不在对账移除范围。"""
        m = _fresh_manager()
        for jid in ("__system_cleanup__", f"t{uuid.uuid4().hex[:4]}_manual"):
            m._scheduler.jobs[jid] = _FakeJob(jid, "cron[x]", store=m._scheduler.jobs)

        report = m.reconcile()

        assert not report["removed"], "系统/手动 Job 不得被对账移除"
        assert set(m._scheduler.jobs) >= {"__system_cleanup__"}

    def test_reconcile_reschedules_stale_trigger(self):
        """Cron 改了但 Job trigger 未同步 → 对账重排。"""
        m = _fresh_manager()
        task_id = _task(cron="30 20 * * *")
        m._scheduler.jobs[task_id] = _FakeJob(
            task_id, "cron[hour='9', minute='0']", store=m._scheduler.jobs)

        report = m.reconcile()

        assert task_id in report["rescheduled"]
        assert m._scheduler.jobs[task_id].trigger is not None

    def test_reconcile_survives_task_load_failure(self, monkeypatch):
        """DB 读失败不抛异常，错误进入报告（可观测）。"""
        m = _fresh_manager()
        from app.repositories import task_repo as tr_module
        # manager 内部以 task_repo 单例调用 list_active
        monkeypatch.setattr(tr_module.task_repo, "list_active",
                            lambda: (_ for _ in ()).throw(RuntimeError("db down")))

        report = m.reconcile()

        assert report["errors"], "失败必须留在报告里而不是静默"
        assert m.last_reconcile_report is not None

    def test_drift_report_lists_missing_jobs(self):
        """漂移报告：active 无 Job 的任务可见（供 UI 展示启用但未调度）。"""
        m = _fresh_manager()
        task_id = _task()

        drift = m.drift_report()

        assert any(d["task_id"] == task_id for d in drift["missing_jobs"])
        assert drift["scheduler_running"] is False


class TestSchedulerApi:
    def test_scheduler_status_endpoint(self):
        token = create_access_token({"sub": "admin"})
        resp = client.get("/api/tasks/scheduler-status",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert "missing_jobs" in body
        assert "last_reconcile" in body

    def test_scheduler_reconcile_endpoint(self):
        token = create_access_token({"sub": "admin"})
        resp = client.post("/api/tasks/scheduler-reconcile",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert "added" in body and "removed" in body and "errors" in body
