"""
tests/test_api/test_stats.py
Stats API 单元测试 - GET /api/stats
"""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app

client = TestClient(app)


def _auth_headers():
    """生成认证 header"""
    token = create_access_token({"sub": "admin"})
    return {"Authorization": f"Bearer {token}"}


class TestStatsAPI:
    """统计 API 测试"""

    def test_stats_returns_200_with_auth(self):
        """认证用户可访问统计接口"""
        response = client.get("/api/stats", headers=_auth_headers())
        assert response.status_code == 200

    def test_stats_returns_401_without_auth(self):
        """未认证用户返回 401"""
        response = client.get("/api/stats")
        assert response.status_code == 401

    def test_stats_response_structure(self):
        """返回数据结构完整"""
        response = client.get("/api/stats", headers=_auth_headers())
        data = response.json()

        # 验证顶层字段
        assert "total_items" in data
        assert "items_today" in data
        assert "executions_today" in data
        assert "tasks" in data
        assert "success_rate_7d" in data
        assert "total_executions_7d" in data
        assert "failures_7d" in data
        assert "daily_items" in data
        assert "top_tasks_7d" in data

    def test_stats_tasks_structure(self):
        """任务状态分布结构正确"""
        response = client.get("/api/stats", headers=_auth_headers())
        tasks = response.json()["tasks"]

        assert "active" in tasks
        assert "paused" in tasks
        assert "error" in tasks
        assert "total" in tasks

    def test_stats_empty_database(self):
        """空数据库返回零值而非报错"""
        response = client.get("/api/stats", headers=_auth_headers())
        data = response.json()

        assert isinstance(data["total_items"], int)
        assert isinstance(data["items_today"], int)
        assert isinstance(data["tasks"]["total"], int)
        assert isinstance(data["daily_items"], list)
        assert isinstance(data["top_tasks_7d"], list)

    def test_stats_daily_items_format(self):
        """每日数据格式正确"""
        response = client.get("/api/stats", headers=_auth_headers())
        daily = response.json()["daily_items"]

        for entry in daily:
            assert "date" in entry
            assert "count" in entry
