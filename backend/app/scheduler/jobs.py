"""
app/scheduler/jobs.py
Job 函数定义：execute_task(task_id)
由 APScheduler 在 Worker 线程中调用，包含完整的抓取流程。
每个执行阶段通过 EventBus 向 SSE 客户端推送细粒度事件。
"""
import logging
import threading
import time
import uuid
from datetime import datetime, timezone

from app.core.event_bus import publish_event
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── 进程级并发锁 ─────────────────────────────────────────
_running_tasks: dict[str, bool] = {}
_lock = threading.Lock()


def acquire_task_lock(task_id: str) -> bool:
    with _lock:
        if _running_tasks.get(task_id):
            return False
        _running_tasks[task_id] = True
        return True


def release_task_lock(task_id: str) -> None:
    with _lock:
        _running_tasks.pop(task_id, None)


def is_task_running(task_id: str) -> bool:
    with _lock:
        return bool(_running_tasks.get(task_id))


# ── 事件发布辅助 ─────────────────────────────────────────

def _pub(task_id: str, etype: str, msg: str, data: dict | None = None) -> None:
    """将 engine 回调格式桥接到 event_bus.publish_event。"""
    publish_event(task_id, etype, msg, data)


def _make_engine_callback(task_id: str):
    """返回传给 engine.fetch_and_parse 的 on_progress 回调。"""
    def callback(event_type: str, message: str, data: dict) -> None:
        _pub(task_id, event_type, message, data)
    return callback


# ── 主执行函数 ───────────────────────────────────────────

def execute_task(task_id: str) -> None:
    """APScheduler 调度入口，防重入 + 异常兜底。"""
    if not acquire_task_lock(task_id):
        logger.warning("Task %s is already running, skip this trigger", task_id)
        return

    exec_id      = str(uuid.uuid4())
    started_at   = datetime.now(timezone.utc)
    executed_at_iso = started_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info("Task execution started", extra={"task_id": task_id, "execution_id": exec_id})
    _pub(task_id, "start", "任务开始执行", {
        "exec_id": exec_id[:8],
        "task_id": task_id,
    })

    try:
        _run_task(task_id, exec_id, executed_at_iso, started_at)
    except Exception as e:
        logger.exception("Unexpected error in execute_task",
                         extra={"task_id": task_id, "execution_id": exec_id})
        _pub(task_id, "failure", f"意外错误: {type(e).__name__}: {e}")
        _record_failure(task_id, exec_id, executed_at_iso, str(e),
                        int((time.time() - started_at.timestamp()) * 1000))
    finally:
        release_task_lock(task_id)


