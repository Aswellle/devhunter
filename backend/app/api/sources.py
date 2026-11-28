"""
app/api/sources.py
Sources API：3-step template wizard + template marketplace/sharing.

端点：
- POST /api/sources/discover - Step 1: URL 自动发现
- POST /api/sources/preview - Step 2: 预览提取
- POST /api/sources/test - Step 3: 测试配置
- POST /api/sources - 保存模板
- GET /api/sources - 列出模板
- GET /api/sources/{id} - 获取模板详情
- POST /api/sources/{id}/share - 分享模板到市场
- POST /api/sources/{id}/unshare - 取消分享
- GET /api/sources/marketplace - 浏览市场
- POST /api/sources/{id}/import - 从市场导入
- POST /api/sources/{id}/clone - 克隆模板
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Optional

from app.api.deps import require_auth
from app.sources.discovery import url_discoverer, DiscoveryResult
from app.sources.preview import preview_extractor
from app.sources.tester import config_tester
from app.sources.registry import template_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["sources"])



class DiscoverRequest(BaseModel):
    url: str = Field(..., description="Target URL to discover")


class PreviewRequest(BaseModel):
    url: str = Field(..., description="Target URL to preview")
    discovery_result: Optional[dict] = Field(None, description="Discovery result from /discover")


class TestRequest(BaseModel):
    url: str = Field(..., description="Target URL to test")
    selectors: dict = Field(default_factory=dict, description="CSS selectors configuration")
    expected_min_items: int = Field(1, ge=1, description="Expected minimum items")
    required_fields: list[str] = Field(default=["title", "link"], description="Required fields")


class CreateSourceRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Template name")
    source_url: str = Field(..., max_length=2048, description="Source URL")
    selectors: dict = Field(default_factory=dict, description="CSS selectors configuration")
    keywords: list[str] = Field(default_factory=list, description="Filter keywords")
    cron_expression: str = Field("0 9 * * *", max_length=100, description="Cron expression")
    category: Optional[str] = Field(None, description="Template category")
    tags: list[str] = Field(default_factory=list, description="Template tags")


class ShareRequest(BaseModel):
    category: Optional[str] = Field(None, description="Marketplace category")
    tags: list[str] = Field(default_factory=list, description="Template tags")


class CloneRequest(BaseModel):
    name: Optional[str] = Field(None, description="Custom name for cloned template")


@router.post("/discover")
def discover_source(
    body: DiscoverRequest,
    _: str = Depends(require_auth),
):
    """
    Step 1: URL 自动发现。

    输入: { "url": "https://example.com" }
    输出: DiscoveryResult JSON
    """
    url = body.url
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    result = url_discoverer.discover(url)
    return result.to_dict()


@router.post("/preview")
def preview_source(
    body: PreviewRequest,
    _: str = Depends(require_auth),
):
    """
    Step 2: 预览提取。

    输入: { "url": "...", "discovery_result": {...} }
    输出: PreviewResult JSON
    """
    url = body.url
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    discovery_data = body.discovery_result
    discovery_result = None
    if discovery_data:
        try:
            discovery_result = DiscoveryResult(**discovery_data)
        except TypeError as e:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_DISCOVERY", "message": f"发现结果格式不正确: {e}"},
            )

    result = preview_extractor.preview(url, discovery_result)
    return result.to_dict()


@router.post("/test")
def test_source(
    body: TestRequest,
    _: str = Depends(require_auth),
):
    """
    Step 3: 测试配置。

    输入: { "url": "...", "selectors": {...}, "expected_min_items": 5 }
    输出: TestResult JSON
    """
    url = body.url
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    selectors = body.selectors
    expected_min_items = body.expected_min_items
    required_fields = body.required_fields

    result = config_tester.test(url, selectors, expected_min_items, required_fields)
    return result.to_dict()


class OpmlPreviewRequest(BaseModel):
    content: str = Field(..., description="OPML 文件全文")


class OpmlImportEntry(BaseModel):
    xml_url: str = Field(..., max_length=2048)
    title: str = Field("", max_length=200)
    html_url: str = Field("", max_length=2048)


class OpmlImportRequest(BaseModel):
    entries: list[OpmlImportEntry] = Field(..., min_length=1, max_length=200)


@router.post("/opml/preview")
def opml_preview(
    body: OpmlPreviewRequest,
    _: str = Depends(require_auth),
):
    """OPML 导入预览：解析清单、SSRF 预检、标记与既有来源重复的条目。

    只做预览不落库——用户确认（可去掉重复/不安全条目）后再调用
    /opml/import。
    """
    from app.sources import opml as opml_module
    from app.repositories.task_repo import task_repo as _task_repo

    try:
        entries = opml_module.parse_opml(body.content)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_OPML", "message": str(e)},
        )
    existing = {
        t.get("source_url") for t in _task_repo.list_all_tasks() if t.get("source_url")
    }
    preview = opml_module.preview_entries(entries, existing)
    return {
        "entries": preview,
        "total": len(preview),
        "duplicates": sum(1 for e in preview if e["duplicate"]),
        "unsafe": sum(1 for e in preview if not e["safe"]),
    }


@router.post("/opml/import", status_code=status.HTTP_201_CREATED)
def opml_import(
    body: OpmlImportRequest,
    _: str = Depends(require_auth),
):
    """把选定的 OPML 条目导入为草稿（paused）RSS 任务。

    导入前逐条重新执行 SSRF 校验（不信任客户端回传的 preview 结论）；
    重复来源（同 source_url 已存在）与不安全地址跳过并计入响应。
    """
    from app.sources import opml as opml_module
    from app.repositories.task_repo import task_repo as _task_repo
    from app.services.task_service import task_service

    entries = [
        {"title": e.title, "xml_url": e.xml_url, "html_url": e.html_url}
        for e in body.entries
    ]
    existing = {
        t.get("source_url") for t in _task_repo.list_all_tasks() if t.get("source_url")
    }
    created = 0
    skipped_duplicate = 0
    skipped_unsafe = 0
    errors: list[str] = []
    for entry in entries:
        url = entry["xml_url"]
        if url in existing:
            skipped_duplicate += 1
            continue
        safe, reason = opml_module._validate_url_safe(url)
        if not safe:
            skipped_unsafe += 1
            errors.append(f"{url}: {reason}")
            continue
        try:
            task_service.create(opml_module.task_payloads([entry])[0])
            created += 1
        except Exception as e:
            errors.append(f"{url}: {e}")
    return {
        "created": created,
        "skipped_duplicate": skipped_duplicate,
        "skipped_unsafe": skipped_unsafe,
        "errors": errors,
    }


@router.get("/opml/export")
def opml_export(_: str = Depends(require_auth)):
    """导出已启用的 RSS 来源为 OPML 2.0（可用其他阅读器导入）。"""
    from app.sources import opml as opml_module
    from app.repositories.task_repo import task_repo as _task_repo

    xml_text = opml_module.export_opml(_task_repo.list_all_tasks())
    return Response(
        content=xml_text,
        media_type="text/x-opml; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="devhunter-feeds.opml"'},
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_source(
    body: CreateSourceRequest,
    _: str = Depends(require_auth),
):
    """
    保存模板（创建自定义来源）。

    输入: {
        "name": "My Source",
        "source_url": "...",
        "selectors": {...},
        "keywords": [...],
        "cron_expression": "..."
    }
    """
    # 构建 config
    config = {
        "source": {"url": body.source_url},
        "fields": {
            "list": body.selectors.get("list", ""),
            "title": body.selectors.get("title", ""),
            "link": body.selectors.get("link", ""),
            "summary": body.selectors.get("summary"),
        },
        "schedule": {
            "recommended": body.cron_expression,
        },
    }

    # 创建模板
    template = template_registry.create({
        "id": str(uuid.uuid4()),
        "name": body.name,
        "kind": "custom",
        "config": config,
        "status": "draft",
        "category": body.category,
        "tags": body.tags,
    })

    return template


@router.get("")
def list_sources(
    _: str = Depends(require_auth),
    kind: str | None = None,
):
    """列出所有模板"""
    templates = template_registry.list_all(kind=kind)
    return [t for t in templates]


@router.get("/{source_id}")
def get_source(
    source_id: str,
    _: str = Depends(require_auth),
):
    """获取模板详情"""
    template = template_registry.get(source_id)
    if not template:
        raise HTTPException(status_code=404, detail="Source not found")
    return template


# ── Template Marketplace / Sharing ────────────────────────────────


@router.post("/{source_id}/share")
def share_source(
    source_id: str,
    body: ShareRequest,
    _: str = Depends(require_auth),
):
    """
    分享模板到市场。

    输入: { "category": "developer", "tags": ["ai", "ml"] }
    """
    template = template_registry.get(source_id)
    if not template:
        raise HTTPException(status_code=404, detail="Source not found")

    # 更新分享状态
    category = body.category
    tags = body.tags
    template_registry.update(source_id, {
        "shared": True,
        "category": category,
        "tags": tags,
    })

    return {"status": "shared", "source_id": source_id}


@router.post("/{source_id}/unshare")
def unshare_source(
    source_id: str,
    _: str = Depends(require_auth),
):
    """取消分享模板"""
    template = template_registry.get(source_id)
    if not template:
        raise HTTPException(status_code=404, detail="Source not found")

    template_registry.update(source_id, {"shared": False})

    return {"status": "unshared", "source_id": source_id}


@router.get("/marketplace/list")
def list_marketplace(
    _: str = Depends(require_auth),
    category: str | None = None,
    sort: str = "popular",  # popular | recent | name
):
    """
    浏览市场中的共享模板。

    Args:
        category: 分类筛选
        sort: 排序方式 (popular | recent | name)
    """
    templates = template_registry.list_shared(category=category, sort=sort)
    return [t for t in templates]


@router.post("/{source_id}/import")
def import_source(
    source_id: str,
    body: CloneRequest,
    _: str = Depends(require_auth),
):
    """
    从市场导入模板。

    输入: { "name": "My Copy" }  // 可选自定义名称
    """
    template = template_registry.get(source_id)
    if not template:
        raise HTTPException(status_code=404, detail="Source not found")

    if not template.get("shared"):
        raise HTTPException(status_code=400, detail="Template is not shared")

    # 创建导入的副本
    new_id = str(uuid.uuid4())
    name = body.name or template.get("name", "Imported Template")

    imported = template_registry.create({
        "id": new_id,
        "name": name,
        "kind": "imported",
        "config": template.get("config", {}),
        "status": "draft",
        "category": template.get("category"),
        "tags": template.get("tags", []),
    })

    # 增加分享计数
    template_registry.increment_share_count(source_id)

    return imported


@router.post("/{source_id}/clone")
def clone_source(
    source_id: str,
    body: CloneRequest,
    _: str = Depends(require_auth),
):
    """
    克隆模板（创建可编辑副本）。

    输入: { "name": "My Clone" }
    """
    template = template_registry.get(source_id)
    if not template:
        raise HTTPException(status_code=404, detail="Source not found")

    new_id = str(uuid.uuid4())
    name = body.name or f"Copy of {template.get('name', 'Template')}"

    cloned = template_registry.create({
        "id": new_id,
        "name": name,
        "kind": "custom",
        "config": template.get("config", {}),
        "status": "draft",
        "category": template.get("category"),
        "tags": template.get("tags", []),
    })

    return cloned
