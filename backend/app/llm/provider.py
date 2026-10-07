"""
app/llm/provider.py
LLM 调用基础设施：OpenAI 兼容 / Anthropic 两种 API 协议 + 付费回执纪律。

付费纪律（四条，全部在 chat() 内强制执行）：
1. 回执先行 —— 调用前落 pending 回执，成功补全结果；崩溃/重启不丢"已付费"账
2. 结果复用 —— 相同 (model, system, prompt) 的已完成调用直接复用正文，不重复付费
3. 预算熔断 —— 当日（UTC）token 累计超过 llm_daily_token_budget 即熔断，次日自动恢复
4. 失败熔断 —— 连续失败达 llm_max_consecutive_failures 后停止调用（进程生命周期内），
   防止服务端故障时重试烧钱

配置来源：每次调用实时解析有效配置（llm.config.resolve_llm_config，界面保存值
优先于环境变量），用户在界面改 Key/换服务商/换协议后立即生效，无需重启。

未配置 api_key 时全链路静默关闭：chat() 返回 None，调用方优雅降级，
页面不出现任何 LLM 相关 UI。

线程安全：APScheduler worker 与 API 请求线程都可能调用；熔断计数用锁保护。
"""
import hashlib
import logging
import threading
import time

import httpx

from app.core.config import settings
from app.llm.config import resolve_llm_config, utc_day_start_iso
from app.llm.receipt_repo import model_receipt_repo

logger = logging.getLogger(__name__)

_ANTHROPIC_VERSION = "2023-06-01"


def _prompt_hash(model: str, system: str, prompt: str) -> str:
    return hashlib.sha256(f"{model}\x00{system}\x00{prompt}".encode("utf-8")).hexdigest()


def _friendly_http_error(status_code: int, body_text: str) -> str:
    """HTTP 状态码 → 用户可读的中文提示（配置页诊断用）"""
    if status_code in (401, 403):
        return "密钥无效或无权限，请检查 API Key"
    if status_code == 404:
        return "接口路径不存在，请确认接口地址与协议是否匹配"
    if status_code == 429:
        return "触发服务端限流或额度不足"
    if status_code >= 500:
        return f"服务端错误（HTTP {status_code}），请稍后重试"
    return f"请求被拒绝（HTTP {status_code}）：{body_text[:120]}"


