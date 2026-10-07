"""
tests/test_api/test_llm_api.py
LLM 接入配置 API 测试：认证、三态保存语义、密钥脱敏、连通性测试端点。
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.core.security import create_access_token
from app.llm import provider as provider_module
from app.llm.config import LLM_SETTING_KEYS
from app.llm.provider import llm_provider
from app.llm.receipt_repo import model_receipt_repo
from app.main import app
from app.repositories.settings_repo import app_settings_repo

client = TestClient(app)


def _auth_headers():
    token = create_access_token({"sub": "admin"})
    return {"Authorization": f"Bearer {token}"}


def _ok_response(text: str = "OK") -> httpx.Response:
    return httpx.Response(200, json={
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
    })


@pytest.fixture(autouse=True)
def _clean_llm_settings():
    """隔离共享测试库与 provider 测试传输"""
    for key in LLM_SETTING_KEYS:
        app_settings_repo.delete(key)
    llm_provider.set_test_transport(None)
    yield
    for key in LLM_SETTING_KEYS:
        app_settings_repo.delete(key)
    llm_provider.set_test_transport(None)


class TestAuth:

    def test_all_endpoints_require_auth(self):
        assert client.get("/api/llm/config").status_code == 401
        assert client.put("/api/llm/config", json={}).status_code == 401
        assert client.delete("/api/llm/config").status_code == 401
        assert client.post("/api/llm/test", json={}).status_code == 401


class TestConfigStatusAndSave:

    def test_initially_unconfigured(self, monkeypatch):
        monkeypatch.setattr(config.settings, "llm_api_key", "")
        data = client.get("/api/llm/config", headers=_auth_headers()).json()
        assert data["configured"] is False
        assert data["source"] == "none"
        assert data["api_key_masked"] is None
        assert data["overrides"] == []

    def test_env_key_detected_as_source(self, monkeypatch):
        monkeypatch.setattr(config.settings, "llm_api_key", "env-secret-key")
        data = client.get("/api/llm/config", headers=_auth_headers()).json()
        assert data["configured"] is True
        assert data["source"] == "env"
        assert data["env_key_present"] is True
        assert data["api_key_masked"] is not None

    def test_save_then_masked_roundtrip(self):
        response = client.put("/api/llm/config", headers=_auth_headers(), json={
            "api_key": "sk-secret-key-abcdef123456",
            "base_url": "https://api.example.com/v1/",
            "model": "test-model",
        })
        assert response.status_code == 200
        data = response.json()

        assert data["configured"] is True
        assert data["source"] == "db"
        assert set(data["overrides"]) == {"llm_api_key", "llm_base_url", "llm_model"}
        assert data["base_url"] == "https://api.example.com/v1", "末尾斜杠应被归一"
        assert data["model"] == "test-model"

        # 密钥脱敏：完整密钥绝不出现在任何响应里
        assert "sk-secret-key-abcdef123456" not in response.text
        masked = data["api_key_masked"]
        assert masked.startswith("sk-s") and masked.endswith("3456")
        assert "••••" in masked

        follow_up = client.get("/api/llm/config", headers=_auth_headers()).json()
        assert "sk-secret-key-abcdef123456" not in str(follow_up)

    def test_partial_update_keeps_other_fields(self):
        client.put("/api/llm/config", headers=_auth_headers(), json={"api_key": "k-0000-9999"})
        data = client.put(
            "/api/llm/config", headers=_auth_headers(), json={"model": "m2"},
        ).json()
        assert set(data["overrides"]) == {"llm_api_key", "llm_model"}
        assert data["model"] == "m2"

    def test_empty_string_clears_single_override(self, monkeypatch):
        """空字符串 = 清除该字段覆盖，回落环境变量；未提交字段不动"""
        monkeypatch.setattr(config.settings, "llm_api_key", "")
        client.put("/api/llm/config", headers=_auth_headers(), json={
            "api_key": "k-0000-9999", "model": "m1",
        })
        data = client.put(
            "/api/llm/config", headers=_auth_headers(), json={"api_key": ""},
        ).json()
        assert data["overrides"] == ["llm_model"]
        assert data["configured"] is False, "Key 覆盖清除后应回落到未配置的环境变量"

    def test_clear_all_reverts_to_env(self, monkeypatch):
        monkeypatch.setattr(config.settings, "llm_api_key", "env-key")
        client.put("/api/llm/config", headers=_auth_headers(), json={
            "api_key": "db-key", "base_url": "https://x.example/v1", "model": "m",
        })
        data = client.delete("/api/llm/config", headers=_auth_headers()).json()
        assert data["overrides"] == []
        assert data["source"] == "env"
        assert data["api_key_masked"] is not None

    def test_base_url_scheme_validated(self):
        response = client.put(
            "/api/llm/config", headers=_auth_headers(), json={"base_url": "ftp://x.example"},
        )
        assert response.status_code == 422

    def test_save_budget_override(self, monkeypatch):
        """预算整数覆盖：写入后 usage.budget 立即反映新预算"""
        monkeypatch.setattr(config.settings, "llm_daily_token_budget", 200_000)
        used_before = model_receipt_repo.tokens_since(provider_module.utc_day_start_iso())
        data = client.put(
            "/api/llm/config", headers=_auth_headers(), json={"daily_token_budget": 5000},
        ).json()
        assert "llm_daily_token_budget" in data["overrides"]
        assert data["usage"]["budget"] == 5000
        assert data["usage"]["remaining"] == 5000 - used_before, "剩余预算扣除共享测试库当日消耗"

    def test_budget_below_minimum_rejected(self):
        assert client.put(
            "/api/llm/config", headers=_auth_headers(), json={"daily_token_budget": 5},
        ).status_code == 422

    def test_usage_block_present(self):
        data = client.get("/api/llm/config", headers=_auth_headers()).json()
        usage = data["usage"]
        for field in ("used_today", "budget", "remaining", "breaker_open",
                      "consecutive_failures", "max_consecutive_failures"):
            assert field in usage


class TestConnectionEndpoint:

    def _set_transport(self, response: httpx.Response):
        llm_provider.set_test_transport(httpx.MockTransport(lambda request: response))

    def test_success_with_form_values(self):
        self._set_transport(_ok_response("OK"))
        response = client.post("/api/llm/test", headers=_auth_headers(), json={
            "api_key": "k", "base_url": "https://x.example/v1", "model": "m",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "连接成功" in data["message"]
        assert data["model"] == "m"

    def test_blank_fields_fall_back_to_effective_config(self):
        """表单空白处沿用当前生效值——支持先测已存配置"""
        client.put("/api/llm/config", headers=_auth_headers(), json={
            "api_key": "saved-key", "base_url": "https://saved.example/v1", "model": "saved-model",
        })
        transport_calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            transport_calls.append(request)
            return _ok_response("OK")

        llm_provider.set_test_transport(httpx.MockTransport(handler))
        data = client.post("/api/llm/test", headers=_auth_headers(), json={
            "api_key": None, "base_url": "", "model": None,
        }).json()

        assert data["ok"] is True
        assert str(transport_calls[0].url) == "https://saved.example/v1/chat/completions"
        assert transport_calls[0].headers["Authorization"] == "Bearer saved-key"

    def test_failure_returns_friendly_message(self):
        self._set_transport(httpx.Response(401, text="unauthorized"))
        data = client.post("/api/llm/test", headers=_auth_headers(), json={
            "api_key": "bad", "base_url": "https://x.example/v1", "model": "m",
        }).json()
        assert data["ok"] is False
        assert "密钥" in data["message"]


class TestReceiptsEndpoint:

    def test_requires_auth(self):
        assert client.get("/api/llm/receipts").status_code == 401

    def test_summary_and_recent_receipts(self):
        """当日汇总包含调用次数与 token 消耗；回执列表按时间倒序"""
        rid = model_receipt_repo.create_pending("thread_digest", "test-model", "h-r1")
        model_receipt_repo.complete(rid, "正文", 120, 30, 800)
        rid2 = model_receipt_repo.create_pending("thread_digest", "test-model", "h-r2")
        model_receipt_repo.fail(rid2, "boom")

        data = client.get("/api/llm/receipts", headers=_auth_headers()).json()

        assert data["today"]["calls"] >= 2
        assert data["today"]["done"] >= 1
        assert data["today"]["failed"] >= 1
        assert data["today"]["tokens"] >= 150

        receipts = data["receipts"]
        assert receipts[0]["created_at"] >= receipts[-1]["created_at"]
        done = next(r for r in receipts if r["status"] == "done" and r["purpose"] == "thread_digest")
        assert done["input_tokens"] == 120 and done["output_tokens"] == 30
        failed = next(r for r in receipts if r["status"] == "failed")
        assert failed["error"] == "boom"

    def test_limit_clamped(self):
        response = client.get("/api/llm/receipts?limit=0", headers=_auth_headers())
        assert response.status_code == 422
