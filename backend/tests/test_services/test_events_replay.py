"""
tests/test_services/test_events_replay.py
SSE 断线补发的仓储层回归：Last-Event-ID 游标按任务维度取事件。

历史缺陷：事件持久化时 execution_id 落的是 task_id（engine 事件不携带
execution_id），而重放查询用 task_executions 的真执行 id——永远匹配
不到，重放恒为空，重连客户端静默丢失断线期间的事件。
端点行为（含无效游标静默为空）由实机 curl 冒烟覆盖。
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.core.database import get_db
from app.repositories.execution_event_repo import execution_event_repo
from app.repositories.task_repo import task_repo


def _task_with_events(count: int = 4) -> tuple[str, list[str]]:
    task_id = task_repo.insert({
        "name": f"重放测试任务 {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })["id"]
    now = datetime.now(timezone.utc)
    ids = []
    for i in range(count):
        row = execution_event_repo.record(
            execution_id=task_id,  # 与真实写入路径一致：execution_id 落 task_id
            task_id=task_id,
            event_type="fetch_done" if i < count - 1 else "success",
            message=f"event {i}",
            data={},
        )
        # 同秒写入的 created_at 相同会破坏游标比较，逐条推开
        with get_db() as conn:
            conn.execute(
                "UPDATE execution_events SET created_at = ? WHERE id = ?",
                ((now + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"), row["id"]),
            )
        ids.append(row["id"])
    return task_id, ids


class TestListByTaskAfter:
    def test_returns_events_after_cursor_in_order(self):
        """游标指向第 1 条 → 其后全部按时间正序补发（含终态事件）"""
        task_id, ids = _task_with_events(4)

        rows = execution_event_repo.list_by_task_after(task_id, after_id=ids[0])

        assert [r["id"] for r in rows] == ids[1:]
        assert rows[-1]["event_type"] == "success"

    def test_cursor_at_last_event_returns_empty(self):
        """游标已在最新事件 → 无需补发"""
        task_id, ids = _task_with_events(3)

        assert execution_event_repo.list_by_task_after(task_id, after_id=ids[-1]) == []

    def test_invalid_cursor_returns_empty(self):
        """占位/未知游标（子查询 NULL）→ 安静返回空，不报错"""
        task_id, _ = _task_with_events(2)

        assert execution_event_repo.list_by_task_after(task_id, after_id="0") == []

    def test_scoped_to_task(self):
        """只补发本任务的事件，他任务事件不串流"""
        task_id, ids = _task_with_events(2)
        other_id, _ = _task_with_events(2)

        rows = execution_event_repo.list_by_task_after(task_id, after_id=ids[0])

        assert {r["task_id"] for r in rows} == {task_id}


# ── seq 游标：同毫秒事件不漏发（时间戳游标的盲区）────────────────

def _record_same_ms(task_id: str, count: int, ms_ts: str) -> list[dict]:
    return [
        execution_event_repo.record(
            execution_id=task_id,
            task_id=task_id,
            event_type="fetch_done",
            message=f"same-ms {i}",
            data={},
            created_at=ms_ts,
        )
        for i in range(count)
    ]


class TestSeqCursor:
    def test_record_returns_globally_unique_monotonic_seq(self):
        task_a, _ = _task_with_events(2)
        task_b, _ = _task_with_events(2)
        rows = (
            execution_event_repo.list_by_task(task_a, limit=10)
            + execution_event_repo.list_by_task(task_b, limit=10)
        )
        seqs = [r["seq"] for r in rows]
        assert len(set(seqs)) == len(seqs), "seq 必须全局唯一"

    def test_same_millisecond_events_are_not_skipped(self):
        """同一毫秒内连续写入 3 条，游标停在第 1 条：时间戳比较
        （created_at > cursor.created_at）会把第 2、3 条漏掉，
        seq 游标必须一条不漏。"""
        task_id, _ = _task_with_events(0)
        rows = _record_same_ms(task_id, 3, "2026-11-28T04:00:00.100Z")

        missed = execution_event_repo.list_by_task_after(task_id, after_id=rows[0]["id"])

        assert [r["id"] for r in missed] == [rows[1]["id"], rows[2]["id"]]

    def test_after_seq_cursor_returns_strictly_later_events(self):
        task_id, _ = _task_with_events(3)
        all_rows = execution_event_repo.list_by_task(task_id, limit=10)
        seqs = sorted(r["seq"] for r in all_rows)

        missed = execution_event_repo.list_by_task_after(task_id, after_seq=seqs[0])

        assert [r["seq"] for r in missed] == seqs[1:]

    def test_legacy_uuid_cursor_maps_to_seq(self):
        """旧客户端发来的 Last-Event-ID 是事件 uuid：按其 seq 继续，
        同毫秒内排在其后的事件不得被漏掉。"""
        task_id, _ = _task_with_events(0)
        rows = _record_same_ms(task_id, 3, "2026-11-28T04:00:00.200Z")

        missed = execution_event_repo.list_by_task_after(task_id, after_seq=rows[0]["seq"])

        assert [r["id"] for r in missed] == [rows[1]["id"], rows[2]["id"]]

    def test_unknown_uuid_cursor_replays_nothing(self):
        """无法解析的旧游标保持旧行为：安静返回空（等价从头订阅）。"""
        task_id, _ = _task_with_events(2)
        assert execution_event_repo.list_by_task_after(task_id, after_id="no-such-id") == []


# ── 水位线：replay/live 去重协议原语 ─────────────────────────────

class TestWatermarkProtocol:
    def test_max_seq_returns_latest(self):
        task_id, _ = _task_with_events(3)
        seqs = sorted(r["seq"] for r in execution_event_repo.list_by_task(task_id, limit=10))
        assert execution_event_repo.max_seq() == seqs[-1]

    def test_up_to_seq_bounds_replay_window(self):
        """补发窗口 (cursor, watermark]：水位线之后的事件留给实时通道，
        不在补发结果中重复出现。"""
        task_id, _ = _task_with_events(4)
        seqs = sorted(r["seq"] for r in execution_event_repo.list_by_task(task_id, limit=10))

        rows = execution_event_repo.list_by_task_after(
            task_id, after_seq=seqs[0], up_to_seq=seqs[2],
        )

        assert [r["seq"] for r in rows] == seqs[1:3]
