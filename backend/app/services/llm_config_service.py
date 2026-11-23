"""
app/services/llm_config_service.py
LLM 接入配置服务：界面保存值（app_settings）的写入/清除、状态组装与用量查询。

保存语义（三态）：
- 字段缺失或为 null → 不改动
- 字段为空串 → 清除该字段的界面覆盖，回落环境变量
- 字段有值   → 写入覆盖（保存前去除首尾空白与末尾斜杠）
- daily_token_budget 为整数 → 直接覆盖（数值字段无"清空"态，回落默认用清除配置）
"""
import base64

from app.core.config import settings
from app.llm.config import LLM_SETTING_KEYS, mask_secret, resolve_llm_config, utc_day_start_iso
from app.llm.provider import llm_provider
from app.llm.receipt_repo import model_receipt_repo
from app.repositories.settings_repo import app_settings_repo
from app.schemas.llm import LLMConfigUpdate

# schema 字段名 → app_settings 键名
_FIELD_TO_KEY = {
    "api_key": "llm_api_key",
    "base_url": "llm_base_url",
    "model": "llm_model",
}


def _encode_cursor(anchor: tuple[str, str] | None) -> str | None:
    """(created_at, id) → 不透明游标（base64url）"""
    if anchor is None:
        return None
    raw = f"{anchor[0]}|{anchor[1]}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> tuple[str, str] | None:
    """不透明游标 → (created_at, id)；非法游标按"从头开始"处理"""
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        created_at, _, receipt_id = raw.partition("|")
        if not created_at or not receipt_id:
            return None
        return created_at, receipt_id
    except Exception:  # noqa: BLE001 —— 游标损坏不应 500，退化为第一页
        return None


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
            "api_protocol": cfg.api_protocol,
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
        if payload.api_protocol is not None:
            app_settings_repo.set("llm_api_protocol", payload.api_protocol)
        if payload.daily_token_budget is not None:
            app_settings_repo.set("llm_daily_token_budget", str(payload.daily_token_budget))
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
            api_protocol=payload.api_protocol or cfg.api_protocol,
        )

    def list_models(self, payload: LLMConfigUpdate) -> dict:
        """用表单参数（空白处沿用生效值）拉取服务商可用模型列表"""
        cfg = resolve_llm_config()
        return llm_provider.list_models(
            api_key=(payload.api_key or "").strip() or cfg.api_key,
            base_url=(payload.base_url or "").strip() or cfg.base_url,
            api_protocol=payload.api_protocol or cfg.api_protocol,
        )

    def usage(self, limit: int = 10, offset: int = 0, cursor: str | None = None) -> dict:
        """
        当日调用汇总 + 回执分页（含失败原因）。

        分页优先走游标（keyset）：翻页期间新增调用不会让后续页错位。
        未提供游标时退回 offset（兼容旧调用方），并按本页最后一条
        生成下一页游标，之后即可无缝切换为游标翻页。
        """
        if cursor:
            receipts, anchor = model_receipt_repo.stats_page(
                limit=limit, before=_decode_cursor(cursor),
            )
        else:
            receipts = model_receipt_repo.stats(limit=limit, offset=offset)
            anchor = (receipts[-1]["created_at"], receipts[-1]["id"]) if len(receipts) == limit else None
        return {
            "today": model_receipt_repo.usage_summary(utc_day_start_iso()),
            "receipts": receipts,
            "total": model_receipt_repo.count_all(),
            "next_cursor": _encode_cursor(anchor),
        }


# 全局单例
llm_config_service = LLMConfigService()
