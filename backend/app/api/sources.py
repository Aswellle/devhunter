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

from app.api.deps import require_auth
from app.sources.discovery import url_discoverer, DiscoveryResult
from app.sources.preview import preview_extractor
from app.sources.tester import config_tester
from app.sources.registry import template_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["sources"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.post("/discover")
def discover_source(
    body: dict,
    _: str = Depends(require_auth),
):
    """
    Step 1: URL 自动发现。

    输入: { "url": "https://example.com" }
    输出: DiscoveryResult JSON
    """
    url = body.get("url", "")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    result = url_discoverer.discover(url)
    return result.to_dict()


@router.post("/preview")
def preview_source(
    body: dict,
    _: str = Depends(require_auth),
):
    """
    Step 2: 预览提取。

    输入: { "url": "...", "discovery_result": {...} }
    输出: PreviewResult JSON
    """
    url = body.get("url", "")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    discovery_data = body.get("discovery_result")
    discovery_result = None
    if discovery_data:
        discovery_result = DiscoveryResult(**discovery_data)

    result = preview_extractor.preview(url, discovery_result)
    return result.to_dict()


@router.post("/test")
def test_source(
    body: dict,
    _: str = Depends(require_auth),
):
    """
    Step 3: 测试配置。

    输入: { "url": "...", "selectors": {...}, "expected_min_items": 5 }
    输出: TestResult JSON
    """
    url = body.get("url", "")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    selectors = body.get("selectors", {})
    expected_min_items = body.get("expected_min_items", 1)
    required_fields = body.get("required_fields", ["title", "link"])

    result = config_tester.test(url, selectors, expected_min_items, required_fields)
    return result.to_dict()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_source(
    body: dict,
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
    name = body.get("name", "")
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    source_url = body.get("source_url", "")
    if not source_url:
        raise HTTPException(status_code=400, detail="source_url is required")

    selectors = body.get("selectors", {})
    keywords = body.get("keywords", [])
    cron_expression = body.get("cron_expression", "0 9 * * *")

    # 构建 config
    config = {
        "source": {"url": source_url},
        "fields": {
            "list": selectors.get("list", ""),
            "title": selectors.get("title", ""),
            "link": selectors.get("link", ""),
            "summary": selectors.get("summary"),
        },
        "schedule": {
            "recommended": cron_expression,
        },
    }

    # 创建模板
    template = template_registry.create({
        "id": str(uuid.uuid4()),
        "name": name,
        "kind": "custom",
        "config": config,
        "status": "draft",
        "category": body.get("category"),
        "tags": body.get("tags", []),
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
    body: dict,
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
    category = body.get("category")
    tags = body.get("tags", [])
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
    body: dict,
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
    name = body.get("name", template.get("name", "Imported Template"))

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
    body: dict,
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
    name = body.get("name", f"Copy of {template.get('name', 'Template')}")

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
