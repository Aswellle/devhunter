"""
app/core/database.py
SQLite 连接管理 + WAL 模式 + 表初始化
"""
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from app.core.config import settings

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, timeout=5.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _split_sql_statements(sql: str) -> list[str]:
    """
    拆分 SQL 文件为独立语句，正确处理 TRIGGER 中 BEGIN...END 块。
    """
    statements = []
    current: list[str] = []
    depth = 0

    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue

        current.append(line)
        upper = stripped.upper()

        # 计算 BEGIN/END 嵌套层级
        if "BEGIN" in upper:
            depth += upper.count("BEGIN")
        if upper == "END;" or upper == "END":
            depth -= 1

        if stripped.endswith(";") and depth <= 0:
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            depth = 0

    if current:
        stmt = "\n".join(current).strip()
        if stmt:
            statements.append(stmt)

    return statements


def init_database() -> None:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        logger.warning("No migration files found in %s", MIGRATIONS_DIR)
        return

    conn = sqlite3.connect(settings.db_path, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        for sql_file in sql_files:
            logger.info("Running migration: %s", sql_file.name)
            sql = sql_file.read_text(encoding="utf-8")
            for stmt in _split_sql_statements(sql):
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError as e:
                    err_msg = str(e).lower()
                    if "already exists" in err_msg or "duplicate" in err_msg:
                        logger.debug("Already exists, skip: %.80s", stmt[:80])
                    else:
                        logger.error("Migration error (%s): %s\n%.200s",
                                     sql_file.name, e, stmt)
                        raise
    finally:
        conn.close()

    logger.info("Database initialized at: %s", settings.db_path)


def close_database() -> None:
    logger.info("Database shutdown")
