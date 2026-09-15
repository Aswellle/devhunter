"""
tests/test_sources/test_registry.py
Template Registry 单元测试
"""
import json
import pytest
from app.sources.registry import template_registry


class TestSourceTemplateRegistry:
    """Template Registry CRUD 测试"""

    def test_create_and_get(self):
        """创建模板并获取"""
        tpl = template_registry.create({
            "id": "test_tpl_1",
            "name": "Test Template",
            "kind": "preset",
            "config": {
                "source": {"url": "https://example.com"},
                "fields": {"list": ".item", "title": "h2", "link": "a"},
            },
        })
        assert tpl["id"] == "test_tpl_1"
        assert tpl["name"] == "Test Template"
        assert tpl["config"]["source"]["url"] == "https://example.com"

        fetched = template_registry.get("test_tpl_1")
        assert fetched is not None
        assert fetched["id"] == "test_tpl_1"

    def test_list_all(self):
        """列出所有模板"""
        template_registry.create({
            "id": "test_tpl_2",
            "name": "Test Template 2",
            "kind": "custom",
            "config": {},
        })
        templates = template_registry.list_all()
        assert len(templates) >= 2

    def test_exists(self):
        """检查模板是否存在"""
        assert template_registry.exists("test_tpl_1") is True
        assert template_registry.exists("nonexistent") is False

    def test_update_health(self):
        """更新健康状态"""
        template_registry.update_health("test_tpl_1", 85.5, "healthy")
        tpl = template_registry.get("test_tpl_1")
        assert tpl["health_score"] == 85.5
        assert tpl["status"] == "healthy"

    def test_apply_to_task(self):
        """应用模板到任务数据"""
        task_data = {
            "name": "My Task",
            "source_url": "",
            "selector_list": "",
            "selector_title": "",
            "selector_link": "",
        }
        result = template_registry.apply_to_task("test_tpl_1", task_data)
        assert result["source_url"] == "https://example.com"
        assert result["selector_list"] == ".item"
        assert result["template_id"] == "test_tpl_1"

    def test_delete(self):
        """删除模板"""
        assert template_registry.delete("test_tpl_2") is True
        assert template_registry.exists("test_tpl_2") is False
