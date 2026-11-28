"""
tests/test_api/test_readiness.py
OPS-001：liveness 与 readiness 分离回归。

- /api/health 只回答进程存活（liveness），永远轻量；
- /api/ready 回答"能否对外服务"（readiness）：DB 可读写、迁移游标已到
  最新版本、Scheduler 已启动。任一失败返回 503，便于容器/网关撤流。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestLiveness:
    def test_health_stays_ok_regardless_of_readiness(self, monkeypatch):
        """/api/health 是 liveness：DB 抛错也不影响进程存活判定。"""
        import app.core.database as db

        monkeypatch.setattr(db, "get_connection",
                            lambda: (_ for _ in ()).throw(RuntimeError("db down")))
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestReadiness:
    def test_ready_when_db_and_scheduler_ok(self, monkeypatch):
        from app.scheduler import manager as mgr
        monkeypatch.setattr(mgr.scheduler_manager, "_started", True, raising=False)

        resp = client.get("/api/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["checks"]["db"] == "ok"
        assert body["checks"]["scheduler"] == "ok"

    def test_not_ready_when_db_unavailable(self, monkeypatch):
        import app.core.database as db
        from app.scheduler import manager as mgr

        monkeypatch.setattr(mgr.scheduler_manager, "_started", True, raising=False)
        monkeypatch.setattr(db, "get_connection",
                            lambda: (_ for _ in ()).throw(RuntimeError("db down")))

        resp = client.get("/api/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["db"].startswith("error")

    def test_not_ready_when_scheduler_stopped(self, monkeypatch):
        from app.scheduler import manager as mgr
        monkeypatch.setattr(mgr.scheduler_manager, "_started", False, raising=False)

        resp = client.get("/api/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["checks"]["scheduler"] == "stopped"

    def test_not_ready_when_migrations_behind(self, monkeypatch):
        """迁移游标落后于最新文件 → not_ready（避免半迁移状态对外服务）。"""
        import app.api.outlets as outlets

        monkeypatch.setattr(outlets, "_latest_migration_version", lambda: 999)
        from app.scheduler import manager as mgr
        monkeypatch.setattr(mgr.scheduler_manager, "_started", True, raising=False)

        resp = client.get("/api/ready")
        assert resp.status_code == 503
        assert "migration" in resp.json()["checks"]

    def test_ready_response_is_lightweight_json(self):
        from app.scheduler import manager as mgr
        mgr.scheduler_manager._started = True
        resp = client.get("/api/ready")
        assert resp.headers["content-type"].startswith("application/json")
        assert set(resp.json()) >= {"status", "checks"}
