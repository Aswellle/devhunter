"""
tests/test_api/test_tasks_api.py
任务详情接口的回归测试。
"""
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.repositories.task_repo import task_repo

client = TestClient(app)


def _auth_headers():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


def _task(cron: str = "0 9 * * *") -> str:
    return task_repo.insert({
        "name": "cron 回填任务",
        "source_url": "https://example.com/",
        "template_id": None,
        "selector_list": "div.item",
        "selector_title": "a",
        "selector_link": "a",
        "selector_summary": None,
        "selector_next_page": None,
        "keywords": [],
        "cron_expression": cron,
    })["id"]


class TestTaskDetailIncludesSchedule:
    """
    详情接口必须返回 cron_expression。

    前端「编辑配置」用详情接口回填表单；该字段缺失时频率控件初值为空，
    用户一保存就会把原有调度改掉/清空（曾经就是这个状态）。
    """

    def test_detail_and_list_expose_cron_expression(self):
        task_id = _task("0 9 * * *")
        headers = _auth_headers()

        detail = client.get(f"/api/tasks/{task_id}", headers=headers).json()
        assert detail.get("cron_expression") == "0 9 * * *"

        listed = client.get("/api/tasks", params={"per_page": 100}, headers=headers).json()
        row = next(t for t in listed["items"] if t["id"] == task_id)
        assert row["cron_expression"] == "0 9 * * *"
