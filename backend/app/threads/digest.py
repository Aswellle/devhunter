"""
app/threads/digest.py
Thread AI 综述：多来源事件的中文摘要生成。

纪律：
- 答案先行：第一句直接说清发生了什么
- 防幻觉：只允许使用材料中出现的事实，不添加材料之外的公司/产品/时间
- 诚实标注：前端展示时明确标记"由 AI 生成"
- 优雅降级：LLM 未配置/熔断/失败时返回 None，综述面板不渲染，
  管线绝不因此失败
"""
import logging
from typing import Any

from app.llm.provider import llm_provider

logger = logging.getLogger(__name__)

# 综述生成的门槛：单条目的 Thread 没有综述价值
DIGEST_MIN_ITEMS = 2
# 材料条数上限（防超长 prompt）与单条摘要截断
MAX_MATERIAL_ITEMS = 10
MAX_SUMMARY_CHARS = 300

DIGEST_SYSTEM_PROMPT = """你是严谨的中文新闻编辑。根据给定的多条报道材料，写一段 80-150 字的中文事件综述。
要求：
1. 答案先行：第一句直接说清发生了什么。
2. 只使用材料中出现的事实、公司名、产品名与时间，绝不添加材料之外的信息。
3. 不确定的内容不写；不使用 Markdown 和表情符号。
4. 直接输出综述正文，不要任何前缀或解释。"""


def build_digest_prompt(thread_title: str, items: list[dict[str, Any]]) -> tuple[str, str]:
    """
    构建综述提示词。

    Args:
        thread_title: Thread 标题
        items: get_items_in_thread 返回的条目（含 task_name/title/summary）

    Returns:
        (system, user) 提示词二元组。
    """
    lines = [f"事件标题：{thread_title}", "", "报道材料："]
    for i, item in enumerate(items[:MAX_MATERIAL_ITEMS], start=1):
        source = item.get("task_name") or "未知来源"
        title = (item.get("title") or "").strip()
        summary = (item.get("summary") or "").strip()[:MAX_SUMMARY_CHARS]
        lines.append(f"{i}. [{source}] {title}")
        if summary:
            lines.append(f"   摘要：{summary}")
    return DIGEST_SYSTEM_PROMPT, "\n".join(lines)


def generate_digest(thread_id: str) -> str | None:
    """
    为指定 Thread 生成并存储 AI 综述。

    门槛：Thread 存在、无既有综述、条目数 >= DIGEST_MIN_ITEMS、LLM 可用。
    任何不满足都返回 None（幂等，可安全重复调用）。
    """
    from app.repositories.thread_repo import thread_repo

    thread = thread_repo.get(thread_id)
    if not thread:
        return None
    if thread.get("digest"):
        return thread["digest"]
    if (thread.get("item_count") or 0) < DIGEST_MIN_ITEMS:
        return None
    if not llm_provider.is_available():
        return None

    items = thread_repo.get_items_in_thread(thread_id)
    system, user = build_digest_prompt(thread.get("title", ""), items)
    text = llm_provider.chat(user, system, purpose="thread_digest", max_tokens=500)
    if not text:
        return None

    thread_repo.save_digest(thread_id, text)
    logger.info("Digest generated for thread %s (%d chars)", thread_id, len(text))
    return text
