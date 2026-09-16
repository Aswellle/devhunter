"""
app/core/database.py
SQLite 连接管理 + WAL 模式 + 表初始化
"""
import logging
import re
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


def _strip_line_comment(line: str) -> str:
    """
    去除行尾的单行注释（-- ...），保留字符串字面量内的 --。
    """
    # 简单处理：找到不在字符串内的第一个 --
    in_string = False
    i = 0
    while i < len(line) - 1:
        ch = line[i]
        if ch == "'" and not in_string:
            in_string = True
        elif ch == "'" and in_string:
            # Check for escaped quote ''
            if i + 1 < len(line) and line[i + 1] == "'":
                i += 1
            else:
                in_string = False
        elif ch == "-" and line[i + 1] == "-" and not in_string:
            return line[:i].rstrip()
        i += 1
    return line


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

        # 去除行尾注释以便检测语句结束
        code_part = _strip_line_comment(line).strip()
        if not code_part:
            continue

        current.append(line)
        upper = code_part.upper()

        # 计算 BEGIN/END 嵌套层级
        if "BEGIN" in upper:
            depth += upper.count("BEGIN")
        if upper == "END;" or upper == "END":
            depth -= 1

        if code_part.endswith(";") and depth <= 0:
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

def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """检查表是否已有指定列（用于跳过重复的 ALTER TABLE ADD COLUMN）"""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


_ADD_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)", re.IGNORECASE
)


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
                # D10: ALTER TABLE ADD COLUMN idempotency checked properly
                # via PRAGMA table_info instead of relying on the generic
                # OperationalError string-match fallback below — that
                # fallback matches on the substring "duplicate" in the
                # lowercased error message, which is exactly SQLite's
                # current wording ("duplicate column name: X") but is not
                # a stable contract; a future SQLite version could reword
                # it and this pre-check keeps ADD COLUMN safe regardless.
                add_col_match = _ADD_COLUMN_RE.match(stmt.strip())
                if add_col_match:
                    table, column = add_col_match.group(1), add_col_match.group(2)
                    if _column_exists(conn, table, column):
                        logger.debug("Column %s.%s already exists, skip", table, column)
                        continue
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
