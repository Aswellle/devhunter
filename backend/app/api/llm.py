"""
app/api/llm.py
LLM 接入配置 API：用户在界面完成 API Key 配置，无需改动 .env 或重启。

- GET    /api/llm/config  当前生效配置（密钥脱敏）与用量/熔断状态
- PUT    /api/llm/config  保存界面配置（覆盖环境变量；空字符串清除该字段覆盖）
- DELETE /api/llm/config  清除全部界面配置，回落环境变量
- POST   /api/llm/test    连通性测试（支持先测未保存的表单值）

安全：API Key 只写不读——任何响应只返回脱敏掩码；端点全部要求用户认证。
"""
from fastapi import APIRouter, Depends

from app.api.deps import require_auth
from app.schemas.llm import LLMConfigStatus, LLMConfigUpdate, LLMTestResult
from app.services.llm_config_service import llm_config_service

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/config", response_model=LLMConfigStatus)
def get_config(_: str = Depends(require_auth)):
    """当前生效的 LLM 配置（密钥脱敏）与当日用量/熔断状态"""
    return llm_config_service.get_status()


@router.put("/config", response_model=LLMConfigStatus)
def save_config(body: LLMConfigUpdate, _: str = Depends(require_auth)):
    """保存界面配置：立即生效（下次调用即用新配置，无需重启）"""
    return llm_config_service.save(body)


@router.delete("/config", response_model=LLMConfigStatus)
def clear_config(_: str = Depends(require_auth)):
    """清除全部界面配置，回落环境变量（若有）"""
    return llm_config_service.clear()


@router.post("/test", response_model=LLMTestResult)
def test_config(body: LLMConfigUpdate, _: str = Depends(require_auth)):
    """连通性测试：空字段沿用当前生效值，支持先测试再保存"""
    return llm_config_service.test(body)
