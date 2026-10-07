"""
app/llm/config.py
LLM 有效配置解析：界面保存值（app_settings 表）优先，回落 .env 环境变量。

设计约束：
- 每次调用实时解析（SQLite 单行读，开销可忽略），用户在界面保存/清除后
  立即生效，无需重启进程。
- API Key 只写不读：对外一律返回 mask_secret() 脱敏掩码。
"""
from dataclasses import dataclass
import time

from app.core.config import settings
from app.repositories.settings_repo import app_settings_repo

# 界面可覆盖的 LLM 配置字段（app_settings 表中的键名）
LLM_SETTING_KEYS = (
    "llm_api_key",
    "llm_base_url",
    "llm_model",
    "llm_daily_token_budget",
)


def utc_day_start_iso() -> str:
    """当前 UTC 日的零点（ISO），作为每日预算统计窗口起点"""
    return time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime())


@dataclass(frozen=True)
class EffectiveLLMConfig:
    api_key: str
    base_url: str
    model: str
    daily_budget: int
    # api_key 的来源：db（界面配置）/ env（环境变量）/ none（未配置）
    source: str


def _int_or(value: str | None, fallback: int) -> int:
    """设置值 → int；为空/非法时回落默认值"""
    try:
        return int(value) if value not in (None, "") else fallback
    except (TypeError, ValueError):
        return fallback


def resolve_llm_config() -> EffectiveLLMConfig:
    """解析当前生效的 LLM 配置：界面覆盖值 > 环境变量默认值"""
    overrides = {k: app_settings_repo.get(k) for k in LLM_SETTING_KEYS}

    if overrides["llm_api_key"]:
        source = "db"
    elif settings.llm_api_key:
        source = "env"
    else:
        source = "none"

    return EffectiveLLMConfig(
        api_key=overrides["llm_api_key"] or settings.llm_api_key or "",
        base_url=overrides["llm_base_url"] or settings.llm_base_url,
        model=overrides["llm_model"] or settings.llm_model,
        daily_budget=_int_or(overrides["llm_daily_token_budget"], settings.llm_daily_token_budget),
        source=source,
    )


def mask_secret(value: str | None) -> str | None:
    """密钥脱敏：保留首尾各 4 位，中间打码；短密钥全打码"""
    if not value:
        return None
    if len(value) <= 8:
        return "••••"
    return f"{value[:4]}••••{value[-4:]}"
