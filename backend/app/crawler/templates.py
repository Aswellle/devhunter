"""
app/crawler/templates.py
预设采集模板加载器 - 从 templates/sources.json 读取
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

TEMPLATES_FILE = Path(__file__).parent.parent.parent / "templates" / "sources.json"


@dataclass
class SourceTemplate:
    id: str
    name: str
    source_url: str
    selector_list: str
    selector_title: str
    selector_link: str
    selector_summary: str | None
    description: str
    default_keywords: list[str]
    recommended_cron: str
    category: str = ""
    subcategory: str = ""


_templates: dict[str, SourceTemplate] = {}


def _load_templates() -> dict[str, SourceTemplate]:
    if not TEMPLATES_FILE.exists():
        logger.warning("Templates file not found: %s", TEMPLATES_FILE)
        return {}
    data = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
    templates: dict[str, SourceTemplate] = {}
    required_fields = {"id", "name", "source_url", "selector_list", "selector_title", "selector_link"}
    for t in data:
        # 校验必填字段
        missing = required_fields - set(t.keys())
        if missing:
            logger.warning("Template skipped, missing required fields %s: %s", missing, t.get("id", "?"))
            continue
        try:
            templates[t["id"]] = SourceTemplate(**{k: t[k] for k in SourceTemplate.__dataclass_fields__ if k in t})
        except (TypeError, ValueError) as e:
            logger.warning("Template skipped, invalid data: %s (%s)", t.get("id", "?"), e)
            continue
    return templates



def get_template(template_id: str) -> SourceTemplate | None:
    global _templates
    if not _templates:
        _templates = _load_templates()
    return _templates.get(template_id)


def list_templates() -> list[SourceTemplate]:
    global _templates
    if not _templates:
        _templates = _load_templates()
    return list(_templates.values())


def apply_template(template_id: str, task_data: dict) -> dict:
    """
    将预设模板的字段合并到 task_data（用户数据优先）。
    若字段为空则从模板填充。
    """
    tpl = get_template(template_id)
    if not tpl:
        return task_data

    result = dict(task_data)
    result.setdefault("source_url", tpl.source_url)
    result.setdefault("selector_list", tpl.selector_list)
    result.setdefault("selector_title", tpl.selector_title)
    result.setdefault("selector_link", tpl.selector_link)
    if result.get("selector_summary") is None:
        result["selector_summary"] = tpl.selector_summary

    return result
