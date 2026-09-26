# Repository Guidelines

DevHunter 是一个自托管的内容聚合系统，自动从 28+ 开发者平台（Hacker News、V2EX、GitHub Trending、Indie Hackers 等）爬取内容，将跨平台事件聚合为 Thread，并提供个性化推荐——全部支持定时执行和全文搜索。

## 项目概述

**核心目标：** 配置一次爬取任务（URL + 选择器/JSON 路径 + 关键词 + Cron），DevHunter 按计划自动抓取、去重、存储、索引——替代手动浏览数十个网站。

**关键能力：**
- **Thread V2** — 多因素跨平台事件聚类（词法 + 实体 + 语义 + 时间 + 来源）
- **Recommendation V2** — 候选生成 → 多因子评分 → 多样性处理 → 可解释推荐
- **3 步模板向导** — URL → 自动发现 → 预览（无需 CSS 选择器知识）
- **模板市场** — 分享和导入社区爬取模板

**技术栈：**
- 后端：Python 3.11+、FastAPI、APScheduler、SQLAlchemy、SQLite（WAL + FTS5）、httpx、BeautifulSoup4
- 前端：React 19、Vite、TypeScript、react-router-dom v7、TanStack Query、Zustand、Tailwind CSS v3、axios
- 部署：Docker Compose、Nginx

---

## 架构与数据流

### 请求生命周期
```
客户端 → API 路由 (api/) → 服务层 (services/) → 仓储层 (repositories/) → SQLite
                                                                         ↑
                                                          迁移文件 (migrations/)
```

### 爬取执行流程
```
调度器 (scheduler/) → 执行任务 → 爬取引擎 (crawler/) → 条目入库
                                ↓                                       ↓
                        EventBus (SSE) ←←←←←←←←←←←←            Thread 计算
                                ↓                                       ↓
                        前端 (useTaskEventStream)           推荐引擎
```

### 调度器架构
- APScheduler `BackgroundScheduler` 运行在**独立线程**中，与 FastAPI 的 async 循环隔离
- 使用 `SQLAlchemyJobStore`，与业务数据共用同一个 SQLite 数据库
- `restore_jobs()` 清空 JobStore 并从 DB 重新加载所有活跃任务——**数据库是唯一真相源**
- 工作任务持有进程内重入锁（`_running_tasks` 字典）强制 `max_instances=1`
- Cron 触发器为 5 字段，在 **UTC** 下求值
- 手动触发使用独立的 job ID（`f"{task_id}_manual"`），避免覆盖 CronTrigger

### 爬取引擎解析模式
- **HTML**（无前缀）— CSS 选择器 via BeautifulSoup4
- **json:\<path\>** — JSON API GET，点分隔路径
- **json-post:\<path\>\|\|\|\<body\>** — JSON API POST
- **rss:** — RSS 2.0 / Atom 订阅源解析

### 实时事件
- `EventBus` 单例通过 SSE 发布任务执行进度
- 前端通过 `/api/tasks/{task_id}/events` 使用 `fetch` + `ReadableStream` 订阅（非 `EventSource`，以携带凭证）
- 事件同时持久化到 `execution_events` 表，支持通过 `Last-Event-ID` 游标重放
- 事件类型：`step_init`、`fetch_*`、`parse_*`、`filter_*`、`dedup_*`、`save_*`、`thread_*`、`items_preview`、`success`/`failure`/`warning`

### 认证模型
- 单用户 JWT（HS256，7 天有效期），通过 **httpOnly cookie**（`devhunter_token`）传递
- `require_auth` 先读 Bearer header，回退到 cookie
- 前端绝不接触 JWT——仅在 localStorage 存储 `devhunter_auth='1'` 布尔标记
- 登录速率限制（5 次/分钟），5 分钟内 5 次失败后账户锁定

---

## 关键目录

