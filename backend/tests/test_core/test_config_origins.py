"""
tests/test_core/test_config_origins.py
CORS_ORIGINS 配置解析与生产环境 Origin 防护测试。
"""
import pytest

from app.core.config import Settings


def _settings(**kwargs) -> Settings:
    """显式传参构造 Settings，避免读取本地 .env 影响断言。"""
    base = dict(
        app_env="development",
        auth_password="test-password",
        secret_key="test-secret-key",
        db_path="data/test_config_origins.db",
    )
    base.update(kwargs)
    return Settings(**base)


class TestCorsOriginsList:
    def test_single_origin(self):
        assert _settings(cors_origins="https://app.example.test").cors_origins_list == [
            "https://app.example.test"
        ]

    def test_multiple_origins_with_whitespace_and_empty_entries(self):
        s = _settings(cors_origins=" http://a.test , , https://b.test ,")
        assert s.cors_origins_list == ["http://a.test", "https://b.test"]

    def test_trailing_slash_is_normalized(self):
        """用户常在环境变量里写带尾斜杠的 Origin，而浏览器发送的 Origin
        永远没有尾斜杠——不归一化会导致自定义域名登录被 403。"""
        s = _settings(cors_origins="https://app.example.test/")
        assert s.cors_origins_list == ["https://app.example.test"]

    def test_empty_string_yields_empty_list(self):
        assert _settings(cors_origins="").cors_origins_list == []


class TestProductionOriginGuard:
    def test_wildcard_origin_rejected_in_production(self):
        s = _settings(app_env="production", cors_origins="*")
        with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
            s.validate_production_secrets()

    def test_explicit_origins_accepted_in_production(self):
        s = _settings(
            app_env="production",
            cors_origins="https://app.example.test,https://dev.example.test",
        )
        s.validate_production_secrets()
