"""
app/schemas/llm.py
LLM 接入配置的 Pydantic 模型
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMUsageStatus(BaseModel):
    """当日用量与熔断状态"""
    used_today: int
    budget: int
    remaining: int
    breaker_open: bool
    consecutive_failures: int
    max_consecutive_failures: int


class LLMConfigStatus(BaseModel):
    """
    当前生效配置（GET/PUT/DELETE 响应）。

    API Key 只回脱敏掩码，任何响应都不携带完整密钥。
    """
    configured: bool
    # api_key 来源：db（界面配置）/ env（环境变量）/ none（未配置）
    source: Literal["db", "env", "none"]
    # 界面已覆盖的字段名（llm_api_key / llm_base_url / llm_model）
    overrides: list[str] = []
    base_url: str
    model: str
    api_key_masked: str | None = None
    # 环境变量中是否存在密钥（提示用户界面配置会覆盖它）
    env_key_present: bool = False
    usage: LLMUsageStatus


class LLMConfigUpdate(BaseModel):
    """
    保存/测试 LLM 接入配置。

    - 字段缺失或为 null：保存时表示"不改动该字段"；测试时表示"沿用当前生效值"
    - 字段为空字符串：保存时表示"清除该字段的界面覆盖"，回落环境变量
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    api_key: str | None = Field(None, max_length=400)
    base_url: str | None = Field(None, max_length=300)
    model: str | None = Field(None, max_length=120)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str | None) -> str | None:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("接口地址必须以 http:// 或 https:// 开头")
        return v


class LLMTestResult(BaseModel):
    """连通性测试结果"""
    ok: bool
    message: str
    model: str | None = None
    latency_ms: int | None = None
