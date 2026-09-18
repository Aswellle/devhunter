"""
app/core/config.py
配置管理 - 基于 pydantic-settings，从 .env 文件读取
"""
import logging
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal


from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)

# .env 文件相对于 config.py 的绝对路径，确保任何 CWD 下都能正确加载
# 修复：原来使用相对路径 ".env"，当从非 backend/ 目录启动时（如 Docker、IDE）
# 会找不到 .env，导致全部使用默认值——用户改了 .env 密码却登录失败
_ENV_FILE = str(Path(__file__).parent.parent.parent / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 应用 ────────────────────────────────────
    app_env: Literal["development", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False

    # ── 数据库 ──────────────────────────────────
    db_path: str = "data/devhunter.db"

    # ── 认证 ────────────────────────────────────
    auth_username: str = "admin"
    auth_password: str = "devhunter123"
    secret_key: str = "change-me-in-production"
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days

    # ── 抓取 ────────────────────────────────────
    crawler_timeout: float = 15.0
    crawler_max_response_mb: int = 5
    crawler_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    # ── 调度器 ──────────────────────────────────
    scheduler_max_workers: int = 3
    scheduler_misfire_grace_time: int = 300

    # ── 日志 ────────────────────────────────────
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # ── CORS ────────────────────────────────────
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:5200"

    @field_validator("secret_key")
    @classmethod
    def validate_or_generate_secret_key(cls, v: str) -> str:
        """如果 secret_key 是已知默认值，自动生成一个强随机密钥"""
        _insecure_secrets = {
            "change-me-in-production",
            "change-me",
            "",
            "<请用 openssl rand -hex 32 生成>",
            "change-me-please-use-openssl-rand-hex-32",
        }
        if v in _insecure_secrets:
            # 生成 64 字符十六进制随机密钥（256 位熵）
            return secrets.token_hex(32)
        return v

    @field_validator("db_path")
    @classmethod
    def ensure_data_dir(cls, v: str) -> str:
        """确保数据目录存在"""
        Path(v).parent.mkdir(parents=True, exist_ok=True)
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate_production_secrets(self) -> None:
        """生产环境启动时校验敏感配置，防止使用默认值/占位符部署"""
        if not self.is_production:
            return
        insecure_passwords = {"devhunter123", "change-me", "", "<请修改为强密码>"}
        insecure_keys = {
            "change-me-in-production", "change-me", "",
            "<请用 openssl rand -hex 32 生成>",
            # docker-compose.yml 的 SECRET_KEY fallback 默认值（未设置环境变量时）
            "change-me-please-use-openssl-rand-hex-32",
        }
        if self.auth_password in insecure_passwords:
            raise RuntimeError("AUTH_PASSWORD must be changed from default in production")
        if self.secret_key in insecure_keys:
            raise RuntimeError("SECRET_KEY must be changed from default in production")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全局单例 Settings（通过 lru_cache 缓存）"""
    return Settings()


# 便捷别名
settings = get_settings()