```
devhunter/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI 路由处理器（10 个模块）
│   │   │   ├── deps.py     # require_auth 依赖注入
│   │   │   └── router.py   # 中央 /api 路由器；threads 必须在 items 之前注册
│   │   ├── core/           # 配置、数据库、安全、日志、event_bus、http_client、exceptions、rate_limit
│   │   ├── services/       # 业务逻辑（task、item、execution、thread、recommendation）
│   │   ├── repositories/   # 数据访问层（6 个仓储）
│   │   ├── schemas/        # Pydantic 请求/响应模型
│   │   ├── crawler/        # HTTP 抓取 + 解析引擎（engine、dedup、templates）
│   │   ├── sources/        # 模板注册、发现、预览、验证、健康、市场
│   │   ├── threads/        # 聚类、评分、合并、拆分
│   │   ├── recommendation/ # 候选、评分、排序、多样性、解释、画像、适配器
│   │   ├── scheduler/      # APScheduler 管理器、任务、清理
│   │   ├── execution/      # 执行状态机
│   │   ├── features/       # 实体提取、语义相似度、时间特征
│   │   └── utils/          # 哈希、URL、相似度工具
│   ├── migrations/         # 18 个纯 SQL 迁移文件（001–018）
│   ├── templates/          # 预设爬取模板（JSON）
│   ├── tests/              # 26 个测试文件，跨 8 个领域模块 + 1 个空目录 + 1 个独立 E2E 脚本
│   ├── run.py              # 本地开发入口
│   ├── e2e_test.py         # 独立 E2E 测试（自包含，使用临时 DB）
│   └── pyproject.toml      # pytest 配置、依赖
├── frontend/
│   └── src/
│       ├── pages/          # 8 个页面（Dashboard、Tasks、Items、Starred、Cloud、Recommend、Profile、Login）
│       ├── components/     # layout/、items/、tasks/、dashboard/、ui/
│       ├── api/            # axios 客户端 + 每领域封装
│       ├── stores/         # Zustand（仅 authStore）
│       ├── hooks/          # useTaskEventStream、useOptimisticMutation、useModalA11y
│       ├── types/          # 共享 TypeScript 接口
│       └── utils/          # 时间格式化
├── docs/                   # 架构文档、审计报告（已 gitignore）
├── docker-compose.yml      # 生产：backend + frontend/nginx
├── docker-compose.dev.yml  # 开发覆盖：backend 端口 8001、调试模式
└── start.bat               # Windows 一键启动
```

---

## 开发命令

### 后端
```bash
cd backend
pip install -r requirements.txt        # 安装依赖（或使用 pip install -e .[dev]）
python run.py                          # 启动开发服务器（http://localhost:8000）
pytest                                 # 运行完整测试套件
pytest tests/test_crawler/test_retry.py              # 单文件
pytest -k test_404_is_terminal_no_retry              # 按名称
python e2e_test.py                     # E2E 测试（自包含，使用临时 DB）
```

### 前端
```bash
cd frontend
npm install                            # 安装依赖
npm run dev                            # 启动开发服务器（http://localhost:5200）
npm run build                          # 生产构建（tsc -b && vite build）
npm run lint                           # ESLint
```

### Docker
```bash
docker compose up -d                   # 生产（frontend :80，backend 内部）
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d  # 开发（backend :8001）
docker compose logs -f backend         # 查看后端日志
```

### Windows
```bash
start.bat                              # 一键启动：backend（:8000）+ frontend（:5200）
```

---

## 代码规范与通用模式

### 后端模式
- **错误处理：** `crawler/engine.py` 绝不抛出异常——所有错误通过 `CrawlResult.error` 返回。API 错误使用 `DevHunterError` 层级（含 `status_code` + `error_code`）。所有错误返回 `{"error": {"code": ..., "message": ...}}`。
- **依赖注入：** `deps.py` 提供 `require_auth()`。服务层通过构造函数注入接收仓储。
- **数据库访问：** `get_db()` 上下文管理器自动 commit/rollback。`transaction()` 用于跨仓储原子性。SQLite WAL 模式，`busy_timeout=5000`，`foreign_keys=ON`。
- **迁移：** 纯 SQL 文件通过 `init_database()` 在启动时应用。使用幂等 `ALTER TABLE ADD COLUMN`——永不破坏性变更。触发器感知的 SQL 拆分器正确处理 `BEGIN...END` 块。
- **单例模式：** `scheduler_manager`、`event_bus`、`settings`（lru_cache）、`get_http_client()`。所有仓储/服务导出单一实例。
- **SSRF 防护：** 爬取引擎在 HTTP 调用前阻止私有/环回/链路本地 IP。DNS 解析失败时 **fail-closed**。`follow_redirects=False`——每个跳转手动重新验证 SSRF。
- **去重：** 三层去重——(1) `external_id` 按任务，(2) `url_hash` 全局，(3) `content_hash`（title+summary 的 SHA256）。
- **日志：** 结构化 JSON 日志，`RequestIdFilter` 从 contextvars 注入 `request_id`。

