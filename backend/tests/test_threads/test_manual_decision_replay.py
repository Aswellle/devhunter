"""
tests/test_threads/test_manual_decision_replay.py
人工纠错跨重建重放回归（ADR-001 / THR-001）。

旧实现的人工 merge/split/解除关联以一次性 Thread UUID 为键，全量重建
生成新 ID 后全部失效——算法会重新犯用户已纠正过的错误。
决策改按成员条目 ID（稳定身份）存储，重建后重放。
"""
import uuid
from datetime import datetime, timezone

from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.thread_repo import thread_repo
from app.services.thread_service import thread_service


def _seed_items(titles: list[str]) -> list[str]:
    task_id = task_repo.insert({
        "name": f"决策重放 {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })["id"]
    token = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    item_repo.bulk_insert([
        {
            "task_id": task_id,
            "title": f"{t} {token}",
            "url": f"https://example.com/decision/{token}/{i}",
            "url_hash": f"decision-hash-{token}-{i}",
            "summary": "s",
            "fetched_at": now,
        }
        for i, t in enumerate(titles)
    ])
    items = item_repo.list_all_chronological()
    by_prefix = {}
    for it in items:
        by_prefix.setdefault(it["title"].rsplit(" ", 1)[0], it["id"])
    return [by_prefix[t] for t in titles]


def _thread_of(item_id: str) -> str | None:
    return (item_repo.get(item_id) or {}).get("thread_id")

def _single_thread(item_id: str) -> str:
    # 聚合接口要求 >=2 条：单条锚点 Thread 直接经仓储创建（与
    # 算法自动创建的单条 Thread 等价）
    tid = thread_repo.create(title="决策锚点", item_id=item_id, platform="test")
    thread_repo.rebuild_thread_stats(tid)
    return tid


class TestMergeDecisionReplay:
    def test_manual_merge_survives_rebuild(self):
        """人工合并的两个 Thread，重建后必须仍聚合在一起——
        旧实现重建后算法立刻把它们拆回去。"""
        a1, a2 = _seed_items(["alpha topic", "alpha issue"])
        b1 = _seed_items(["beta story"])[0]

        t_a = thread_service.aggregate_items([a1, a2])["id"]
        t_b = _single_thread(b1)
        assert t_a and t_b and t_a != t_b

        merged = thread_service.merge_threads(t_b, t_a, reason="decision replay test")
        assert merged is not None

        thread_service.recompute_all_threads()

        threads = {_thread_of(i) for i in (a1, a2, b1)}
        assert len(threads) == 1, "人工合并的成员重建后必须仍在同一 Thread"
        assert None not in threads


class TestSplitDecisionReplay:
    def test_manual_split_survives_rebuild(self):
        """人工拆出的条目，重建后不得又被算法聚回原 Thread。"""
        a1, a2, a3 = _seed_items(["alpha topic", "alpha issue", "alpha problem"])
        t = thread_service.aggregate_items([a1, a2, a3])["id"]

        split = thread_service.split_thread(t, [a3])
        assert split is not None
        assert _thread_of(a3) != _thread_of(a1)

        thread_service.recompute_all_threads()

        assert _thread_of(a3) != _thread_of(a1), "拆分决策重建后必须仍然成立"
        assert _thread_of(a1) == _thread_of(a2)


class TestRejectDecisionReplay:
    def test_unlink_suppresses_auto_relation_after_rebuild(self):
        """解除关联的两侧，重建后重新登记 reject_merge：
        自动关联/合并守卫按新 Thread ID 继续生效。"""
        a1 = _seed_items(["alpha topic"])[0]
        b1 = _seed_items(["zeta subject"])[0]

        t_a = _single_thread(a1)
        t_b = _single_thread(b1)
        # 解除关联的前提：两 Thread 间存在自动故事线关联（near-miss）
        thread_repo.record_relation(t_a, t_b, similarity=0.4, source="auto")

        assert thread_service.unlink_related_thread(t_a, t_b) is True

        thread_service.recompute_all_threads()

        new_a = _thread_of(a1)
        new_b = _thread_of(b1)
        assert new_a and new_b and new_a != new_b
        assert thread_repo.is_pair_rejected(new_a, new_b), (
            "重建后 reject 仲裁必须按新 Thread ID 重新登记"
        )
