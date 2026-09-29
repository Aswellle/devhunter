"""
tests/test_scheduler/test_jobs.py
执行链路回归测试。

覆盖两类线上事故（均表现为"抓取成功但结果为空"）：

1. 手动触发（preset_exec=True）时 _run_task 使用了未在该函数作用域导入的
   execution_repo → 整轮执行以 NameError 结束，事务回滚，一条都不入库；
   执行历史里只留下一句内部异常文本。
2. 缺必填配置（来源 URL / 三个选择器）的任务仍可被触发执行，engine 抓不到
   任何东西，用户看到的是误导性的「采集完成但无数据（Selector 可能已失效）」。
"""
import uuid
from datetime import datetime, timezone

from app.crawler.engine import CrawlItem, CrawlResult
from app.repositories.execution_repo import execution_repo
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.scheduler import jobs


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _task(**overrides) -> str:
    """写入一条合法任务，返回 task_id。"""
    data = {
        "name": "回归任务",
        "source_url": "https://example.com/",
        "template_id": None,
        "selector_list": "div.item",
        "selector_title": "a.title",
        "selector_link": "a.title",
        "selector_summary": None,
        "selector_next_page": None,
        "keywords": [],
        "cron_expression": "0 9 * * *",
    }
    data.update(overrides)
    return task_repo.insert(data)["id"]


def _stub_result(count: int = 2) -> CrawlResult:
    items = [
        CrawlItem(
            title=f"标题 {i}",
            url=f"https://example.com/post/{i}",
            summary=f"摘要 {i}",
            url_hash=f"stub-hash-{i}",
        )
        for i in range(count)
    ]
    return CrawlResult(items=items, list_count=count, pages_fetched=1)


class TestConfigGuard:
    """必填配置校验"""

    def test_validate_task_config_accepts_complete_config(self):
        assert jobs.validate_task_config({
            "source_url": "https://a.com/",
            "selector_list": "div",
            "selector_title": "a",
            "selector_link": "a",
        }) == []

    def test_validate_task_config_lists_missing_labels(self):
        missing = jobs.validate_task_config({
            "source_url": "https://a.com/",
            "selector_list": "   ",
            "selector_title": "a",
            "selector_link": None,
        })
        assert missing == ["列表项 Selector", "链接 Selector"]

    def test_incomplete_config_fails_without_fetching(self, monkeypatch):
        """配置不完整 → 明确失败，且不发起抓取。"""
        task_id = _task(selector_title="")
        exec_id = str(uuid.uuid4())
        execution_repo.create_running(exec_id, task_id, _iso())

        def _boom(**kwargs):
            raise AssertionError("配置不完整时不应发起抓取")

        monkeypatch.setattr("app.crawler.engine.fetch_and_parse", _boom)
        jobs.execute_task(task_id, exec_id=exec_id, _skip_lock=True)

        row = execution_repo.get(exec_id)
        assert row["status"] == "failure"
        assert "标题 Selector" in row["error_message"]
        assert row["items_fetched"] == 0


class TestManualTriggerPersistence:
    """手动触发（preset_exec=True）的落库路径"""

    def test_run_saves_items_and_finalizes_execution(self, monkeypatch):
        """抓取成功时必须真正写入 items 并把 execution 置为 success。"""
        task_id = _task()
        exec_id = str(uuid.uuid4())
        execution_repo.create_running(exec_id, task_id, _iso())
        monkeypatch.setattr("app.crawler.engine.fetch_and_parse",
                            lambda **kwargs: _stub_result(2))

        jobs.execute_task(task_id, exec_id=exec_id, _skip_lock=True)

        row = execution_repo.get(exec_id)
        assert row["status"] == "success"
        assert (row["items_fetched"], row["items_new"]) == (2, 2)

        items, total = item_repo.query(task_id=task_id)
        assert total == 2, "preset_exec 事务内的 bulk_insert 必须真正写库"
        # dedup 会用 compute_url_hash(url) 覆写 url_hash，所以按 URL 断言
        assert {i["url"] for i in items} == {
            "https://example.com/post/0", "https://example.com/post/1",
        }

    def test_run_without_new_items_keeps_execution_out_of_running(self, monkeypatch):
        task_id = _task()
        exec_id = str(uuid.uuid4())
        execution_repo.create_running(exec_id, task_id, _iso())
        monkeypatch.setattr("app.crawler.engine.fetch_and_parse",
                            lambda **kwargs: _stub_result(0))

        jobs.execute_task(task_id, exec_id=exec_id, _skip_lock=True)

        row = execution_repo.get(exec_id)
        assert row["status"] == "warning"
        assert row["items_new"] == 0