### 前端模式
- **状态管理：** TanStack Query 管理服务端状态（`staleTime: 30s`、`retry: 1`）。Zustand 仅用于认证布尔标记。React useState 用于 UI 状态。`useSearchParams` 用于 URL 同步状态（筛选器、视图模式、标签页）。
- **API 客户端：** 共享 axios 实例（`baseURL: '/api'`、`withCredentials: true`、30s 超时）。401 拦截器分发 `devhunter:auth-expired` 事件。网络/5xx 错误自动重试（最多 2 次）。
- **路由：** `react-router-dom` v7 配合 `BrowserRouter`。`AuthGuard` 重定向到 `/login`。`AuthExpiredHandler` 监听 auth-expired 事件。
- **SSE 事件：** `useTaskEventStream` 通过 `fetch` + `ReadableStream` 映射原始事件到步骤状态机（`init→fetch→parse→filter→dedup→save`），含重连/退避（5 次重试，1s→30s）。Caps events at 500。
- **模态框：** `createPortal` 到 document.body（避免 overflow:hidden 裁剪）。`ConfirmDialog` 使用原生 `<dialog>`。`useModalA11y` 共享焦点陷阱 + aria-hidden。
- **查询键：** 全部通过 `queryKeys.*` 工厂函数——从不使用原始字面量。

### 命名规范
- 后端：模块/函数/变量用 `snake_case`，类用 `PascalCase`，常量用 `UPPER_SNAKE`
- 前端：组件/页面用 `PascalCase`，函数/变量用 `camelCase`，hooks 用 `use*` 前缀
- API 路由：`/api` 前缀下 RESTful 风格，复数名词（`/tasks`、`/items`、`/threads`）
- 数据库表：复数 `snake_case`（`tasks`、`items`、`thread_items`、`user_interactions`）

---

## 关键文件

| 文件 | 用途 |
|------|------|
| `backend/app/main.py` | FastAPI 应用工厂、生命周期、中间件、错误处理器 |
| `backend/app/run.py` | 本地开发入口（uvicorn） |
| `backend/app/api/router.py` | 中央 API 路由器，挂载 9 个子路由器 |
| `backend/app/core/config.py` | Pydantic-settings 配置 |
| `backend/app/core/database.py` | SQLite 连接、迁移、事务 |
| `backend/app/core/security.py` | JWT 创建/验证、密码校验 |
| `backend/app/core/event_bus.py` | 线程安全 SSE 事件广播器 |
| `backend/app/core/http_client.py` | 共享 httpx 客户端（Chrome 指纹 headers） |
| `backend/app/core/exceptions.py` | DevHunterError 层级 |
| `backend/app/core/rate_limit.py` | Slowapi 速率限制器单例 |
| `backend/app/crawler/engine.py` | 核心爬取引擎（4 种解析模式、SSRF、重试、分页） |
| `backend/app/crawler/dedup.py` | 三层去重 |
| `backend/app/scheduler/manager.py` | APScheduler 包装器，DB 同步 |
| `backend/app/scheduler/jobs.py` | 任务执行、重入锁、事件发布 |
| `backend/app/threads/clustering.py` | Thread 聚类算法 v2 |
| `backend/app/threads/scoring.py` | 五因子 Thread 评分 |
| `backend/app/recommendation/` | 完整推荐管线（候选→评分→排序→多样性→解释） |
| `frontend/src/App.tsx` | 根组件、路由、认证守卫 |
| `frontend/src/api/client.ts` | 共享 axios 客户端 + 拦截器 |
| `frontend/src/hooks/useTaskEventStream.ts` | SSE 事件消费 hook |
| `frontend/src/stores/authStore.ts` | Zustand 认证标记 |
| `frontend/src/types/index.ts` | 共享 TypeScript 接口 |
| `frontend/vite.config.ts` | Vite 配置、开发代理到 backend |
| `docker-compose.yml` | 生产容器编排 |

