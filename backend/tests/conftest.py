"""
tests/conftest.py
测试 fixtures：设置测试数据库
"""
import os
import sys
import tempfile
import sqlite3
from pathlib import Path

import pytest

# 确保 backend 在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))


def _run_migrations(db_path: str):
    """运行所有 migration 文件"""
    migrations_dir = Path(__file__).parent.parent / "migrations"
    conn = sqlite3.connect(db_path)
    try:
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            sql = sql_file.read_text(encoding="utf-8")
            try:
                conn.executescript(sql)
            except sqlite3.OperationalError as e:
                # 忽略 "duplicate column name" 等错误
                if "duplicate column name" not in str(e):
                    raise
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(scope="session")
def test_db_path():
    """创建临时测试数据库"""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="devhunter_test_")
    os.close(fd)
    _run_migrations(path)
    yield path
    os.unlink(path)


@pytest.fixture(autouse=True)
def setup_test_db(test_db_path, monkeypatch):
    """每个测试前设置数据库路径"""
    from app.core import config
    monkeypatch.setattr(config.settings, "db_path", test_db_path)
    yield
