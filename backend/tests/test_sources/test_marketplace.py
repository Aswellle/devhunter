"""
tests/test_sources/test_marketplace.py
Template Marketplace / Sharing 单元测试
"""
import pytest
from app.sources.registry import template_registry


class TestTemplateMarketplace:
    """模板市场测试"""

    def test_create_and_share_template(self):
        """创建并分享模板"""
        # 创建模板
        tpl = template_registry.create({
            "id": "test_share_1",
            "name": "Test Share Template",
            "kind": "custom",
            "config": {"source": {"url": "https://example.com"}},
            "status": "draft",
        })
        assert tpl["id"] == "test_share_1"
        assert tpl["shared"] is False or tpl["shared"] == 0

        # 分享模板
        template_registry.update("test_share_1", {
            "shared": True,
            "category": "developer",
            "tags": ["test", "example"],
        })

        updated = template_registry.get("test_share_1")
        assert updated["shared"] is True or updated["shared"] == 1
        assert updated["category"] == "developer"

    def test_list_shared_templates(self):
        """列出共享模板"""
        # 创建并分享多个模板
        for i in range(3):
            tpl = template_registry.create({
                "id": f"test_market_{i}",
                "name": f"Market Template {i}",
                "kind": "custom",
                "config": {"source": {"url": f"https://example{i}.com"}},
            })
            template_registry.update(f"test_market_{i}", {
                "shared": True,
                "category": "test",
            })

        shared = template_registry.list_shared()
        assert len(shared) >= 3

    def test_list_shared_by_category(self):
        """按分类列出共享模板"""
        template_registry.create({
            "id": "test_cat_dev",
            "name": "Dev Template",
            "kind": "custom",
            "config": {},
        })
        template_registry.update("test_cat_dev", {
            "shared": True,
            "category": "developer",
        })

        template_registry.create({
            "id": "test_cat_ai",
            "name": "AI Template",
            "kind": "custom",
            "config": {},
        })
        template_registry.update("test_cat_ai", {
            "shared": True,
            "category": "ai",
        })

        dev_templates = template_registry.list_shared(category="developer")
        assert len(dev_templates) >= 1
        assert all(t["category"] == "developer" for t in dev_templates)

    def test_increment_share_count(self):
        """增加分享计数"""
        tpl = template_registry.create({
            "id": "test_count_1",
            "name": "Count Template",
            "kind": "custom",
            "config": {},
        })

        assert tpl["share_count"] == 0

        template_registry.increment_share_count("test_count_1")
        updated = template_registry.get("test_count_1")
        assert updated["share_count"] == 1

        template_registry.increment_share_count("test_count_1")
        updated = template_registry.get("test_count_1")
        assert updated["share_count"] == 2

    def test_import_template(self):
        """导入模板"""
        # 创建并分享源模板
        source = template_registry.create({
            "id": "test_import_source",
            "name": "Import Source",
            "kind": "custom",
            "config": {"source": {"url": "https://import-test.com"}},
        })
        template_registry.update("test_import_source", {"shared": True})

        # 导入
        imported = template_registry.create({
            "id": "test_imported",
            "name": "Imported Copy",
            "kind": "imported",
            "config": source["config"],
        })

        assert imported["id"] != source["id"]
        assert imported["kind"] == "imported"
        assert imported["config"] == source["config"]

    def test_unshare_template(self):
        """取消分享模板"""
        tpl = template_registry.create({
            "id": "test_unshare",
            "name": "Unshare Template",
            "kind": "custom",
            "config": {},
        })
        template_registry.update("test_unshare", {"shared": True})

        # 取消分享
        template_registry.update("test_unshare", {"shared": False})
        updated = template_registry.get("test_unshare")
        assert updated["shared"] is False or updated["shared"] == 0

        # 确认不在市场列表中
        shared = template_registry.list_shared()
        assert not any(t["id"] == "test_unshare" for t in shared)
