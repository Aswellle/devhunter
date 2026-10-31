"""
tests/test_threads/test_relations.py
同一故事线关联：near-miss 检测、关联 CRUD、merge 重定向、split 补关联、重建清理。
"""
import uuid
from unittest.mock import patch

from app.core.database import get_db
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.thread_repo import thread_repo
from app.services.thread_service import thread_service
from app.threads import clustering as clustering_module
from app.threads.clustering import ThreadClusteringResult, thread_clusterer
from app.threads.merge import thread_merger
from app.threads.scoring import ThreadScore
from app.threads.split import thread_splitter


def _make_task() -> str:
    return task_repo.insert({
        "name": f"故事线测试任务 {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })["id"]


def _make_items(task_id: str, count: int) -> list[str]:
    token = uuid.uuid4().hex[:8]
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    item_repo.bulk_insert([
        {
            "task_id": task_id,
            "title": f"storyline item {token} #{i}",
            "url": f"https://example.com/storyline/{token}/{i}",
            "url_hash": f"storyline-hash-{token}-{i}",
            "summary": "s",
            "fetched_at": now,
        }
        for i in range(count)
    ])
    items, _ = item_repo.query(task_id=task_id)
    return [it["id"] for it in items]


def _relation_rows() -> list[tuple[str, str, float, str]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT thread_a, thread_b, similarity, source FROM thread_relations"
        ).fetchall()
    return [(r["thread_a"], r["thread_b"], r["similarity"], r["source"]) for r in rows]


class TestRecordRelation:
    """关联 CRUD：规范序、幂等、自关联拒绝、级联清理"""

    def test_canonical_order_and_idempotent(self):
        task_id = _make_task()
        id_a, id_b = _make_items(task_id, 2)
        ta = thread_repo.create("Thread A", id_a, "hn")
        tb = thread_repo.create("Thread B", id_b, "v2ex")

        assert thread_repo.record_relation(ta, tb, 0.38) is True
        # 反向重复写入是幂等空操作；规范序统一为 (小, 大)
        assert thread_repo.record_relation(tb, ta, 0.9) is False
        rows = [r for r in _relation_rows() if {r[0], r[1]} == {ta, tb}]
        assert len(rows) == 1
        a, b, sim, source = rows[0]
        assert a == min(ta, tb) and b == max(ta, tb)
        assert sim == 0.38
        assert source == "auto"

    def test_self_relation_rejected(self):
        assert thread_repo.record_relation("x", "x", 0.5) is False

    def test_get_related_threads_from_both_sides(self):
        task_id = _make_task()
        id_a, id_b = _make_items(task_id, 2)
        ta = thread_repo.create("Thread A", id_a, "hn")
        tb = thread_repo.create("Thread B", id_b, "v2ex")

        thread_repo.record_relation(ta, tb, 0.42)

        rel_a = thread_repo.get_related_threads(ta)
        rel_b = thread_repo.get_related_threads(tb)
        assert len(rel_a) == len(rel_b) == 1
        assert rel_a[0]["id"] == tb
        assert rel_a[0]["title"] == "Thread B"
        assert rel_a[0]["similarity"] == 0.42
        assert rel_b[0]["id"] == ta

    def test_delete_relation(self):
        task_id = _make_task()
        id_a, id_b = _make_items(task_id, 2)
        ta = thread_repo.create("Thread A", id_a, "hn")
        tb = thread_repo.create("Thread B", id_b, "v2ex")
        thread_repo.record_relation(ta, tb, 0.4)

        # 方向无关：按任一端都能删
        assert thread_repo.delete_relation(tb, ta) is True
        assert thread_repo.delete_relation(tb, ta) is False
        assert thread_repo.get_related_threads(ta) == []

    def test_cascade_on_thread_delete(self):
        task_id = _make_task()
        id_a, id_b = _make_items(task_id, 2)
        ta = thread_repo.create("Thread A", id_a, "hn")
        tb = thread_repo.create("Thread B", id_b, "v2ex")
        thread_repo.record_relation(ta, tb, 0.4)

        with get_db() as conn:
            conn.execute("UPDATE items SET thread_id = NULL WHERE thread_id = ?", (ta,))
            conn.execute("DELETE FROM thread_items WHERE thread_id = ?", (ta,))
            conn.execute("DELETE FROM threads WHERE id = ?", (ta,))

        assert thread_repo.get_related_threads(tb) == []


class TestMergeRepointsRelations:
    """合并时关联重定向到目标 Thread"""

    def test_relations_follow_merge(self):
        task_id = _make_task()
        id_a, id_b, id_t = _make_items(task_id, 3)
        ta = thread_repo.create("Thread A", id_a, "hn")
        tb = thread_repo.create("Thread B", id_b, "v2ex")
        tt = thread_repo.create("Thread T", id_t, "jd")

        thread_repo.record_relation(ta, tb, 0.4)
        thread_repo.record_relation(ta, tt, 0.8)
        thread_repo.record_relation(tb, tt, 0.3)

        merged = thread_merger.merge(ta, tt, reason="测试")
        assert merged is not None

        # (A,B) 与 (A,T) 重定向为 (B,T)；(B,T) 已有关联（0.3），
        # INSERT OR IGNORE 保留先写入的，重定向的重复项被忽略
        rel_b = {r["id"]: r for r in thread_repo.get_related_threads(tb)}
        assert set(rel_b) == {tt}
        assert rel_b[tt]["similarity"] == 0.3
        # A 已删除，其关联随级联消失
        assert thread_repo.get_related_threads(ta) == []

    def test_merge_into_related_thread_drops_pair(self):
        task_id = _make_task()
        id_a, id_t = _make_items(task_id, 2)
        ta = thread_repo.create("Thread A", id_a, "hn")
        tt = thread_repo.create("Thread T", id_t, "v2ex")
        thread_repo.record_relation(ta, tt, 0.42)

        thread_merger.merge(ta, tt)

        # source-target 关联与 source 一起消失，不产生自关联
        assert thread_repo.get_related_threads(tt) == []


class TestSplitRecordsRelation:
    """人工拆分后源/新 Thread 自动补一条 split 关联"""

    def test_split_creates_relation_with_moved_similarity(self):
        task_id = _make_task()
        id_a, id_b = _make_items(task_id, 2)
        ta = thread_repo.create("Thread A", id_a, "hn")
        thread_repo.add_item(ta, id_b, similarity=0.42, title="t2", platform="v2ex")

        new_thread = thread_splitter.split(ta, [id_b])
        assert new_thread is not None

        rel = thread_repo.get_related_threads(ta)
        assert len(rel) == 1
        assert rel[0]["id"] == new_thread["id"]
        assert rel[0]["source"] == "split"
        assert rel[0]["similarity"] == 0.42, "关联强度 = 拆出条目对源 Thread 的平均相似度"

    def test_split_syncs_items_thread_id(self):
        """items.thread_id 是 thread 成员关系的外键镜像，拆分必须跟随"""
        task_id = _make_task()
        id_a, id_b = _make_items(task_id, 2)
        ta = thread_repo.create("Thread A", id_a, "hn")
        thread_repo.add_item(ta, id_b, similarity=0.4, title="t2", platform="v2ex")

        new_thread = thread_splitter.split(ta, [id_b])
        assert new_thread is not None

        with get_db() as conn:
            moved = conn.execute(
                "SELECT thread_id FROM items WHERE id = ?", (id_b,)
            ).fetchone()["thread_id"]
            stayed = conn.execute(
                "SELECT thread_id FROM items WHERE id = ?", (id_a,)
            ).fetchone()["thread_id"]
        assert moved == new_thread["id"], "拆出条目指向新 Thread"
        assert stayed == ta, "留存条目仍指向源 Thread"


class TestNearMissClustering:
    """聚类 near-miss：阈值之下的明显相关候选带出关联信号"""

    class _StubScorer:
        def __init__(self, total: float):
            self.total = total

        def score(self, *args, **kwargs) -> ThreadScore:
            s = ThreadScore()
            s.total_score = self.total
            return s

    def _candidates(self) -> list[dict]:
        return [{
            "id": "thread_1",
            "title": "candidate thread title",
            "last_seen_at": "2026-10-31T00:00:00Z",
            "platforms": ["v2ex"],
        }]

    def test_near_miss_creates_with_related_thread(self):
        item = {"title": "related storyline title", "source_id": "hn"}
        with patch.object(clustering_module, "thread_scorer", self._StubScorer(0.38)):
            result = thread_clusterer.cluster(item, self._candidates())

        assert result.action == "create"
        assert result.thread_id is None
        assert result.related_thread_id == "thread_1"
        assert result.match_reason.startswith("storyline_near_miss")
        assert result.to_dict()["related_thread_id"] == "thread_1"

    def test_above_threshold_joins_without_relation(self):
        item = {"title": "same event", "source_id": "hn"}
        with patch.object(clustering_module, "thread_scorer", self._StubScorer(0.55)):
            result = thread_clusterer.cluster(item, self._candidates())

        assert result.action == "join"
        assert result.thread_id == "thread_1"
        assert result.related_thread_id is None

    def test_below_storyline_threshold_is_plain_create(self):
        item = {"title": "unrelated", "source_id": "hn"}
        with patch.object(clustering_module, "thread_scorer", self._StubScorer(0.20)):
            result = thread_clusterer.cluster(item, self._candidates())

        assert result.action == "create"
        assert result.related_thread_id is None


class TestNearMissServiceIntegration:
    """服务层接线：near-miss 创建新 Thread 并落一条关联"""

    def test_compute_records_relation_on_near_miss(self):
        task_id = _make_task()
        _make_items(task_id, 2)
        items, _ = item_repo.query(task_id=task_id)

        # 第一次调用走真实 create；第二次返回指向首个 Thread 的 near-miss
        def scripted_cluster(new_item, candidate_threads, threshold=None, **kwargs):
            if not scripted_cluster.created_id:
                return ThreadClusteringResult(action="create")
            return ThreadClusteringResult(
                action="create",
                score=None,
                match_reason="storyline_near_miss,score=0.38",
                related_thread_id=scripted_cluster.created_id,
            )

        scripted_cluster.created_id = None

        with patch("app.services.thread_service.thread_clusterer") as fake:
            fake.cluster.side_effect = scripted_cluster
            thread_service.compute_threads_for_items([dict(items[0])])
            threads, _ = thread_repo.list_all(task_id=task_id)
            scripted_cluster.created_id = threads[0]["id"]
            thread_service.compute_threads_for_items([dict(items[1])])

        detail = thread_service.get_thread(scripted_cluster.created_id)
        assert len(detail["related_threads"]) == 1
        related = detail["related_threads"][0]
        assert related["title"] == items[1]["title"]
        assert related["source"] == "auto"
        assert related["similarity"] == 0.0, "无评分对象时关联强度记 0"


class TestRecomputeClearsRelations:
    """重建清空全部关联（重放聚类会按 near-miss 规则重新生成）"""

    def test_delete_all_clears_relations(self):
        task_id = _make_task()
        id_a, id_b = _make_items(task_id, 2)
        ta = thread_repo.create("Thread A", id_a, "hn")
        tb = thread_repo.create("Thread B", id_b, "v2ex")
        thread_repo.record_relation(ta, tb, 0.4)

        thread_repo.delete_all()

        assert _relation_rows() == []


class TestRelationsSummary:
    """列表批量关联摘要"""

    def test_counts_and_top(self):
        task_id = _make_task()
        id_a, id_b, id_c = _make_items(task_id, 3)
        ta = thread_repo.create("Thread A", id_a, "hn")
        tb = thread_repo.create("Thread B", id_b, "v2ex")
        tc = thread_repo.create("Thread C", id_c, "jd")

        thread_repo.record_relation(ta, tb, 0.35)
        thread_repo.record_relation(ta, tc, 0.41)

        summary = thread_repo.get_relations_summary([ta, tb])
        assert summary[ta]["count"] == 2
        assert summary[ta]["top"]["title"] == "Thread C", "top 取相似度最高的关联方"
        assert summary[tb]["count"] == 1
        assert summary[tb]["top"]["title"] == "Thread A"

    def test_empty_ids(self):
        assert thread_repo.get_relations_summary([]) == {}