---

## 运行时与工具链偏好

- **Python：** 需要 3.11+。本地开发使用 `venv`。依赖在 `requirements.txt` 中固定版本。
- **Node：** 前端使用 npm（非 Bun/pnpm）。Vite 用于开发服务器和构建。
- **包管理器：** 后端用 `pip`，前端用 `npm`。
- **无 monorepo 工具：** 后端和前端是独立项目，分别管理依赖。
- **数据库：** 仅 SQLite（无 PostgreSQL/MySQL）。WAL 模式启用。FTS5 用于全文搜索。
- **无 ORM 迁移工具：** 纯 SQL 文件，非 Alembic。
- **前端端口：** 开发服务器在 **5200**（非 Vite 默认的 5173）。代理目标为 `127.0.0.1:8100`（必须与后端实际端口匹配）。
- **无后端 linter/formatter 配置**（无 ruff/black）——遵循现有代码风格。

---

## 测试与 QA

### 后端测试
- **框架：** pytest + `pytest-asyncio`（asyncio_mode = "auto"）、`pytest-cov`
- **配置：** `pyproject.toml` — `testpaths = ["tests"]`
- **测试金字塔三层：**
  - **纯单元测试** — 领域逻辑（评分、排序、状态机、相似度）——无 DB、无 I/O、完全确定性
  - **服务/仓储集成测试** — 使用共享的 session 级 SQLite 测试 DB 并应用迁移
  - **API 测试** — 通过 FastAPI `TestClient` 覆盖完整 ASGI 栈
- **Fixture：** `backend/tests/conftest.py` — session 级临时 SQLite DB 带迁移，autouse monkeypatch 覆盖 `config.settings.db_path`
- **组织：** 26 个测试文件，8 个领域模块：`test_api/`、`test_crawler/`、`test_recommendation/`、`test_sources/`、`test_features/`、`test_threads/`、`test_services/`、`test_execution/`
- **模式：**
  - API 测试使用 FastAPI `TestClient` + `_auth_headers()` Bearer token 辅助函数
  - 爬取器测试使用 `_FakeResponse` + `_ScriptedClient`（脚本化响应序列 + `.calls` 计数器）
  - 模块属性使用 `monkeypatch`（如 `engine.time.sleep`、`_is_ssrf_safe_url`）
  - 服务测试使用 `unittest.mock.patch` 隔离仓储单例
  - 类分组：`Test*API`、`Test*Service` 等
  - 中文 docstring 保持一致
- **无前端测试：** 前端尚无测试基础设施。
- **无 CI 流水线：** 无 `.github/workflows` 或类似配置。
- **覆盖率：** `pytest-cov` 可用但无 coverage config 或阈值定义。

### 运行测试
```bash
pytest                              # 完整套件
pytest tests/test_crawler/          # 单模块
pytest -k "test_name"               # 按名称
pytest --cov=app --cov-report=term  # 带覆盖率
python e2e_test.py                  # 独立 E2E（必须从 backend/ 目录运行）
```

### 测试覆盖情况
- **覆盖良好：** test_crawler（11 个测试）、test_recommendation（30+）、test_threads/test_scoring（11）、test_execution（4）、test_sources（30+ 跨 7 个文件）、test_features（11）、test_api（6）
- **覆盖较少：** test_sources/test_preview、test_tester、test_discovery（仅序列化）；test_recommendation/test_candidates（仅形状）；test_services（仅空/限制）
- **空白：** `test_repositories/`（0 个测试——整个仓储层无覆盖）

---

## 环境变量

