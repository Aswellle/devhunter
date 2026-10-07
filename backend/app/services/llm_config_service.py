"""
app/services/llm_config_service.py
LLM 接入配置服务：界面保存值（app_settings）的写入/清除与状态组装。

保存语义（三态）：
- 字段缺失或为 null → 不改动
- 字段为空串 → 清除该字段的界面覆盖，回落环境变量
- 字段有值   → 写入覆盖（保存前去除首尾空白与末尾斜杠）
"""
from app.core.config import settings
from app.llm.config import LLM_SETTING_KEYS, mask_secret, resolve_llm_config
from app.llm.provider import llm_provider
from app.repositories.settings_repo import app_settings_repo
from app.schemas.llm import LLMConfigUpdate

# schema 字段名 → app_settings 键名
_FIELD_TO_KEY = {
    "api_key": "llm_api_key",
    "base_url": "llm_base_url",
    "model": "llm_model",
}


class LLMConfigService:

    def get_status(self) -> dict:
        """当前生效配置 + 用量/熔断状态（密钥脱敏）"""
        cfg = resolve_llm_config()
        overrides = [k for k in LLM_SETTING_KEYS if app_settings_repo.get(k) is not None]
        return {
            "configured": bool(cfg.api_key),
            "source": cfg.source,
            "overrides": overrides,
            "base_url": cfg.base_url,
            "model": cfg.model,
            "api_key_masked": mask_secret(cfg.api_key),
            "env_key_present": bool(settings.llm_api_key),
            "usage": llm_provider.status(),
        }

    def save(self, payload: LLMConfigUpdate) -> dict:
        """按三态语义应用界面提交的字段，返回保存后的状态"""
        for field, settings_key in _FIELD_TO_KEY.items():
            raw = getattr(payload, field)
            if raw is None:
                continue  # 未提交 / 显式 null → 不改动
            value = raw.strip()
            if not value:
                app_settings_repo.delete(settings_key)
                continue
            if settings_key == "llm_base_url":
                value = value.rstrip("/")
            app_settings_repo.set(settings_key, value)
        return self.get_status()

    def clear(self) -> dict:
        """清除全部界面覆盖，回落环境变量"""
        for key in LLM_SETTING_KEYS:
            app_settings_repo.delete(key)
        return self.get_status()

    def test(self, payload: LLMConfigUpdate) -> dict:
        """连通性测试：表单有值用表单值，空白处沿用当前生效值（可先测后存）"""
        cfg = resolve_llm_config()
        return llm_provider.test_connection(
            api_key=(payload.api_key or "").strip() or cfg.api_key,
            base_url=(payload.base_url or "").strip() or cfg.base_url,
            model=(payload.model or "").strip() or cfg.model,
        )


# 全局单例
llm_config_service = LLMConfigService()
