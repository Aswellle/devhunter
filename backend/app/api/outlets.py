"""
app/api/outlets.py
机器可读出口（Machine Outlets）：面向 RSS 阅读器、LLM Agent 与外部工具的只读端点。

- GET /api/llms.txt        公开：llms.txt 站点能力说明（llmstxt.org 规范）
- GET /api/rss             机器令牌或用户认证：全部条目 RSS 2.0
- GET /api/rss/{task_id}   机器令牌或用户认证：按数据源的 RSS
- GET /api/rss/feeds       用户认证：列出全部订阅地址与能力令牌（JSON）

安全模型：RSS 用 URL 携带的能力令牌认证（阅读器无法走 httpOnly cookie），
令牌由 SECRET_KEY 经 HMAC 派生（core/security.machine_token），
轮换 SECRET_KEY 即吊销。
"""
from email.utils import format_datetime
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.api.deps import require_auth, require_machine_access
from app.core.security import machine_token
from app.repositories.task_repo import task_repo
from app.services.item_service import item_service

router = APIRouter(tags=["outlets"])

RSS_PAGE_SIZE = 100

_LLMS_TXT = """# DevHunter

> 自托管的内容聚合系统：配置一次爬取任务（URL + 选择器/JSON 路径 + 关键词 + Cron），
> DevHunter 按计划自动抓取、去重、存储、索引，将跨平台事件聚合为 Thread，
> 并提供个性化推荐与全文搜索（FTS5）。

DevHunter 是单用户自托管服务。除 `/api/health` 与本文件外，所有 API 均需认证：
登录端点 `POST /api/auth/login` 签发 JWT（7 天有效），通过 httpOnly cookie
`devhunter_token` 或 `Authorization: Bearer <JWT>` 携带。

## 机器可读出口

- [RSS 全部条目](/api/rss)：最新 100 条采集内容，含全文摘要。需要能力令牌（`?token=`），令牌可经认证请求 `GET /api/rss/feeds` 获取。
- [RSS 按数据源](/api/rss/{task_id})：单个爬取任务的订阅，同上需要令牌。
- [订阅地址清单](/api/rss/feeds)：认证后返回所有订阅 URL 与能力令牌（JSON）。

## 主要 API（需认证）

- GET /api/items：分页条目列表，支持 `task_id`、`search`（FTS5 全文）、`starred`、`is_read`
- GET /api/items/{id}：条目详情
- GET /api/items/threads：跨平台事件 Thread 列表（分页，可按 `task_id` 过滤）
- GET /api/items/threads/{id}：Thread 详情（含条目与聚合画像 stats）
- GET /api/recommendations：个性化推荐（含推荐理由）
- GET /api/stats：仪表盘统计
- GET /api/tasks：爬取任务 CRUD
- GET /api/executions、GET /api/sources、GET /api/topics：执行历史 / 爬取模板 / 用户主题
- GET /api/health：健康检查（无需认证）
"""


@router.get("/llms.txt")
def llms_txt() -> Response:
    """llms.txt：站点能力说明，供 LLM Agent 发现本服务的能力。公开、无用户数据。"""
    return Response(
        content=_LLMS_TXT,
        media_type="text/plain; charset=utf-8",
    )


# ── RSS 出口 ─────────────────────────────────────────────
# 注意：/rss/feeds 必须注册在 /rss/{task_id} 之前，否则 "feeds" 会被路径参数吞掉


@router.get("/rss/feeds")
def list_feeds(request: Request, _: str = Depends(require_auth)):
    """列出所有 RSS 订阅地址与能力令牌（需用户认证；令牌不出现在无认证响应里）。"""
    base = _site_base_url(request)
    token = machine_token()
    feeds = [
        {
            "task_id": t["id"],
            "task_name": t["name"],
            "url": f"{base}/api/rss/{t['id']}?token={token}",
        }
        for t in task_repo.list_active()
    ]
    return {
        "token": token,
        "base_url": base,
        "all_url": f"{base}/api/rss?token={token}",
        "feeds": feeds,
    }


@router.get("/rss/{task_id}")
def rss_by_task(task_id: str, request: Request, _: str = Depends(require_machine_access)):
    """按数据源输出 RSS 2.0（最新 100 条）。"""
    task = task_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Task not found"})
    items, _total = item_service.list_items(task_id=task_id, page=1, per_page=RSS_PAGE_SIZE)
    xml = _build_rss(
        channel_title=f"DevHunter · {task['name']}",
        site_url=_site_base_url(request),
        items=items,
    )
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")


@router.get("/rss")
def rss_all(request: Request, _: str = Depends(require_machine_access)):
    """全部条目的 RSS 2.0（最新 100 条）。"""
    items, _total = item_service.list_items(page=1, per_page=RSS_PAGE_SIZE)
    xml = _build_rss(
        channel_title="DevHunter · 全部采集",
        site_url=_site_base_url(request),
        items=items,
    )
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")


# ── 内部实现 ─────────────────────────────────────────────


def _site_base_url(request: Request) -> str:
    """从请求推导站点根 URL（RSS channel link 与订阅地址用）。"""
    return str(request.base_url).rstrip("/")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _rfc822(value: str | None) -> str:
    """ISO 时间 → RFC 822（RSS pubDate 规范）。解析失败返回空串。"""
    dt = _parse_dt(value)
    return format_datetime(dt) if dt else ""


def _build_rss(channel_title: str, site_url: str, items: list[dict[str, Any]]) -> str:
    """
    手工构建 RSS 2.0 XML（无外部依赖）。

    所有动态文本经 xml escape，杜绝注入；guid 用条目内部 id（isPermaLink=false），
    链接是外链原文地址；发布时间取 fetched_at（回落 created_at）。
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        f"<title>{escape(channel_title)}</title>",
        f"<link>{escape(site_url)}</link>",
        "<description>DevHunter 采集内容订阅</description>",
        "<generator>DevHunter</generator>",
    ]
    for it in items:
        title = it.get("title") or "(untitled)"
        url = it.get("url") or ""
        summary = it.get("summary") or ""
        pub_date = _rfc822(it.get("fetched_at") or it.get("created_at"))
        task_name = it.get("task_name") or ""
        lines += [
            "<item>",
            f"<title>{escape(title)}</title>",
            f"<link>{escape(url)}</link>",
            f'<guid isPermaLink="false">{escape(str(it.get("id") or ""))}</guid>',
            f"<pubDate>{escape(pub_date)}</pubDate>",
            f"<category>{escape(task_name)}</category>",
            f"<description>{escape(summary)}</description>",
            "</item>",
        ]
    lines += ["</channel>", "</rss>"]
    return "\n".join(lines)
