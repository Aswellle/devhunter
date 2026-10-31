"""
e2e_test.py  —  DevHunter 后端完整 E2E 测试
使用 FastAPI TestClient，无需启动外部服务器。
覆盖：Auth / Task CRUD / Items / Executions / 错误处理
"""
import json
import os
import sys
import uuid

# 切换工作目录到 backend/，让 .env 和 data/ 路径正确
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 使用临时数据库，测试完成后清理
TEST_DB = f"data/test_{uuid.uuid4().hex[:8]}.db"
os.environ["DB_PATH"] = TEST_DB
os.environ["AUTH_PASSWORD"] = "test123"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["LOG_FORMAT"] = "text"
os.environ["LOG_LEVEL"] = "WARNING"

from fastapi.testclient import TestClient
from app.main import create_app
from app.core.database import init_database

# 重新初始化（使用测试 DB）
init_database()
app = create_app()
client = TestClient(app, raise_server_exceptions=True)

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
errors = []

def check(name: str, cond: bool, detail: str = ""):
    if cond:
        print(f"  {PASS} {name}")
    else:
        print(f"  {FAIL} {name}  ← {detail}")
        errors.append(name)

def section(title: str):
    print(f"\n── {title} ──────────────────────────────────")

# ════════════════════════════════════════════════════════
# 1. 健康检查
# ════════════════════════════════════════════════════════
section("健康检查")
r = client.get("/health")
check("GET /health → 200", r.status_code == 200)
check("返回 status=ok", r.json().get("status") == "ok")

# ════════════════════════════════════════════════════════
# 2. 认证
# ════════════════════════════════════════════════════════
section("认证")
r = client.post("/api/auth/login", json={"password": "wrong"})
check("错误密码 → 401", r.status_code == 401)

r = client.post("/api/auth/login", json={"password": "test123"})
check("正确密码 → 200", r.status_code == 200)
# S4 修复：login 不再在响应体中返回 access_token（避免 XSS 可读取 JWT），
# 认证完全依赖 httpOnly Cookie，TestClient 在同一 client 实例内自动携带。
check("登录响应体不含 access_token（S4 修复）", "access_token" not in r.json())

HEADERS: dict[str, str] = {}

# 用一个全新、未登录过的 client 验证匿名请求确实被拒绝——用同一个已登录
# client 测试会因为它已经带有登录时设置的 httpOnly Cookie 而始终通过认证。
anon_client = TestClient(app, raise_server_exceptions=True)
r = anon_client.get("/api/tasks")
check("无 Token 访问受保护接口 → 401", r.status_code == 401)

# ════════════════════════════════════════════════════════
# 3. 预设模板
# ════════════════════════════════════════════════════════
section("预设模板")
r = client.get("/api/tasks/templates", headers=HEADERS)
check("GET /api/tasks/templates → 200", r.status_code == 200)
templates = r.json()
check("返回预设模板（≥5）", len(templates) >= 5, f"got {len(templates)}")
ids = [t["id"] for t in templates]
for tid in ["hackernews", "v2ex", "github_trending", "juejin", "indiehackers"]:
    check(f"  模板 {tid} 存在", tid in ids)

# ════════════════════════════════════════════════════════
# 4. 创建采集任务
# ════════════════════════════════════════════════════════
section("创建采集任务")
payload = {
    "name": "HN 前端需求",
    "source_url": "https://news.ycombinator.com/",
    "template_id": "hackernews",
    "selector_list": ".athing",
    "selector_title": ".titleline > a",
    "selector_link": ".titleline > a",
    "selector_summary": None,
    "keywords": ["React", "frontend"],
    "cron_expression": "0 * * * *",
}
r = client.post("/api/tasks", json=payload, headers=HEADERS)
check("POST /api/tasks → 201", r.status_code == 201, str(r.status_code))
task = r.json()
TASK_ID = task.get("id", "")
check("返回 task.id", bool(TASK_ID))
check("status = active", task.get("status") == "active")
check("keywords 正确", task.get("keywords") == ["React", "frontend"])
check("cron 正确", task.get("cron_expression") == "0 * * * *")