def _run_task(task_id: str, exec_id: str, executed_at_iso: str, started_at: datetime) -> None:
    """核心执行逻辑，包含全链路事件发布。"""
    from app.crawler.dedup import deduplicate
    from app.crawler.engine import fetch_and_parse
    from app.repositories.execution_repo import execution_repo
    from app.repositories.item_repo import item_repo
    from app.repositories.task_repo import task_repo

    wall_start = time.time()

    # ── Step 1: 读取任务配置 ─────────────────────────────
    task = task_repo.get(task_id)
    if not task:
        _pub(task_id, "failure", "任务配置不存在，请刷新页面")
        return

    if task.get("status") == "paused":
        _pub(task_id, "step", "任务已暂停，本次触发已跳过")
        return

    source_url = task["source_url"]
    keywords: list[str] = task.get("keywords") or []

    kw_hint = ""
    if keywords:
        shown = keywords[:4]
        more  = len(keywords) - len(shown)
        kw_hint = "，".join(shown) + (f" 等{more}个" if more else "")

    _pub(task_id, "step_init",
         f"配置加载完成",
         {
             "source_url": source_url[:60],
             "keywords":   kw_hint or "（全量）",
             "keywords_full": keywords,
             "cron":       task.get("cron_expression", ""),
         })

    selectors = {
        "list":      task["selector_list"],
        "title":     task["selector_title"],
        "link":      task["selector_link"],
        "summary":   task.get("selector_summary"),
        "next_page": task.get("selector_next_page"),
    }

    # ── Step 2: 抓取（engine 内部会推送多条细粒度事件）───
    result = fetch_and_parse(
        url=source_url,
        selectors=selectors,
        keywords=keywords,
        on_progress=_make_engine_callback(task_id),
    )

    duration_ms   = int(time.time() * 1000) - int(wall_start * 1000)
    items_fetched = len(result.items)

    # ── Step 3: 处理失败 ─────────────────────────────────
    if not result.success:
        logger.warning("Task %s fetch failed: %s", task_id, result.error,
                       extra={"task_id": task_id, "execution_id": exec_id})
        # Distinguish retry-exhaustion from a one-shot failure in the stored message.
        error_msg = result.error
        if result.retries_used > 0:
            error_msg = f"{error_msg} (retries used: {result.retries_used})"
        execution_repo.insert({
            "id": exec_id, "task_id": task_id, "status": "failure",
            "items_fetched": 0, "items_new": 0, "duration_ms": duration_ms,
            "error_message": error_msg, "executed_at": executed_at_iso,
        })
        task_repo.update_execution_stats(task_id, success=False, empty=False,
                                         executed_at=executed_at_iso)
        _pub(task_id, "failure",
             f"抓取失败: {result.error}",
             {"duration_ms": duration_ms,
              "pages_fetched": result.pages_fetched,
              "retries_used": result.retries_used})
        return

    # ── Step 4: 去重 ─────────────────────────────────────
    _pub(task_id, "dedup_start",
         f"正在检查 {items_fetched} 条 URL 是否已采集…",
         {"total": items_fetched})

    new_items  = deduplicate(result.items)
    items_new  = len(new_items)
    dup_count  = items_fetched - items_new

    _pub(task_id, "dedup_done",
         f"去重完成：{items_new} 条新增，{dup_count} 条已存在",
         {"new": items_new, "duplicates": dup_count})

    # ── Step 5: 写入数据库 ───────────────────────────────
    if new_items:
        _pub(task_id, "save_start",
             f"正在写入 {items_new} 条新数据…",
             {"count": items_new})
        records = [{
            "task_id":   task_id,
            "title":     item.title,
            "url":       item.url,
            "url_hash":  item.url_hash,
            "summary":   item.summary,
            "fetched_at": executed_at_iso,
        } for item in new_items]
        item_repo.bulk_insert(records)
        _pub(task_id, "save_done",
             f"已保存 {items_new} 条到数据库",
             {"saved": items_new})

        # ── Step 5.5: 计算 Thread 归属 ─────────────────────
        if new_items:
            _pub(task_id, "thread_start", "正在计算多平台聚合…")
            try:
                from app.services.thread_service import thread_service
                # 重新获取刚插入的 items（带 DB ID）
                recent = item_repo.query(
                    task_id=task_id,
                    search=None,
                    starred=None,
                    is_read=None,
                    page=1,
                    per_page=items_new,
                )[0]
                # 只取当前批次刚插入的（按 fetched_at 匹配）
                new_records = [
                    r for r in recent
                    if r.get("fetched_at", "") == executed_at_iso
                ]
                if new_records:
                    thread_service.compute_threads_for_items(new_records)
                    _pub(task_id, "thread_done",
                         f"Thread 聚合完成")
            except Exception as e:
                logger.warning("Thread compute failed: %s", e)
                _pub(task_id, "thread_skip", "Thread 聚合跳过")

        # 推送前 3 条新条目预览
        preview = [
            {"title": item.title[:80], "url": item.url[:100], "summary": item.summary[:60]}
            for item in new_items[:3]
        ]
        _pub(task_id, "items_preview",
             f"新增条目预览（共 {items_new} 条）",
             {"items": preview, "total": items_new})
    else:
        _pub(task_id, "save_skip",
             "无新增数据，跳过写入")

    # ── Step 6: 记录执行结果 ─────────────────────────────
    is_empty   = items_fetched == 0
    exec_status = "warning" if is_empty else "success"

    execution_repo.insert({
        "id": exec_id, "task_id": task_id, "status": exec_status,
        "items_fetched": items_fetched, "items_new": items_new,
        "duration_ms": duration_ms, "error_message": None,
        "executed_at": executed_at_iso,
    })
    task_repo.update_execution_stats(task_id, success=True,
                                     empty=is_empty, executed_at=executed_at_iso)

    # ── Step 7: 最终事件 ─────────────────────────────────
    if is_empty:
        _pub(task_id, "warning",
             f"采集完成但无数据（Selector 可能已失效）耗时 {duration_ms}ms",
             {"items_fetched": 0, "items_new": 0, "duration_ms": duration_ms,
              "html_size_kb": result.html_size_kb, "list_count": result.list_count,
              "pages_fetched": result.pages_fetched, "retries_used": result.retries_used})
    else:
        _pub(task_id, "success",
             f"执行成功：新增 {items_new} 条，共抓取 {items_fetched} 条，耗时 {duration_ms}ms",
             {"items_new": items_new, "items_fetched": items_fetched,
              "duration_ms": duration_ms, "html_size_kb": result.html_size_kb,
              "pages_fetched": result.pages_fetched, "retries_used": result.retries_used})

    logger.info("Task %s done: fetched=%d new=%d duration=%dms",
                task_id, items_fetched, items_new, duration_ms,
                extra={"task_id": task_id, "execution_id": exec_id})


def _record_failure(task_id: str, exec_id: str, executed_at: str,
                    error: str, duration_ms: int) -> None:
    try:
        from app.repositories.execution_repo import execution_repo
        from app.repositories.task_repo import task_repo
        execution_repo.insert({
            "id": exec_id, "task_id": task_id, "status": "failure",
            "items_fetched": 0, "items_new": 0, "duration_ms": duration_ms,
            "error_message": error[:1000], "executed_at": executed_at,
        })
        task_repo.update_execution_stats(task_id, success=False, empty=False,
                                         executed_at=executed_at)
    except Exception as e:
        logger.error("Failed to record failure for task %s: %s", task_id, e)
