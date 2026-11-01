"""
test_migrations.py — 迁移版本游标回归测试。

历史缺陷：init_database 每次启动全量重放全部迁移，重建型迁移
（006/008/015）用显式列清单搬数据，等效于每次重启清空 items 去重键
与执行指标列。版本游标落地后，重启路径必须做到数据无损。
"""
import sqlite3
from pathlib import Path

import pytest

from app.core import config
from app.core.database import init_database, _migration_version


@pytest.fixture
def fresh_db_path(tmp_path, monkeypatch):
    """独立临时库（不复用 session 级测试库），db_path 指向它。"""
    path = str(tmp_path / "migrations.db")
    monkeypatch.setattr(config.settings, "db_path", path)
    return path


def _seed_and_read(path: str) -> tuple[dict, dict]:
    """写入随后必须跨重启存活的业务数据，返回重启前后的两份快照。"""
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT INTO items (id, task_id, title, url, url_hash, summary, is_read,"
            " is_starred, fetched_at, created_at, external_id, content_hash)"
            " VALUES ('i1','t1','T','http://x/','h1',NULL,0,0,"
            " '2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','ext-1','hash-1')"
        )
        conn.execute(
            "INSERT INTO task_executions (id, task_id, status, items_fetched, items_new,"
            " duration_ms, error_message, executed_at, pages_count, items_seen)"
            " VALUES ('e1','t1','success',5,2,100,NULL,"
            " '2026-01-01T00:00:00Z',3,5)"
        )
        conn.commit()
        before = {
            "item": conn.execute(
                "SELECT external_id, content_hash FROM items WHERE id='i1'"
            ).fetchone(),
            "exec": conn.execute(
                "SELECT pages_count, items_seen FROM task_executions WHERE id='e1'"
            ).fetchone(),
        }
    finally:
        conn.close()

    init_database()

    conn = sqlite3.connect(path)
    try:
        after = {
            "item": conn.execute(
                "SELECT external_id, content_hash FROM items WHERE id='i1'"
            ).fetchone(),
            "exec": conn.execute(
                "SELECT pages_count, items_seen FROM task_executions WHERE id='e1'"
            ).fetchone(),
        }
    finally:
        conn.close()
    return before, after


def test_fresh_db_reaches_max_migration_version(fresh_db_path):
    """全新库应用全部迁移后，user_version 等于最大迁移版本号。"""
    init_database()
    migrations_dir = Path(__file__).parent.parent / "migrations"
    max_version = max(
        v for f in migrations_dir.glob("*.sql")
        if (v := _migration_version(f)) is not None
    )
    conn = sqlite3.connect(fresh_db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == max_version
    finally:
        conn.close()


def test_restart_preserves_items_and_execution_data(fresh_db_path):
    """回归：第二次 init_database 不得清空 items 去重键与执行指标。"""
    init_database()
    before, after = _seed_and_read(fresh_db_path)
    assert before["item"] == ("ext-1", "hash-1")
    assert before["exec"] == (3, 5)
    assert after["item"] == before["item"], "items.external_id/content_hash 在重启后丢失"
    assert after["exec"] == before["exec"], "task_executions 指标在重启后丢失"


def test_only_new_migrations_run_on_existing_db(tmp_path, monkeypatch):
    """游标只放行新增迁移：002 已应用后再加 003，仅 003 执行。"""
    import app.core.database as database

    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text(
        "CREATE TABLE demo (id TEXT PRIMARY KEY, note TEXT);", encoding="utf-8"
    )
    (migrations_dir / "002_note.sql").write_text(
        "ALTER TABLE demo ADD COLUMN flag INTEGER NOT NULL DEFAULT 0;", encoding="utf-8"
    )
    monkeypatch.setattr(config.settings, "db_path", str(tmp_path / "cursor.db"))
    monkeypatch.setattr(database, "MIGRATIONS_DIR", migrations_dir)

    init_database()
    assert database._migration_version(migrations_dir / "002_note.sql") == 2

    (migrations_dir / "003_extra.sql").write_text(
        "ALTER TABLE demo ADD COLUMN extra TEXT;", encoding="utf-8"
    )
    conn = sqlite3.connect(tmp_path / "cursor.db")
    try:
        # 写入一行业务数据，验证 001/002 不会因重放而毁掉它
        conn.execute("INSERT INTO demo (id, note) VALUES ('d1', 'keep')")
        conn.commit()
    finally:
        conn.close()

    init_database()
    conn = sqlite3.connect(tmp_path / "cursor.db")
    try:
        assert conn.execute("SELECT extra FROM demo WHERE id='d1'").fetchone() == (None,)
        assert conn.execute("SELECT note FROM demo WHERE id='d1'").fetchone() == ("keep",)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    finally:
        conn.close()
