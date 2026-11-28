"""
tests/test_repositories/test_task_repo_status.py
任务插入必须保留调用方指定的 status（回归）。

旧实现 INSERT 语句把 status 硬编码为 'active'：向导"验证失败保存为
草稿"与 OPML 导入的 paused 意图全部失效——草稿任务被启用并被定时调度。
"""
import uuid

from app.repositories.task_repo import task_repo


def _payload(status=None) -> dict:
    data = {
        "name": f"状态回归 {uuid.uuid4().hex[:6]}",
        "source_url": "https://feed.example.com/rss",
        "selector_list": "rss:",
        "selector_title": "rss:title",
        "selector_link": "rss:link",
        "cron_expression": "0 9 * * *",
    }
    if status is not None:
        data["status"] = status
    return data


class TestTaskInsertStatus:
    def test_paused_status_is_persisted(self):
        task = task_repo.insert(_payload("paused"))
        assert task["status"] == "paused"

    def test_active_status_is_persisted(self):
        task = task_repo.insert(_payload("active"))
        assert task["status"] == "active"

    def test_default_status_is_active(self):
        task = task_repo.insert(_payload())
        assert task["status"] == "active"

    def test_unknown_status_falls_back_to_active(self):
        """非法状态值不得写库（CHECK 约束的表外注入防护）。"""
        task = task_repo.insert(_payload("bogus"))
        assert task["status"] == "active"