全部由 `pydantic-settings` 从 `.env` 读取（大小写不敏感，`extra="ignore"`）。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_ENV` | `development` | `development` / `production` |
| `APP_HOST` | `0.0.0.0` | 绑定主机 |
| `APP_PORT` | `8000` | 绑定端口 |
| `AUTH_PASSWORD` | *(占位符)* | 登录密码（明文比较） |
| `AUTH_USERNAME` | `admin` | JWT 主题 / 显示名 |
| `SECRET_KEY` | *(占位符)* | JWT 签名密钥（检测到默认值时自动生成） |
| `JWT_EXPIRE_MINUTES` | `10080` | Token 有效期（7 天） |
| `DB_PATH` | `data/devhunter.db` | SQLite 路径 |
| `CRAWLER_TIMEOUT` | `15.0` | HTTP 超时（秒） |
| `CRAWLER_MAX_RESPONSE_MB` | `5` | 响应体大小上限 |
| `SCHEDULER_MAX_WORKERS` | `3` | 并行爬取任务数 |
| `SCHEDULER_MISFIRE_GRACE_TIME` | `300` | APScheduler misfire grace（秒） |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `LOG_FORMAT` | `json` | `json` 或 `text` |
| `CORS_ORIGINS` | `http://localhost:5173,...` | 逗号分隔的允许来源 |

**安全注意：** 生产环境启动调用 `validate_production_secrets()`，拒绝占位符值。使用 `openssl rand -hex 32` 生成。

---

## 数据库 Schema

SQLite，WAL 模式。关键表：

| 表 | 用途 |
|----|------|
| `tasks` | 爬取任务配置（含 `selector_next_page` 分页、`deleted_at` 软删除） |
| `items` | 爬取内容条目 |
| `items_fts` | FTS5 虚拟表，全文搜索 |
| `task_executions` | 执行历史和状态 |
| `execution_events` | 细粒度执行事件日志（SSE 源） |
| `threads` | 跨平台事件聚类 |
| `thread_items` | M:N 关联，含相似度评分 |
| `user_topics` | 用户定义的关注主题 |
| `user_interactions` | 行为追踪（view/click/dwell/star/share） |
| `user_topic_affinity` | 计算的主题亲和度分数 |
| `recommendation_config` | 推荐算法配置 |
| `source_templates` | 爬取模板存储（预设 + 自定义） |

---

## API 端点

全部在 `/api` 前缀下。除 `/auth/login` 和 `/health` 外均需认证。

| 端点 | 方法 | 用途 |
|------|------|------|
| `/auth/login` | POST | 登录（速率限制，设置 httpOnly cookie） |
| `/auth/logout` | POST | 登出 |
| `/tasks` | GET/POST | 列出/创建爬取任务 |
| `/tasks/{id}` | GET/PATCH/DELETE | 任务 CRUD |
| `/tasks/{id}/trigger` | POST | 手动执行触发（202） |
| `/tasks/{id}/events` | GET | SSE 事件流 |
| `/tasks/{id}/executions` | GET | 执行历史 |
| `/items` | GET | 列出条目（分页、FTS 搜索、过滤） |
| `/items/{id}` | GET/PATCH/DELETE | 条目 CRUD |
| `/items/batch` | PATCH | 批量更新（已读/收藏） |
| `/items/batch` | DELETE | 批量删除（速率限制） |
| `/items/threads` | GET | Thread 列表（分页） |
| `/items/threads/{id}` | GET | Thread 详情含条目 |
| `/sources/discover` | POST | 自动发现来源结构 |
| `/sources/preview` | POST | 预览爬取结果 |
| `/sources/test` | POST | 测试爬取配置 |
| `/sources` | GET/POST | 模板 CRUD |
| `/sources/marketplace/list` | GET | 列出共享模板 |
| `/sources/marketplace/share` | POST | 分享模板 |
| `/sources/marketplace/import` | POST | 导入共享模板 |
| `/stats` | GET | 仪表盘概览 |
| `/recommendations` | GET | 个性化推荐 |
| `/topics` | GET/POST | 用户主题管理 |
| `/topics/recommended` | GET | 推荐主题 |
| `/interactions` | POST | 记录用户交互 |
| `/health` | GET | 健康检查 |

---

## 添加功能指南

### 添加后端功能
1. 在 `schemas/` 添加 Pydantic schema
2. 如需新数据访问，在 `repositories/` 添加仓储方法
3. 在 `services/` 添加服务逻辑
4. 在 `api/` 添加 API 路由
5. 在 `api/router.py` 注册路由
6. 如变更 schema，在 `migrations/` 添加 SQL 迁移
7. 在 `tests/` 添加 pytest 测试

