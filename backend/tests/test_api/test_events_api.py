"""
tests/test_api/test_events_api.py
SSE 端点的 seq 游标回归：同毫秒事件补发不漏、原生 id: 帧往返、
029 迁移后全局 seq 唯一。

TestClient 的 ASGI 传输会缓冲完整响应体——无限 SSE 生成器会把测试
挂死。因此每个用例先建立游标补发场景，再由后台线程驱动请求、主线程
在端点订阅后发布终态事件让生成器自然返回。
"""
import re
import threading
import time
import uuid

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.event_bus import publish_event
from app.core.security import create_access_token
from app.main import app
from app.repositories.execution_event_repo import execution_event_repo
from app.repositories.task_repo import task_repo

client = TestClient(app)


def _auth_headers():
    token = create_access_token({"sub": "admin"})
    return {"Authorization": f"Bearer {token}"}


def _task() -> str:
    return task_repo.insert({
        "name": f"SSE 游标 {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })["id"]


def _record_same_ms(task_id: str, count: int, ms_ts: str) -> list[dict]:
    return [
        execution_event_repo.record(
            execution_id=task_id, task_id=task_id,
            event_type="fetch_done", message=f"same-ms {i}", data={},
            created_at=ms_ts,
        )
        for i in range(count)
    ]


def _drive_stream(path: str, headers: dict, result: dict) -> None:
    with client.stream("GET", path, headers=headers) as resp:
        resp.read()  # 缓冲完整响应体（流在终态事件后自然结束）
        result["status"] = resp.status_code
        result["text"] = resp.text


def _finish_with_terminal(task_id: str, driver: threading.Thread, delay: float = 1.0):
    """端点订阅后发布终态事件，让无限心跳的 SSE 生成器自然结束。"""
    time.sleep(delay)
    publish_event(task_id, "success", "测试终态", {})
    driver.join(timeout=15)
    assert not driver.is_alive(), "SSE 流未在终态事件后结束"


class TestSeqMigration:
    def test_global_seq_is_unique_after_migration(self):
        """029 迁移重排历史行并建唯一索引：全表 seq 无重复。"""
        task_id = _task()
        for _ in range(3):
            execution_event_repo.record(
                execution_id=task_id, task_id=task_id,
                event_type="fetch_done", message="m", data={},
            )
        with get_db() as conn:
            total, distinct = conn.execute(
                "SELECT COUNT(*), COUNT(DISTINCT seq) FROM execution_events"
            ).fetchone()
        assert total == distinct, "seq 必须全表唯一"

    def test_unique_index_exists(self):
        with get_db() as conn:
            indexes = {
                r[1] for r in conn.execute(
                    "PRAGMA index_list(execution_events)"
                ).fetchall()
            }
        assert "uq_execution_events_seq" in indexes
        assert "idx_execution_events_task_seq" in indexes


class TestSseSeqRoundTrip:
    def test_replay_after_seq_cursor_emits_native_id_frames(self):
        """Last-Event-ID=<seq> 重连：同毫秒后续事件全部补发，
        每帧带原生 id: <seq>，补发与实时帧的 seq 严格递增。"""
        task_id = _task()
        rows = _record_same_ms(task_id, 3, "2026-11-28T05:00:00.100Z")

        headers = {**_auth_headers(), "Last-Event-ID": str(rows[0]["seq"])}
        result: dict = {}
        driver = threading.Thread(
            target=_drive_stream,
            args=(f"/api/tasks/{task_id}/events", headers, result),
            daemon=True,
        )
        driver.start()
        _finish_with_terminal(task_id, driver)

        assert result["status"] == 200
        ids = re.findall(r"^id: (\d+)$", result["text"], re.MULTILINE)
        # 补发：同毫秒内排在校验点之后的两条；实时：终态事件一条
        assert ids[:2] == [str(rows[1]["seq"]), str(rows[2]["seq"])]
        assert len(ids) == 3
        assert all(int(a) < int(b) for a, b in zip(ids, ids[1:]))

    def test_legacy_uuid_last_event_id_still_replays(self):
        """旧客户端回传事件 uuid：按其 seq 续传，同毫秒后续不漏。"""
        task_id = _task()
        rows = _record_same_ms(task_id, 2, "2026-11-28T05:00:00.200Z")

        headers = {**_auth_headers(), "Last-Event-ID": rows[0]["id"]}
        result: dict = {}
        driver = threading.Thread(
            target=_drive_stream,
            args=(f"/api/tasks/{task_id}/events", headers, result),
            daemon=True,
        )
        driver.start()
        _finish_with_terminal(task_id, driver)

        ids = re.findall(r"^id: (\d+)$", result["text"], re.MULTILINE)
        # 补发 1 条（同毫秒后续）+ 实时终态 1 条
        assert ids[0] == str(rows[1]["seq"])
        assert len(ids) == 2 and int(ids[0]) < int(ids[1])


class TestSeqUpgradePath:
    def test_upgrade_from_pre029_db_renumbers_global_seq(self):
        """模拟 019 时代的旧库（seq 按执行内编号、跨执行重复）升级到
        029：历史行被全局重排、唯一索引生效、执行内顺序不变。"""
        import shutil
        import sqlite3
        import tempfile
        from pathlib import Path

        from app.core import config, database

        fd, raw_path = tempfile.mkstemp(suffix=".db", prefix="dh_upgrade_")
        import os
        os.close(fd)

        real_migrations = database.MIGRATIONS_DIR
        try:
            # 1) 只应用 001–019，构造旧版本库
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                for f in sorted(real_migrations.glob("*.sql")):
                    from app.core.database import _migration_version
                    if (_migration_version(f) or 0) <= 19:
                        shutil.copy(f, tmp_dir / f.name)
                config.settings.db_path = raw_path
                database.MIGRATIONS_DIR = tmp_dir
                database.init_database()

            conn = sqlite3.connect(raw_path, isolation_level=None)
            try:
                assert conn.execute("PRAGMA user_version").fetchone()[0] == 19
                # 旧写入路径：两个执行各自 seq 1..2，同毫秒 created_at
                for i, exec_id in enumerate(("exec-a", "exec-b")):
                    for n in (1, 2):
                        conn.execute(
                            "INSERT INTO execution_events"
                            " (id, execution_id, task_id, event_type, message,"
                            "  data, created_at, seq) VALUES"
                            " (?, ?, 't', 'fetch_done', ?, '{}',"
                            "  '2026-11-28T05:00:00.100Z', ?)",
                            (f"old-{i}-{n}", exec_id, f"old {n}", n),
                        )
            finally:
                conn.close()

            # 2) 指回真实迁移目录升级（020–029 全部补齐）
            database.MIGRATIONS_DIR = real_migrations
            database.init_database()

            conn = sqlite3.connect(raw_path, isolation_level=None)
            try:
                rows = conn.execute(
                    "SELECT execution_id, seq FROM execution_events"
                    " ORDER BY execution_id, seq"
                ).fetchall()
                indexes = {r[1] for r in conn.execute(
                    "PRAGMA index_list(execution_events)"
                ).fetchall()}
            finally:
                conn.close()

            assert "uq_execution_events_seq" in indexes
            seqs = [s for _, s in rows]
            assert len(set(seqs)) == len(seqs), "升级后 seq 必须全局唯一"
            # 同一执行内的相对顺序保持不变
            for exec_id in ("exec-a", "exec-b"):
                in_order = [s for e, s in rows if e == exec_id]
                assert in_order == sorted(in_order)
        finally:
            database.MIGRATIONS_DIR = real_migrations
            for suffix in ("", "-wal", "-shm"):
                Path(raw_path + suffix).unlink(missing_ok=True)


class TestReplayLiveDedup:
    def test_event_published_during_replay_is_delivered_once(self, monkeypatch):
        """补发查询执行期间发布的事件：旧实现先订阅队列再查库补发，
        该事件既出现在补发结果又留在实时队列（重复送达）；水位线协议下
        补发窗口封顶于 watermark，只送达一次。"""
        task_id = _task()
        rows = _record_same_ms(task_id, 2, "2026-11-28T05:00:00.300Z")

        from app.api import events as events_module

        real_replay = events_module.execution_event_repo.list_by_task_after
        published_during: list[int] = []

        def replay_and_publish(*args, **kwargs):
            # 模拟"补发查询执行期间"发布：先持久化并入队，再跑真实查询
            publish_event(task_id, "fetch_done", "published-during-replay", {})
            published_during.append(execution_event_repo.max_seq())
            return real_replay(*args, **kwargs)

        monkeypatch.setattr(
            events_module.execution_event_repo,
            "list_by_task_after",
            replay_and_publish,
        )

        headers = {**_auth_headers(), "Last-Event-ID": str(rows[0]["seq"])}
        result: dict = {}
        driver = threading.Thread(
            target=_drive_stream,
            args=(f"/api/tasks/{task_id}/events", headers, result),
            daemon=True,
        )
        driver.start()
        _finish_with_terminal(task_id, driver, delay=1.5)

        assert result["status"] == 200
        assert published_during, "屏障事件必须已发布"
        ids = re.findall(r"^id: (\d+)$", result["text"], re.MULTILINE)
        assert len(ids) == len(set(ids)), f"事件被重复送达：{ids}"
        assert str(published_during[0]) in ids