class LLMProvider:
    """LLM 客户端（OpenAI 兼容 / Anthropic 协议，带付费纪律）"""

    def __init__(self) -> None:
        self._client: httpx.Client | None = None
        self._client_lock = threading.Lock()
        self._consecutive_failures = 0
        self._failure_lock = threading.Lock()
        # 测试注入口：设置后用 MockTransport 构建内部客户端（测试专用）
        self._test_transport: httpx.BaseTransport | None = None
        # "未配置"只告警一次，避免每条 Thread 刷一遍日志
        self._not_configured_logged = False

    # ── 状态查询 ─────────────────────────────────────

    def is_configured(self) -> bool:
        return bool(resolve_llm_config().api_key)

    def is_available(self) -> bool:
        """配置齐全且未触发任何熔断"""
        if not self.is_configured():
            return False
        with self._failure_lock:
            if self._consecutive_failures >= settings.llm_max_consecutive_failures:
                return False
        return self.remaining_budget() > 0

    def remaining_budget(self) -> int:
        """今日剩余 token 预算（有效配置的每日预算）"""
        used = model_receipt_repo.tokens_since(utc_day_start_iso())
        return max(0, resolve_llm_config().daily_budget - used)

    def status(self) -> dict:
        """用量与熔断状态（配置页展示用）"""
        budget = resolve_llm_config().daily_budget
        used = model_receipt_repo.tokens_since(utc_day_start_iso())
        with self._failure_lock:
            failures = self._consecutive_failures
        return {
            "used_today": used,
            "budget": budget,
            "remaining": max(0, budget - used),
            "breaker_open": failures >= settings.llm_max_consecutive_failures,
            "consecutive_failures": failures,
            "max_consecutive_failures": settings.llm_max_consecutive_failures,
        }

    # ── 测试注入口 ───────────────────────────────────

    def set_test_transport(self, transport: httpx.BaseTransport | None) -> None:
        """注入 httpx MockTransport（仅测试使用）；传 None 恢复真实客户端"""
        with self._client_lock:
            self._test_transport = transport
            self._client = None  # 强制重建

    # ── 内部 ─────────────────────────────────────────

    def _get_client(self) -> httpx.Client:
        """客户端与配置解耦：不带 base_url 与鉴权头——Key/服务商在界面
        更换后无需重建连接或重启进程，鉴权按请求携带，URL 按请求拼接。"""
        if self._client is None or self._client.is_closed:
            with self._client_lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.Client(
                        headers={"Content-Type": "application/json"},
                        timeout=httpx.Timeout(
                            connect=10.0,
                            read=settings.llm_timeout,
                            write=10.0,
                            pool=5.0,
                        ),
                        limits=httpx.Limits(max_keepalive_connections=2, max_connections=4),
                        # 测试注入口：MockTransport 替换真实 HTTP 层
                        transport=self._test_transport,
                    )
        return self._client

    def _openai_chat(
        self, api_key: str, base_url: str, model: str,
        system: str, prompt: str, max_tokens: int, temperature: float,
    ) -> tuple[str, int, int]:
        """OpenAI 兼容协议：POST {base}/chat/completions → (正文, 输入, 输出)"""
        response = self._get_client().post(
            base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        response.raise_for_status()
        data = response.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        usage = data.get("usage") or {}
        return (
            text.strip(),
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        )

    def _anthropic_chat(
        self, api_key: str, base_url: str, model: str,
        system: str, prompt: str, max_tokens: int, temperature: float,
    ) -> tuple[str, int, int]:
        """Anthropic Messages 协议：POST {base}/v1/messages → (正文, 输入, 输出)"""
        payload: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        response = self._get_client().post(
            base_url.rstrip("/") + "/v1/messages",
            headers={
                "Authorization": f"Bearer {api_key}",
                "anthropic-version": _ANTHROPIC_VERSION,
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        text = "".join(
            block.get("text", "")
            for block in (data.get("content") or [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        usage = data.get("usage") or {}
        return (
            text.strip(),
            int(usage.get("input_tokens") or 0),
            int(usage.get("output_tokens") or 0),
        )

    def _chat_via(
        self, api_protocol: str, api_key: str, base_url: str, model: str,
        system: str, prompt: str, max_tokens: int, temperature: float,
    ) -> tuple[str, int, int]:
        """按协议分派对话请求 → (正文, 输入 tokens, 输出 tokens)"""
        if api_protocol == "anthropic":
            return self._anthropic_chat(api_key, base_url, model, system, prompt, max_tokens, temperature)
        return self._openai_chat(api_key, base_url, model, system, prompt, max_tokens, temperature)

    # ── 主入口 ───────────────────────────────────────

    def chat(
        self,
        prompt: str,
        system: str,
        purpose: str,
        max_tokens: int = 600,
    ) -> str | None:
        """
        调用 Chat Completions，返回正文。

        任何不可用状态（未配置/熔断/失败）都返回 None 并记录日志，
        调用方据此优雅降级——管线绝不因 LLM 不可用而失败。
        """
        cfg = resolve_llm_config()
        if not cfg.api_key:
            if not self._not_configured_logged:
                logger.info("LLM not configured (no api key), LLM features disabled")
                self._not_configured_logged = True
            return None

        with self._failure_lock:
            if self._consecutive_failures >= settings.llm_max_consecutive_failures:
                logger.warning(
                    "LLM circuit open: %d consecutive failures, skipping purpose=%s",
                    self._consecutive_failures, purpose,
                )
                return None

        remaining = self.remaining_budget()
        if remaining <= 0:
            logger.warning(
                "LLM daily token budget exhausted (%d), skipping purpose=%s until next UTC day",
                cfg.daily_budget, purpose,
            )
            return None

        prompt_hash = _prompt_hash(cfg.model, system, prompt)
        cached = model_receipt_repo.find_done_result(cfg.model, prompt_hash)
        if cached is not None:
            logger.debug("LLM result reused for purpose=%s", purpose)
            return cached

        receipt_id = model_receipt_repo.create_pending(purpose, cfg.model, prompt_hash)
        started = time.monotonic()
        try:
            text, input_tokens, output_tokens = self._chat_via(
                cfg.api_protocol, cfg.api_key, cfg.base_url, cfg.model,
                system, prompt, max_tokens, 0.3,
            )
            if not text:
                raise ValueError("empty completion")
            duration_ms = int((time.monotonic() - started) * 1000)

            model_receipt_repo.complete(receipt_id, text, input_tokens, output_tokens, duration_ms)
            with self._failure_lock:
                self._consecutive_failures = 0
            logger.info(
                "LLM call done purpose=%s tokens=%d+%d in %dms",
                purpose, input_tokens, output_tokens, duration_ms,
            )
            return text
        except Exception as e:  # noqa: BLE001 —— 管线永不因 LLM 失败而中断
            with self._failure_lock:
                self._consecutive_failures += 1
                failures = self._consecutive_failures
            model_receipt_repo.fail(receipt_id, str(e))
            logger.warning(
                "LLM call failed purpose=%s (%d/%d consecutive): %s",
                purpose, failures, settings.llm_max_consecutive_failures, e,
            )
            return None

    # ── 连通性诊断 ───────────────────────────────────

    def test_connection(
        self, api_key: str, base_url: str, model: str, api_protocol: str = "openai",
    ) -> dict:
        """
        配置页的"测试连接"：用给定参数发一次极小请求（max_tokens=16）。

        与 chat() 的区别：
        - 不写回执、不计入预算与失败熔断（用户诊断动作，允许在熔断后验证修复）
        - 不静默降级——把失败原因翻译成用户可读的中文提示返回

        返回 {ok, message, model, latency_ms}
        """
        if not api_key:
            return {"ok": False, "message": "请先填写 API Key", "model": model or None, "latency_ms": None}
        if not base_url:
            return {"ok": False, "message": "请先填写接口地址", "model": model or None, "latency_ms": None}

        started = time.monotonic()
        try:
            sample, _, _ = self._chat_via(
                api_protocol, api_key, base_url, model,
                "", "连接测试，请回复：OK", 16, 0,
            )
            message = "连接成功"
            if sample:
                message += f"，模型回复：{sample[:40]}"
            return self._test_result(True, message, model, started)
        except httpx.TimeoutException:
            return self._test_result(
                False, "连接超时，请检查接口地址与网络后重试", model, started)
        except httpx.TransportError:
            return self._test_result(
                False, "无法连接到接口地址，请检查接口地址与网络", model, started)
        except httpx.HTTPStatusError as e:
            return self._test_result(
                False, _friendly_http_error(e.response.status_code, e.response.text), model, started)
        except Exception as e:  # noqa: BLE001 —— 诊断入口必须给出可读结果而非 500
            return self._test_result(False, f"测试失败：{e}", model, started)

    def list_models(self, api_key: str, base_url: str, api_protocol: str = "openai") -> dict:
        """
        用给定参数拉取服务商的可用模型列表（模型选择用）。

        诊断动作：不写回执、不计入预算与失败熔断。
        返回 {ok, message, models, latency_ms}
        """
        if not api_key:
            return {"ok": False, "message": "请先填写 API Key", "models": [], "latency_ms": None}
        if not base_url:
            return {"ok": False, "message": "请先填写接口地址", "models": [], "latency_ms": None}

        started = time.monotonic()
        if api_protocol == "anthropic":
            url = base_url.rstrip("/") + "/v1/models"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "anthropic-version": _ANTHROPIC_VERSION,
            }
        else:
            url = base_url.rstrip("/") + "/models"
            headers = {"Authorization": f"Bearer {api_key}"}

        try:
            response = self._get_client().get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            items = data.get("data") or data.get("models") or []
            models = []
            for item in items:
                model_id = item.get("id") or item.get("name") if isinstance(item, dict) else str(item)
                if model_id:
                    models.append(str(model_id))
            models.sort()
            message = f"获取到 {len(models)} 个模型" if models else "服务商未返回任何模型，请手动填写模型名称"
            return {
                "ok": True,
                "message": message,
                "models": models,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        except httpx.TimeoutException:
            return {"ok": False, "message": "连接超时，请检查接口地址与网络后重试", "models": [],
                    "latency_ms": int((time.monotonic() - started) * 1000)}
        except httpx.TransportError:
            return {"ok": False, "message": "无法连接到接口地址，请检查接口地址与网络", "models": [],
                    "latency_ms": int((time.monotonic() - started) * 1000)}
        except httpx.HTTPStatusError as e:
            return {"ok": False,
                    "message": _friendly_http_error(e.response.status_code, e.response.text),
                    "models": [],
                    "latency_ms": int((time.monotonic() - started) * 1000)}
        except Exception as e:  # noqa: BLE001 —— 诊断入口必须给出可读结果而非 500
            return {"ok": False, "message": f"获取失败：{e}", "models": [],
                    "latency_ms": int((time.monotonic() - started) * 1000)}

    @staticmethod
    def _test_result(ok: bool, message: str, model: str, started: float) -> dict:
        return {
            "ok": ok,
            "message": message,
            "model": model or None,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }


# 全局单例
llm_provider = LLMProvider()