### 添加前端功能
1. 在 `types/index.ts` 添加类型
2. 在 `api/` 添加 API 封装
3. 在 `pages/` 或 `components/` 添加页面/组件
4. 在 `App.tsx` 注册路由
5. 接入 TanStack Query 管理服务端状态

### 修改爬取器
- 永远不要从 `crawler/engine.py` 抛出异常——通过 `CrawlResult.error` 返回错误
- 维护 SSRF 防护（私有 IP 阻止）
- 遵守 `CRAWLER_MAX_RESPONSE_MB` 截断
- 使用 `tests/test_crawler/` 模式测试（stubs、monkeypatch）

### 修改 Thread/推荐
- Thread 聚类：`threads/clustering.py` + `threads/scoring.py`
- 推荐管线：`recommendation/candidates.py` → `scoring.py` → `ranking.py` → `diversification.py` → `explanations.py`
- 两者均有大量单元测试——修改后运行

### Git 提交规则

  - commit message 中禁止包含任何 `Co-Authored-By` 署名（包括但不限于 Claude、Anthropic、noreply@anthropic.com 等任何 AI 相关署名）

  - 所有提交仅保留用户本人的 git 作者信息（`用户名 <邮箱>`）

  - 创建 PR 时同样不添加任何 AI 合作者信息

### 仓库管理硬性规则（永远不可违反）

  - **禁止修改公共仓库的可见性**：不得将任何公开（public）仓库切换为私有（private）或内部（internal），即使是为了清除 contributor 缓存、刷新索引或其他任何原因。此操作会导致 star 和 fork 数据永久丢失。

  - **禁止通过 `gh repo edit --visibility` 切换任何仓库的可见性**：除非用户明确要求且已书面确认接受丢失 star/fork 的后果。

  - **禁止通过其他任何手段（API、浏览器设置等）修改仓库可见性**：本规则覆盖所有可能的可见性修改方式。

---

## 关键注意事项（非显而易见的坑）

1. **路由顺序很重要**：`threads` 必须在 `router.py` 中注册在 `items` 之前，否则 `/items/{id}` 通配符会吞掉 `/items/threads`。
2. **SSRF fail-closed**：DNS 解析错误返回 `(False, "...")`——不是允许。这对安全至关重要。
3. **POST 5xx 不重试**：重试失败的 POST 可能产生重复副作用。GET/HTML/RSS 5xx 重试 3 次。
4. **线程隔离**：调度器在独立线程运行——不直接调用 async 函数。
5. **WAL 模式**：SQLite 单写入器。`busy_timeout=5000` 处理争用。无连接池——每次 `get_db()` 创建新连接。
6. **FTS5 回退**：如果 FTS 查询失败（语法错误），回退到 LIKE。LIKE 通配符用反斜杠转义。
7. **亲和度衰减**：每次交互应用 `score*0.9 + delta*0.1`——非简单递增。防止亲和度饱和。
8. **EventBus 双重持久化**：事件进入内存队列（实时 SSE）**和** `execution_events` 表（重放）。
9. **迁移幂等性**：使用 `PRAGMA table_info` 检查列是否存在，非错误消息字符串匹配。
10. **启动恢复**：所有来自前一进程的 `running` 执行在加载任务前标记为 `interrupted`。
11. **Nginx SSE 配置**：`/api/tasks/` 需要 `proxy_buffering off` + `proxy_read_timeout 3600s`（流式传输关键）。
12. **Vite 代理端口不匹配**：`vite.config.ts` 代理到 8100，但后端默认 8000。如更改 `APP_PORT`，代理会断。
13. **JWT 响应体不含 token**：登录响应不包含 `access_token`（XSS 缓解）。JWT 仅通过 httpOnly cookie 传递。
14. **无暗色模式切换**：侧边栏始终深色（`#0F1117`），内容始终浅色。`DESIGN.md` 提到暗色模式但未实现为切换。
15. **前端端口为 5200**：非标准，非 Vite 默认 5173。