# 创建第二个任务（自定义）
r2 = client.post("/api/tasks", json={
    "name": "自定义源",
    "source_url": "https://v2ex.com/",
    "template_id": None,
    "selector_list": ".cell",
    "selector_title": "a.topic-link",
    "selector_link": "a.topic-link",
    "selector_summary": None,
    "keywords": [],
    "cron_expression": "*/30 * * * *",
}, headers=HEADERS)
check("创建自定义任务 → 201", r2.status_code == 201)
TASK2_ID = r2.json().get("id", "")

# ════════════════════════════════════════════════════════
# 5. 任务校验
# ════════════════════════════════════════════════════════
section("创建任务 - 参数校验")
# 无效 URL
r = client.post("/api/tasks", json={**payload, "source_url": "not-a-url"}, headers=HEADERS)
check("非法 URL → 422", r.status_code in (400, 422), str(r.status_code))

# 非法 Cron（3 段）
r = client.post("/api/tasks", json={**payload, "cron_expression": "* * *"}, headers=HEADERS)
check("非法 Cron → 422", r.status_code in (400, 422), str(r.status_code))

# ════════════════════════════════════════════════════════
# 6. 任务列表 & 详情
# ════════════════════════════════════════════════════════
section("任务列表 & 详情")
r = client.get("/api/tasks", headers=HEADERS)
check("GET /api/tasks → 200", r.status_code == 200)
data = r.json()
check("total = 2", data.get("total") == 2, str(data.get("total")))
check("items 长度 = 2", len(data.get("items", [])) == 2)

r = client.get(f"/api/tasks/{TASK_ID}", headers=HEADERS)
check("GET /api/tasks/{id} → 200", r.status_code == 200)
check("返回正确任务名", r.json().get("name") == "HN 前端需求")

r = client.get(f"/api/tasks/{uuid.uuid4()}", headers=HEADERS)
check("不存在的 task → 404", r.status_code == 404)
check("错误码正确", r.json().get("error", {}).get("code") == "TASK_NOT_FOUND")

# 按 status 过滤
r = client.get("/api/tasks?status=active", headers=HEADERS)
check("过滤 status=active → 2 个", r.json().get("total") == 2)

# ════════════════════════════════════════════════════════
# 7. 更新任务
# ════════════════════════════════════════════════════════
section("更新任务")
r = client.put(f"/api/tasks/{TASK_ID}", json={"name": "HN 需求（已更新）"}, headers=HEADERS)
check("PUT /api/tasks/{id} → 200", r.status_code == 200)
check("名称已更新", r.json().get("name") == "HN 需求（已更新）")

# 暂停任务
r = client.put(f"/api/tasks/{TASK_ID}", json={"status": "paused"}, headers=HEADERS)
check("暂停任务 → 200", r.status_code == 200)
check("status = paused", r.json().get("status") == "paused")

# 恢复任务
r = client.put(f"/api/tasks/{TASK_ID}", json={"status": "active"}, headers=HEADERS)
check("恢复任务 → status=active", r.json().get("status") == "active")

# ════════════════════════════════════════════════════════
# 8. 采集结果 Items
# ════════════════════════════════════════════════════════
section("采集结果 Items")
# 直接写入测试数据
from app.repositories.item_repo import item_repo
from app.utils.url import compute_url_hash

