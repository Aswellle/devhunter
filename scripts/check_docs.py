#!/usr/bin/env python
"""
scripts/check_docs.py
文档数字与代码事实一致性检查（DOC-001）。

文档里能自动统计的数字不再靠人工维护：
- README 的预设模板数量与 backend/templates/sources.json 一致；
- schema 的 PRESET_TEMPLATES 与 sources.json 的 id 集合完全相等
  （历史坑：新增模板只进 JSON 不进 schema，任务创建会 400）；
- AGENTS.md 的迁移数量/编号、测试文件数量与仓库实际一致；
- api/router.py 保持 threads 在 items 之前注册（/items/{id} 通配符坑）。

用法：python scripts/check_docs.py   （CI 直接调用；失败 exit 1）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "backend" / "templates" / "sources.json"
SCHEMA = ROOT / "backend" / "app" / "schemas" / "task.py"
ROUTER = ROOT / "backend" / "app" / "api" / "router.py"
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"
MIGRATIONS = ROOT / "backend" / "migrations"
TESTS = ROOT / "backend" / "tests"

errors: list[str] = []


def check(label: str, ok: bool, detail: str) -> None:
    print(("PASS  " if ok else "FAIL  ") + label + (f"  [{detail}]" if detail else ""))
    if not ok:
        errors.append(f"{label}: {detail}")


def main() -> int:
    templates = json.loads(TEMPLATES.read_text(encoding="utf-8"))
    template_ids = {t["id"] for t in templates}
    check("sources.json 模板 id 唯一", len(template_ids) == len(templates),
          f"{len(templates)} 条 / {len(template_ids)} id")

    # PRESET_TEMPLATES 与 sources.json 必须完全一致
    schema_text = SCHEMA.read_text(encoding="utf-8")
    block = re.search(r"PRESET_TEMPLATES = \{(.*?)\n\}", schema_text, re.S)
    preset_ids = set(re.findall(r'"([a-z0-9_]+)"', block.group(1))) if block else set()
    check("PRESET_TEMPLATES 与 sources.json 一致",
          preset_ids == template_ids,
          f"schema-only={sorted(preset_ids - template_ids)} json-only={sorted(template_ids - preset_ids)}")

    # README 模板数量
    readme = README.read_text(encoding="utf-8")
    readme_counts = {int(n) for n in re.findall(r"(\d+) 个预设模板", readme)}
    check("README 预设模板数量与代码一致",
          readme_counts == {len(templates)},
          f"README={sorted(readme_counts)} actual={len(templates)}")

    # 迁移数量与编号
    migration_files = sorted(MIGRATIONS.glob("*.sql"))
    versions = [int(f.name.split("_")[0]) for f in migration_files]
    latest = max(versions) if versions else 0
    agents = AGENTS.read_text(encoding="utf-8")
    m = re.search(r"(\d+) 个纯 SQL 迁移文件（001–(\d+)）", agents)
    check("AGENTS 迁移数量与编号一致",
          bool(m) and int(m.group(1)) == len(migration_files) and int(m.group(2)) == latest,
          f"AGENTS={m.groups() if m else None} actual=({len(migration_files)}, {latest})")

    # 测试文件数量
    test_files = [
        f for f in TESTS.rglob("test_*.py")
        if "__pycache__" not in f.parts
    ]
    m2 = re.search(r"(\d+) 个测试文件", agents)
    check("AGENTS 测试文件数量一致",
          bool(m2) and int(m2.group(1)) == len(test_files),
          f"AGENTS={m2.group(1) if m2 else None} actual={len(test_files)}")

    # 路由顺序不变量
    router = ROUTER.read_text(encoding="utf-8")
    threads_pos = router.find("threads.router")
    items_pos = router.find("items.router")
    check("router 注册 threads 在 items 之前",
          0 <= threads_pos < items_pos,
          f"threads@{threads_pos} items@{items_pos}")

    # 新增能力必须有文档记录
    for token in ("github_connector", "reddit_connector", "notifications",
                  "opportunities", "opml", "GITHUB_TOKEN"):
        check(f"AGENTS 记录了 {token}", token in agents, "")

    if errors:
        print(f"\n{len(errors)} 项不一致：文档数字或清单与代码事实不符")
        return 1
    print("\n全部一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
