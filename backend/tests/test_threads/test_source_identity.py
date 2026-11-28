"""
tests/test_threads/test_source_identity.py
Thread 来源身份回归：来源独立性必须以稳定 provider 身份（来源 URL
主机名）计算，而不是可修改的任务名。

旧实现用任务名（items 无 source_id 的回退）当身份——重命名任务会
改变聚类结果；同平台的两个任务被当成跨平台共识；一个平台多个采集
入口虚增来源计数。
"""
import json
import uuid

from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.thread_repo import thread_repo
from app.threads.scoring import thread_scorer
from app.utils.url import source_identity


class TestSourceIdentityHelper:
    def test_host_is_stable_identity(self):
        assert source_identity("https://news.ycombinator.com/item?id=1") == (
            "news.ycombinator.com"
        )

    def test_www_prefix_is_normalized(self):
        assert source_identity(
            "https://www.example.com/list"
        ) == source_identity("https://example.com/list")

    def test_empty_url_falls_back(self):
        assert source_identity("", "hn") == "hn"

    def test_malformed_url_falls_back(self):
        assert source_identity("not-a-url", "fallback") == "fallback"


class TestIdentityDrivenSourceScore:
    def _item(self, task_name: str, source_id: str) -> dict:
        return {
            "title": "OpenAI launches GPT-5",
            "task_name": task_name,
            "source_id": source_id,
            "published_at": "2026-09-15T10:00:00Z",
        }

    def _thread(self, source_keys: list[str], platforms: list[str] | None = None) -> dict:
        return {
            "title": "OpenAI launches GPT-5",
            "last_seen_at": "2026-09-15T10:00:00Z",
            "source_keys": source_keys,
            "platforms": platforms if platforms is not None else source_keys,
        }

    def _score(self, item: dict, thread: dict) -> float:
        score = thread_scorer.score(
            item, thread,
            {"entities": {}, "fingerprint": ""},
            {"entities": {}, "fingerprint": ""},
        )
        return score.source_score

    def test_task_rename_does_not_change_score(self):
        """重命名任务只改展示名：身份（主机名）不变 → 同源 0.3。"""
        item = self._item("新名字 HN", "news.ycombinator.com")
        thread = self._thread(["news.ycombinator.com"], platforms=["旧名字 HN"])
        assert self._score(item, thread) == 0.3

    def test_same_platform_tasks_are_not_cross_platform_consensus(self):
        """同平台两个采集任务（同一主机）不得算作跨平台共识。"""
        item_a = self._item("HN 前页", "news.ycombinator.com")
        item_b = self._item("HN Ask", "news.ycombinator.com")
        thread = self._thread(["news.ycombinator.com"], platforms=["HN 前页"])
        assert self._score(item_a, thread) == 0.3
        assert self._score(item_b, thread) == 0.3

    def test_different_providers_are_independent_evidence(self):
        """不同平台主机 → 跨来源共识 1.0。"""
        item = self._item("V2EX", "www.v2ex.com")
        thread = self._thread(["news.ycombinator.com"])
        assert self._score(item, thread) == 1.0

    def test_legacy_thread_without_source_keys_falls_back_to_names(self):
        """旧线程尚未回填 source_keys：退回任务名比较，行为不变。"""
        item = {
            "title": "OpenAI launches GPT-5",
            "task_name": "v2ex",
            "source_id": "www.v2ex.com",
            "published_at": "2026-09-15T10:00:00Z",
        }
        thread = {
            "title": "OpenAI launches GPT-5",
            "last_seen_at": "2026-09-15T10:00:00Z",
            "platforms": ["v2ex"],
        }
        assert self._score(item, thread) == 0.3


class TestSourceKeysPersistence:
    def _task_with_url(self, source_url: str) -> str:
        return task_repo.insert({
            "name": f"身份测试 {uuid.uuid4().hex[:6]}",
            "source_url": source_url,
            "template_id": None,
            "selector_list": "div",
            "selector_title": "h2",
            "selector_link": "a",
            "selector_next_page": None,
            "keywords": [],
            "cron_expression": "0 9 * * *",
        })["id"]

    def _item(self, task_id: str, url: str) -> str:
        item_id = str(uuid.uuid4())
        item_repo.bulk_insert([{
            "id": item_id,
            "task_id": task_id,
            "title": f"条目 {item_id[:6]}",
            "url": url,
            "url_hash": f"src-id-{item_id}",
            "summary": "s",
        }])
        return item_id

    def test_create_persists_source_key(self):
        task_id = self._task_with_url("https://news.ycombinator.com/")
        item_id = self._item(task_id, "https://news.ycombinator.com/item?id=9")

        thread_id = thread_repo.create(
            title="身份 Thread", item_id=item_id, platform="HN",
            source_key="news.ycombinator.com",
        )

        thread = thread_repo.get(thread_id)
        assert thread["source_keys"] == ["news.ycombinator.com"]

    def test_add_item_merges_new_source_key(self):
        task_a = self._task_with_url("https://news.ycombinator.com/")
        task_b = self._task_with_url("https://www.v2ex.com/")
        item_a = self._item(task_a, "https://news.ycombinator.com/item?id=9")
        item_b = self._item(task_b, "https://www.v2ex.com/topic")

        thread_id = thread_repo.create(
            title="跨源 Thread", item_id=item_a, platform="HN",
            source_key="news.ycombinator.com",
        )
        thread_repo.add_item(
            thread_id=thread_id, item_id=item_b, similarity=0.9,
            title="跨源", platform="V2EX", source_key="v2ex.com",
        )

        thread = thread_repo.get(thread_id)
        assert thread["source_keys"] == ["news.ycombinator.com", "v2ex.com"]

    def test_rebuild_stats_backfills_source_keys_from_members(self):
        """统计重建从成员条目的任务 source_url 回填身份——旧线程被触碰
        即自愈，任务改名不影响回填结果。"""
        task_id = self._task_with_url("https://www.juejin.cn/")
        item_id = self._item(task_id, "https://juejin.cn/post/1")

        thread_id = thread_repo.create(title="旧线程", item_id=item_id, platform="掘金")

        # create 未传 source_key（模拟旧数据），重建后应从任务回填
        thread_repo.rebuild_thread_stats(thread_id)
        thread = thread_repo.get(thread_id)
        assert thread["source_keys"] == ["juejin.cn"]
