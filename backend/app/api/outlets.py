"""
app/api/outlets.py
机器可读出口（Machine Outlets）：面向 RSS 阅读器、LLM Agent 与外部工具的只读端点。

- GET /api/llms.txt   公开：llms.txt 站点能力说明（llmstxt.org 规范）
  （RSS 与后续 MCP 出口陆续在此模块扩展）
"""
from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter(tags=["outlets"])

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
