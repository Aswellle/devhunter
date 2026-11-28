"""
app/sources/opml.py
OPML（RSS 订阅清单）导入/导出（PROD-001）。

导入路径：解析 → SSRF 预检 → 重复检测（预览）→ 以草稿（paused）创建
rss: 任务，用户确认后才在任务页启用。导出路径：把已启用的 RSS 任务
输出为 OPML，便于迁移到其他阅读器。
"""
import html
import logging
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse

from app.core.ssrf import resolve_and_validate_url

logger = logging.getLogger(__name__)

# OPML 是纯文本清单：限制大小，避免恶意文件撑爆解析
MAX_OPML_BYTES = 2 * 1024 * 1024

_RSS_SELECTORS = {
    "selector_list": "rss:",
    "selector_title": "rss:title",
    "selector_link": "rss:link",
    "selector_summary": "rss:description",
}


def _validate_url_safe(url: str) -> tuple[bool, str]:
    """SSRF 预检（DNS 解析 + 私网/回环黑名单，fail-closed）。

    独立薄封装便于测试注入；生产路径始终走 core/ssrf。
    """
    ok, msg, _ip = resolve_and_validate_url(url)
    return ok, msg


def parse_opml(content: str) -> list[dict[str, str]]:
    """解析 OPML，返回 [{title, xml_url, html_url}]。

    只接受 http/https 的 xmlUrl；无 xmlUrl 的 outline（文件夹/说明项）
    跳过。畸形 XML / 空内容抛 ValueError（由 API 层转 400）。
    """
    if not content or not content.strip():
        raise ValueError("OPML 内容为空")
    if len(content.encode("utf-8", errors="ignore")) > MAX_OPML_BYTES:
        raise ValueError("OPML 文件过大（上限 2MB）")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise ValueError(f"OPML 解析失败：{e}") from e

    if root.tag.lower() != "opml":
        raise ValueError("不是有效的 OPML 文件（根元素不是 <opml>）")

    entries: list[dict[str, str]] = []
    for outline in root.iter("outline"):
        xml_url = (outline.get("xmlUrl") or outline.get("xmlurl") or "").strip()
        if not xml_url:
            continue
        scheme = urlparse(xml_url).scheme.lower()
        if scheme not in ("http", "https"):
            continue
        entries.append({
            "title": (outline.get("title") or outline.get("text") or xml_url).strip(),
            "xml_url": xml_url,
            "html_url": (outline.get("htmlUrl") or outline.get("htmlurl") or "").strip(),
        })
    return entries


def preview_entries(
    entries: list[dict[str, str]], existing_urls: set[str],
) -> list[dict[str, Any]]:
    """为每个条目补充 SSRF 校验结果与重复标记（导入前预览）。"""
    result: list[dict[str, Any]] = []
    for entry in entries:
        safe, error = _validate_url_safe(entry["xml_url"])
        result.append({
            **entry,
            "safe": safe,
            "error": "" if safe else error,
            "duplicate": entry["xml_url"] in existing_urls,
        })
    return result


def task_payloads(entries: list[dict[str, str]]) -> list[dict[str, Any]]:
    """把 OPML 条目转成 rss: 任务创建载荷（草稿：status=paused）。"""
    payloads: list[dict[str, Any]] = []
    for entry in entries:
        payloads.append({
            "name": entry["title"][:100] or entry["xml_url"][:100],
            "source_url": entry["xml_url"],
            "template_id": None,
            **_RSS_SELECTORS,
            "keywords": [],
            # 每小时一次：先草稿保存，验证后由用户启用
            "cron_expression": "0 * * * *",
            "content_kind": "discussion",
            "status": "paused",
        })
    return payloads


def export_opml(tasks: list[dict[str, Any]], title: str = "DevHunter Feeds") -> str:
    """把已启用（active）的 RSS 任务导出为 OPML 2.0。

    只导出 selector_list 以 rss: 开头的任务——HTML/X 等非订阅来源写成
    OPML 会让其他阅读器订阅到不可解析的页面。
    """
    outlines: list[str] = []
    for t in tasks:
        if (t.get("status") or "") != "active":
            continue
        if not (t.get("selector_list") or "").startswith("rss:"):
            continue
        url = t.get("source_url") or ""
        if not url:
            continue
        name = t.get("name") or url
        outlines.append(
            '    <outline type="rss" text="{text}" title="{title}" xmlUrl="{xml}"/>'.format(
                text=html.escape(name, quote=True),
                title=html.escape(name, quote=True),
                xml=html.escape(url, quote=True),
            )
        )

    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        "  <head>",
        f"    <title>{html.escape(title)}</title>",
        "  </head>",
        "  <body>",
        *outlines,
        "  </body>",
        "</opml>",
    ])