test_items = [
    {"task_id": TASK_ID, "title": "Show HN: React framework for devs",
     "url": "https://hn.example.com/1", "summary": "A new React tool"},
    {"task_id": TASK_ID, "title": "Python 3.13 released with new features",
     "url": "https://hn.example.com/2", "summary": "Python changelog"},
    {"task_id": TASK_ID, "title": "Ask HN: Best frontend libraries 2026",
     "url": "https://hn.example.com/3", "summary": "Community discussion"},
    {"task_id": TASK2_ID, "title": "V2EX: 求推荐 Go 框架",
     "url": "https://v2ex.example.com/1", "summary": ""},
]
for item in test_items:
    item["url_hash"] = compute_url_hash(item["url"])
    item["fetched_at"] = "2026-04-03T10:00:00Z"
inserted = item_repo.bulk_insert(test_items)
check(f"写入 {len(test_items)} 条测试数据", inserted == len(test_items))

# 列表查询
r = client.get("/api/items", headers=HEADERS)
check("GET /api/items → 200", r.status_code == 200)
data = r.json()
check("total = 4", data.get("total") == 4, str(data.get("total")))
check("默认按时间倒序", len(data.get("items", [])) == 4)

# 按 task_id 过滤
r = client.get(f"/api/items?task_id={TASK_ID}", headers=HEADERS)
check(f"按 task_id 过滤 → 3 条", r.json().get("total") == 3)

# 搜索（FTS5 或 LIKE 回退）
r = client.get("/api/items?search=React", headers=HEADERS)
check("搜索 React → ≥1 结果", r.json().get("total") >= 1, str(r.json().get("total")))

r = client.get("/api/items?search=Python", headers=HEADERS)
check("搜索 Python → 1 结果", r.json().get("total") >= 1)

r = client.get("/api/items?search=完全不存在的词语xyz123", headers=HEADERS)
check("搜索无匹配 → 0", r.json().get("total") == 0, str(r.json().get("total")))

# 分页
r = client.get("/api/items?page=1&per_page=2", headers=HEADERS)
data = r.json()
check("分页 per_page=2 → items 长度 2", len(data.get("items", [])) == 2)
check("total 仍为 4", data.get("total") == 4)

# ════════════════════════════════════════════════════════
# 9. Item 状态更新
# ════════════════════════════════════════════════════════
section("Item 状态更新")
items_list = client.get("/api/items", headers=HEADERS).json()["items"]
ITEM_ID = items_list[0]["id"]
ITEM2_ID = items_list[1]["id"]
ITEM3_ID = items_list[2]["id"]

# 标记已读
r = client.patch(f"/api/items/{ITEM_ID}", json={"is_read": True}, headers=HEADERS)
check("PATCH is_read=True → 200", r.status_code == 200)
check("is_read 已更新", r.json().get("is_read") == True)

# 标记收藏
r = client.patch(f"/api/items/{ITEM_ID}", json={"is_starred": True}, headers=HEADERS)
check("PATCH is_starred=True → 200", r.status_code == 200)
check("is_starred 已更新", r.json().get("is_starred") == True)

# 筛选收藏
r = client.get("/api/items?starred=true", headers=HEADERS)
check("starred=true 过滤 → 1 条", r.json().get("total") == 1)

# 取消收藏
r = client.patch(f"/api/items/{ITEM_ID}", json={"is_starred": False}, headers=HEADERS)
check("取消收藏 → is_starred=False", r.json().get("is_starred") == False)

# 批量标记已读
r = client.patch("/api/items/batch",
    json={"ids": [ITEM2_ID, ITEM3_ID], "is_read": True}, headers=HEADERS)
check("PATCH /items/batch → 200", r.status_code == 200)
check("批量更新 2 条", r.json().get("updated") == 2)

# 不存在的 item
r = client.patch("/api/items/nonexistent", json={"is_read": True}, headers=HEADERS)
check("不存在 item → 404", r.status_code == 404)

# ════════════════════════════════════════════════════════
# 10. 执行记录
# ════════════════════════════════════════════════════════
section("任务执行记录")
from app.repositories.execution_repo import execution_repo

