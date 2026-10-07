"""
app/llm/provider.py
LLM 调用基础设施：OpenAI 兼容 Chat Completions + 付费回执纪律。

付费纪律（四条，全部在 chat() 内强制执行）：
1. 回执先行 —— 调用前落 pending 回执，成功补全结果；崩溃/重启不丢"已付费"账
2. 结果复用 —— 相同 (model, system, prompt) 的已完成调用直接复用正文，不重复付费
3. 预算熔断 —— 当日（UTC）token 累计超过 llm_daily_token_budget 即熔断，次日自动恢复
4. 失败熔断 —— 连续失败达 llm_max_consecutive_failures 后停止调用（进程生命周期内），
   防止服务端故障时重试烧钱

未配置 llm_api_key 时全链路静默关闭：chat() 返回 None，调用方优雅降级，
页面不出现任何 LLM 相关 UI。

线程安全：APScheduler worker 与 API 请求线程都可能调用；熔断计数用锁保护。
"""
import hashlib
import logging
import threading
import time

import httpx

from app.core.config import settings
from app.llm.receipt_repo import model_receipt_repo

logger = logging.getLogger(__name__)


def _utc_day_start_iso() -> str:
    """当前 UTC 日的零点（ISO），作为预算统计窗口起点"""
    now = time.gmtime()
    return time.strftime("%Y-%m-%dT00:00:00Z", now)


def _prompt_hash(model: str, system: str, prompt: str) -> str:
    return hashlib.sha256(f"{model}\x00{system}\x00{prompt}".encode("utf-8")).hexdigest()


class LLMProvider:
    """OpenAI 兼容 Chat Completions 客户端（带付费纪律）"""

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
        return bool(settings.llm_api_key)

    def is_available(self) -> bool:
        """配置齐全且未触发任何熔断"""
        if not self.is_configured():
            return False
        with self._failure_lock:
            if self._consecutive_failures >= settings.llm_max_consecutive_failures:
                return False
        return self.remaining_budget() > 0

    def remaining_budget(self) -> int:
        """今日剩余 token 预算"""
        used = model_receipt_repo.tokens_since(_utc_day_start_iso())
        return max(0, settings.llm_daily_token_budget - used)

    # ── 测试注入口 ───────────────────────────────────

    def set_test_transport(self, transport: httpx.BaseTransport | None) -> None:
        """注入 httpx MockTransport（仅测试使用）；传 None 恢复真实客户端"""
        with self._client_lock:
            self._test_transport = transport
            self._client = None  # 强制重建

    # ── 内部 ─────────────────────────────────────────

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            with self._client_lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.Client(
                        base_url=settings.llm_base_url.rstrip("/"),
                        headers={
                            "Authorization": f"Bearer {settings.llm_api_key}",
                            "Content-Type": "application/json",
                        },
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
        if not self.is_configured():
            if not self._not_configured_logged:
                logger.info("LLM not configured (llm_api_key empty), LLM features disabled")
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
                settings.llm_daily_token_budget, purpose,
            )
            return None

        prompt_hash = _prompt_hash(settings.llm_model, system, prompt)
        cached = model_receipt_repo.find_done_result(settings.llm_model, prompt_hash)
        if cached is not None:
            logger.debug("LLM result reused for purpose=%s", purpose)
            return cached

        receipt_id = model_receipt_repo.create_pending(purpose, settings.llm_model, prompt_hash)
        started = time.monotonic()
        try:
            response = self._get_client().post(
                "/chat/completions",
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            data = response.json()
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
            if not text:
                raise ValueError("empty completion")
            usage = data.get("usage") or {}
            input_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)
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


# 全局单例
llm_provider = LLMProvider()
