"""
tests/test_llm/test_config.py
LLM 有效配置解析与界面覆盖（app_settings）语义测试。
"""
import pytest

from app.core import config
from app.llm.config import LLM_SETTING_KEYS, mask_secret, resolve_llm_config
from app.repositories.settings_repo import app_settings_repo


@pytest.fixture(autouse=True)
def _clean_llm_overrides():
    """隔离共享测试库：前后清理界面覆盖行"""
    for key in LLM_SETTING_KEYS:
        app_settings_repo.delete(key)
    yield
    for key in LLM_SETTING_KEYS:
        app_settings_repo.delete(key)


class TestResolve:

    def test_env_fallback_when_no_overrides(self, monkeypatch):
        """无界面覆盖时回落环境变量"""
        monkeypatch.setattr(config.settings, "llm_api_key", "env-key")
        monkeypatch.setattr(config.settings, "llm_base_url", "https://env.example/v1")
        monkeypatch.setattr(config.settings, "llm_model", "env-model")

        cfg = resolve_llm_config()
        assert cfg.api_key == "env-key"
        assert cfg.base_url == "https://env.example/v1"
        assert cfg.model == "env-model"
        assert cfg.source == "env"

    def test_none_when_unconfigured(self, monkeypatch):
        monkeypatch.setattr(config.settings, "llm_api_key", "")
        cfg = resolve_llm_config()
        assert cfg.api_key == ""
        assert cfg.source == "none"

    def test_db_overrides_env(self, monkeypatch):
        """界面覆盖值优先于环境变量"""
        monkeypatch.setattr(config.settings, "llm_api_key", "env-key")
        monkeypatch.setattr(config.settings, "llm_model", "env-model")
        app_settings_repo.set("llm_api_key", "db-key")
        app_settings_repo.set("llm_model", "db-model")

        cfg = resolve_llm_config()
        assert cfg.api_key == "db-key"
        assert cfg.model == "db-model"
        assert cfg.source == "db"


class TestMaskSecret:

    def test_long_key_keeps_head_and_tail(self):
        assert mask_secret("sk-1234567890abcdef") == "sk-1••••cdef"

    def test_short_key_fully_masked(self):
        assert mask_secret("abcd1234") == "••••"

    def test_empty(self):
        assert mask_secret(None) is None
        assert mask_secret("") is None