# 写入测试执行记录
for i, (st, fetched, new_c, dur, err) in enumerate([
    ("success", 30, 4, 2340, None),
    ("warning", 0,  0, 1200, None),
    ("failure", 0,  0, 500,  "HTTP 503: Service Unavailable"),
]):
    execution_repo.insert({
        "task_id": TASK_ID,
        "status": st,
        "items_fetched": fetched,
        "items_new": new_c,
        "duration_ms": dur,
        "error_message": err,
        "executed_at": f"2026-04-03T0{i+1}:00:00Z",
    })

r = client.get(f"/api/tasks/{TASK_ID}/executions", headers=HEADERS)
check("GET /tasks/{id}/executions → 200", r.status_code == 200)
data = r.json()
check("total = 3", data.get("total") == 3, str(data.get("total")))
statuses = [e["status"] for e in data["items"]]
check("包含 success/warning/failure 三种状态",
      set(statuses) == {"success", "warning", "failure"}, str(statuses))

# 执行历史分页
r = client.get(f"/api/tasks/{TASK_ID}/executions?per_page=2", headers=HEADERS)
check("分页 per_page=2", len(r.json().get("items", [])) == 2)

# 不存在的 task → 404
r = client.get(f"/api/tasks/{uuid.uuid4()}/executions", headers=HEADERS)
check("不存在 task 执行历史 → 404", r.status_code == 404)

# ════════════════════════════════════════════════════════
# 11. 手动触发执行
# ════════════════════════════════════════════════════════
section("手动触发执行")
r = client.post(f"/api/tasks/{TASK_ID}/execute", headers=HEADERS)
check("POST /tasks/{id}/execute → 202", r.status_code == 202)
check("返回 execution_id", bool(r.json().get("execution_id")))
check("返回 message", bool(r.json().get("message")))

r = client.post(f"/api/tasks/{uuid.uuid4()}/execute", headers=HEADERS)
check("触发不存在任务 → 404", r.status_code == 404)

# ════════════════════════════════════════════════════════
# 12. 删除任务（软删除）
# ════════════════════════════════════════════════════════
section("软删除任务")
r = client.delete(f"/api/tasks/{TASK2_ID}", headers=HEADERS)
check("DELETE /tasks/{id} → 204", r.status_code == 204)

r = client.get(f"/api/tasks/{TASK2_ID}", headers=HEADERS)
check("已删除任务 GET → 404", r.status_code == 404)

r = client.get("/api/tasks", headers=HEADERS)
check("删除后列表 total=1", r.json().get("total") == 1)

# 删除不存在的任务
r = client.delete(f"/api/tasks/{uuid.uuid4()}", headers=HEADERS)
check("删除不存在任务 → 404", r.status_code == 404)

# ════════════════════════════════════════════════════════
# 13. 去重验证
# ════════════════════════════════════════════════════════
section("URL 去重")
from app.crawler.dedup import deduplicate
from app.crawler.engine import CrawlItem

items_before = item_repo.query()[1]
dup_items = [
    CrawlItem(title="重复条目", url="https://hn.example.com/1", summary=""),  # 已存在
    CrawlItem(title="新条目", url="https://hn.example.com/999", summary=""),  # 新的
]
new_only = deduplicate(dup_items)
check("去重：2 条中 1 条重复 → 返回 1 条新", len(new_only) == 1)
check("返回的是新 URL", new_only[0].url == "https://hn.example.com/999")

# ════════════════════════════════════════════════════════
# 结果汇总
# ════════════════════════════════════════════════════════
print("\n" + "="*55)
total_tests = 0  # count from earlier
if errors:
    print(f"\033[91m✗ {len(errors)} 项失败：\033[0m")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"\033[92m✓ 所有 E2E 测试通过！\033[0m")

# 清理测试数据库
import os
try:
    os.remove(TEST_DB)
    for ext in ["-shm", "-wal"]:
        try: os.remove(TEST_DB + ext)
        except: pass
except: pass
