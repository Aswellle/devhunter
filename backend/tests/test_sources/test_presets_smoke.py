"""
tests/test_sources/test_presets_smoke.py
Preset Smoke Tests：验证所有预设模板配置完整性。

每个 preset 必须包含：
- 有效的 source_url
- 非空的 selector_list
- 非空的 selector_title
- 非空的 selector_link
- 有效的 recommended_cron
"""
import json
from pathlib import Path

import pytest

from app.crawler.templates import SourceTemplate, get_template, list_templates


class TestPresetSmoke:
    """Preset 模板冒烟测试"""

    def test_all_presets_have_required_fields(self):
        """所有预设模板必须包含必填字段"""
        templates = list_templates()
        assert len(templates) > 0, "No preset templates found"

        required_fields = ["id", "name", "source_url", "selector_list", "selector_title", "selector_link"]
        for tpl in templates:
            for field in required_fields:
                assert getattr(tpl, field, None), f"Template {tpl.id} missing {field}"

    def test_all_presets_have_valid_urls(self):
        """所有预设模板的 source_url 必须是有效 URL"""
        from app.utils.url import is_valid_url
        templates = list_templates()
        for tpl in templates:
            assert is_valid_url(tpl.source_url), f"Template {tpl.id} has invalid URL: {tpl.source_url}"

    def test_all_presets_have_valid_cron(self):
        """所有预设模板必须有有效的 cron 表达式"""
        templates = list_templates()
        for tpl in templates:
            assert tpl.recommended_cron, f"Template {tpl.id} missing recommended_cron"
            # 基本格式检查：5 段
            parts = tpl.recommended_cron.split()
            assert len(parts) == 5, f"Template {tpl.id} cron must have 5 fields: {tpl.recommended_cron}"

    def test_preset_ids_are_unique(self):
        """预设模板 ID 必须唯一"""
        templates = list_templates()
        ids = [tpl.id for tpl in templates]
        assert len(ids) == len(set(ids)), f"Duplicate preset IDs: {ids}"

    def test_get_template_by_id(self):
        """通过 ID 获取模板"""
        templates = list_templates()
        if templates:
            tpl = get_template(templates[0].id)
            assert tpl is not None
            assert tpl.id == templates[0].id

    def test_get_template_not_found(self):
        """不存在的模板 ID → 返回 None"""
        tpl = get_template("nonexistent_template_id")
        assert tpl is None

    def test_sources_json_exists(self):
        """sources.json 文件必须存在"""
        templates_file = Path(__file__).parent.parent.parent / "templates" / "sources.json"
        assert templates_file.exists(), f"Templates file not found: {templates_file}"

    def test_sources_json_valid(self):
        """sources.json 必须是有效的 JSON 数组"""
        templates_file = Path(__file__).parent.parent.parent / "templates" / "sources.json"
        data = json.loads(templates_file.read_text(encoding="utf-8"))
        assert isinstance(data, list), "sources.json must be a JSON array"
        assert len(data) > 0, "sources.json must not be empty"


class TestTemplatePagination:
    def test_template_accepts_optional_next_page_selector(self):
        """模板 schema 支持可选分页配置：带 selector_next_page 的模板
        不再被加载器丢弃，字段进入 API 响应供创建任务透传。"""
        template = SourceTemplate(
            id="tpl-pagination",
            name="分页模板",
            source_url="https://example.com/list",
            selector_list=".item",
            selector_title="h2",
            selector_link="a",
            selector_summary=None,
            description="d",
            default_keywords=[],
            recommended_cron="0 9 * * *",
            selector_next_page="a.next",
        )
        assert template.selector_next_page == "a.next"

    def test_templates_api_exposes_next_page_field(self):
        """/api/tasks/templates 响应携带 selector_next_page，模板市场
        创建任务时才能把分页配置带进 Task。"""
        from fastapi.testclient import TestClient

        from app.core.security import create_access_token
        from app.main import app

        client = TestClient(app)
        token = create_access_token({"sub": "admin"})
        resp = client.get("/api/tasks/templates",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload, "预设模板不应为空"
        assert all("selector_next_page" in t for t in payload)
