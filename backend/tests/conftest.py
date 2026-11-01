"""
tests/conftest.py
测试 fixtures：设置测试数据库
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# 确保 backend 在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def test_db_path():
    """创建临时测试数据库。

    迁移必须经生产入口 init_database() 应用：测试里手写 executescript
    走的是另一套执行器（无逐语句拆分、无 ADD COLUMN 幂等预检、无
    user_version 游标），对"第二次启动重放"这类缺陷天然免疫，生产上
    才暴露。"""
    from app.core import config
    from app.core.database import init_database

    fd, path = tempfile.mkstemp(suffix=".db", prefix="devhunter_test_")
    os.close(fd)
    config.settings.db_path = path
    init_database()
    yield path
    os.unlink(path)


@pytest.fixture(autouse=True)
def setup_test_db(test_db_path, monkeypatch):
    """每个测试前设置数据库路径"""
    from app.core import config
    monkeypatch.setattr(config.settings, "db_path", test_db_path)
    yield
