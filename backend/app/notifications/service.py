"""
app/notifications/service.py
通知规则匹配与 Webhook 投递（PROD-003）。

- 触发：keyword（保存搜索的关键词命中新条目）、thread（多来源 Thread）、
  health（来源执行失败/部分成功）。
- 投递：入队即写 notification_deliveries（(rule_id, event_key) 唯一 →
  同事件幂等），后台任务按重试计划投递；MAX_ATTEMPTS 次失败后进入
  dead-letter，可经 API 手动重试。
- 安全：每次投递前对 webhook URL 做 SSRF 预检（fail-closed），错误信息
  只记异常类型/状态码，绝不回显 URL（URL 可能含 path token）。
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.http_client import get_http_client
from app.notifications.repo import notification_repo as repo

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
# 指数退避（分钟）：1, 2, 4, 8, 16
BACKOFF_MINUTES = [1, 2, 4, 8, 16]
DELIVERY_TIMEOUT = 10.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ssrf_check(url: str) -> tuple[bool, str]:
    """Webhook 投递前 SSRF 预检（独立薄封装便于测试注入）。"""
    from app.core.ssrf import resolve_and_validate_url
    ok, msg, _ip = resolve_and_validate_url(url)
    return ok, msg


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    lowered = (text or "").lower()
    return any(k.strip() and k.strip().lower() in lowered for k in keywords)


# ── 触发：匹配规则并入队 ────────────────────────────────────────

def dispatch_keyword_items(items: list[dict[str, Any]]) -> int:
    """保存搜索触发：新条目命中关键词规则 → 入队投递。

    同一条目对同一规则只入队一次（event_key = item:<id>）。返回新入队数。
    """
    rules = repo.list_enabled_rules("keyword")
    if not rules or not items:
        return 0
    fired = 0
    for item in items:
        item_id = item.get("id") or ""
        if not item_id:
            continue
        text = f"{item.get('title') or ''} {item.get('summary') or ''}"
        for rule in rules:
            keywords = (rule.get("config") or {}).get("keywords") or []
            if not _matches_keywords(text, keywords):
                continue
            created = repo.enqueue(
                rule_id=rule["id"],
                channel_id=rule["channel_id"],
                event_key=f"item:{item_id}",
                payload={
                    "trigger": "keyword",
                    "rule": rule["name"],
                    "item": {
                        "id": item_id,
                        "title": item.get("title") or "",
                        "url": item.get("url") or "",
                        "summary": (item.get("summary") or "")[:300],
                    },
                },
            )
            if created:
                fired += 1
                repo.mark_rule_fired(rule["id"])
    return fired


def dispatch_thread_event(thread: dict[str, Any]) -> int:
    """Thread 触发：多来源 Thread 命中规则 → 入队。

    event_key = thread:<id>:<item_count>：同一 Thread 报道数增长时可再次
    通知（新进展），但同一状态不重复。
    """
    rules = repo.list_enabled_rules("thread")
    thread_id = thread.get("id") or thread.get("thread_id") or ""
    if not rules or not thread_id:
        return 0
    item_count = int(thread.get("item_count") or 0)
    platforms = thread.get("platforms") or []
    fired = 0
    for rule in rules:
        min_items = int((rule.get("config") or {}).get("min_items") or 2)
        if item_count < min_items or len(platforms) < 2:
            continue
        created = repo.enqueue(
            rule_id=rule["id"],
            channel_id=rule["channel_id"],
            event_key=f"thread:{thread_id}:{item_count}",
            payload={
                "trigger": "thread",
                "rule": rule["name"],
                "thread": {
                    "id": thread_id,
                    "title": thread.get("title") or "",
                    "item_count": item_count,
                    "platforms": platforms,
                    "url": f"/?thread={thread_id}",
                },
            },
        )
        if created:
            fired += 1
            repo.mark_rule_fired(rule["id"])
    return fired


def dispatch_health_event(event: dict[str, Any]) -> int:
    """来源健康触发：任务失败/部分成功 → 入队。

    event_key = health:<task_id>:<kind>:<executed_at>：同一次执行只通知一次。
    """
    rules = repo.list_enabled_rules("health")
    task_id = event.get("task_id") or ""
    if not rules or not task_id:
        return 0
    kind = event.get("kind") or ""
    fired = 0
    for rule in rules:
        kinds = (rule.get("config") or {}).get("kinds") or ["failure"]
        if kind not in kinds:
            continue
        created = repo.enqueue(
            rule_id=rule["id"],
            channel_id=rule["channel_id"],
            event_key=f"health:{task_id}:{kind}:{event.get('executed_at') or ''}",
            payload={
                "trigger": "health",
                "rule": rule["name"],
                "source": {
                    "task_id": task_id,
                    "task_name": event.get("task_name") or "",
                    "kind": kind,
                    "message": (event.get("message") or "")[:300],
                },
            },
        )
        if created:
            fired += 1
            repo.mark_rule_fired(rule["id"])
    return fired


# ── 投递 ───────────────────────────────────────────────────────

def deliver_pending(limit: int = 50) -> dict[str, int]:
    """投递到期待发通知。

    成功 → sent；失败 → failed 并按指数退避安排下次重试；达到
    MAX_ATTEMPTS → dead（需手动重试）。SSRF 拦截与网络错误同等处理。
    """
    stats = {"sent": 0, "failed": 0, "dead": 0}
    for delivery in repo.list_pending_deliveries(limit=limit):
        channel = repo.get_channel(delivery["channel_id"])
        if not channel or not channel.get("enabled"):
            # 渠道被删除/停用：保留记录，标记 dead，避免无限重试
            repo.mark_failed(delivery["id"], "channel unavailable", None, dead=True)
            stats["dead"] += 1
            continue

        url = channel.get("url") or ""
        safe, msg = _ssrf_check(url)
        if not safe:
            _fail(delivery, f"SSRF blocked: {msg}", stats)
            continue

        try:
            response = get_http_client().post(
                url,
                json=delivery.get("payload") or {},
                headers={"Content-Type": "application/json"},
                timeout=DELIVERY_TIMEOUT,
            )
            if response.status_code >= 400:
                # 只记录状态码：响应体/URL 可能含敏感信息
                _fail(delivery, f"HTTP {response.status_code}", stats)
                continue
        except httpx.TimeoutException:
            _fail(delivery, "timeout", stats)
            continue
        except httpx.RequestError as e:
            # 不记录 URL/请求体，只记异常类型
            _fail(delivery, f"connection error: {type(e).__name__}", stats)
            continue

        repo.mark_sent(delivery["id"])
        stats["sent"] += 1
    return stats


def _fail(delivery: dict[str, Any], error: str, stats: dict[str, int]) -> None:
    attempts = int(delivery.get("attempts") or 0) + 1
    if attempts >= MAX_ATTEMPTS:
        repo.mark_failed(delivery["id"], error, None, dead=True)
        stats["dead"] += 1
        logger.warning(
            "Notification delivery dead-lettered (rule=%s, attempts=%d): %s",
            delivery.get("rule_id"), attempts, error,
        )
        return
    delay = BACKOFF_MINUTES[min(attempts - 1, len(BACKOFF_MINUTES) - 1)]
    next_at = _iso(_now() + timedelta(minutes=delay))
    repo.mark_failed(delivery["id"], error, next_at, dead=False)
    stats["failed"] += 1


def retry_delivery(delivery_id: str) -> bool:
    """手动重试（dead-letter 恢复）：重置为 pending。"""
    return repo.reset_for_retry(delivery_id)


def dispatch_deliveries_job() -> None:
    """调度入口：投递所有到期通知（调度器每 5 分钟调用）。"""
    try:
        stats = deliver_pending()
        if any(stats.values()):
            logger.info(
                "Notification deliveries: sent=%d failed=%d dead=%d",
                stats["sent"], stats["failed"], stats["dead"],
            )
    except Exception as e:
        logger.error("Notification delivery job failed: %s", e)
