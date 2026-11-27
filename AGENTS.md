# Repository Guidelines

DevHunter 是一个自托管的内容聚合系统，自动从 28+ 开发者平台（Hacker News、V2EX、GitHub Trending、Indie Hackers 等）爬取内容，将跨平台事件聚合为 Thread，并提供个性化推荐——全部支持定时执行和全文搜索。

## 项目概述

**核心目标：** 配置一次爬取任务（URL + 选择器/JSON 路径 + 关键词 + Cron），DevHunter 按计划自动抓取、去重、存储、索引——替代手动浏览数十个网站。

**关键能力：**
- **Thread V2** — 多因素跨平台事件聚类（词法 + 实体 + 语义 + 时间 + 来源）
- **个性化推荐** — 多因子引擎（`services/recommendation_service.py`：候选 → 评分 → 排序 → 可解释推荐），配合标注助手（服务端快照 + 胜率指标）；`recommendation/` 目录仅保留解释生成与离线评测指标等共享纯函数模块
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
- **x:** — X（推特）公开账号时间线：`https://x.com/<账号>` 自动改写为
  `syndication.twitter.com` 嵌入页并解析 `__NEXT_DATA__`，无需登录/API Key

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
│   │   ├── core/           # 配置、数据库、安全、SSRF、日志、event_bus、http_client、exceptions、rate_limit
│   │   ├── services/       # 业务逻辑（task、item、execution、thread、recommendation）
│   │   ├── repositories/   # 数据访问层（6 个仓储）
│   │   ├── schemas/        # Pydantic 请求/响应模型
│   │   ├── crawler/        # HTTP 抓取 + 解析引擎（engine、dedup、templates、x_source）
│   │   ├── sources/        # 模板注册、发现、预览、验证、健康、市场
│   │   ├── threads/        # 聚类、评分、合并、拆分
│   │   ├── recommendation/ # 候选、评分、排序、多样性、解释、画像、适配器
│   │   ├── scheduler/      # APScheduler 管理器、任务、清理
│   │   ├── execution/      # 执行状态机
│   │   ├── features/       # 实体提取、语义相似度、时间特征
│   │   └── utils/          # 哈希、URL、相似度工具
│   ├── migrations/         # 28 个纯 SQL 迁移文件（001–028）
│   ├── templates/          # 预设爬取模板（JSON）
│   ├── tests/              # 28 个测试文件，跨 8 个领域模块 + 1 个空目录 + 1 个独立 E2E 脚本
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

### Git 钩子
```bash
git config core.hooksPath .githooks    # 克隆后执行一次：启用提交信息语言校验
```

---

## 代码规范与通用模式

### 后端模式
- **错误处理：** `crawler/engine.py` 绝不抛出异常——所有错误通过 `CrawlResult.error` 返回。API 错误使用 `DevHunterError` 层级（含 `status_code` + `error_code`）。所有错误返回 `{"error": {"code": ..., "message": ...}}`。
- **依赖注入：** `deps.py` 提供 `require_auth()`。服务层通过构造函数注入接收仓储。
- **数据库访问：** `get_db()` 上下文管理器自动 commit/rollback。`transaction()` 用于跨仓储原子性。SQLite WAL 模式，`busy_timeout=5000`，`foreign_keys=ON`。
- **迁移：** 纯 SQL 文件通过 `init_database()` 在启动时应用。使用幂等 `ALTER TABLE ADD COLUMN`——永不破坏性变更。触发器感知的 SQL 拆分器正确处理 `BEGIN...END` 块。
- **单例模式：** `scheduler_manager`、`event_bus`、`settings`（lru_cache）、`get_http_client()`。所有仓储/服务导出单一实例。
- **SSRF 防护：** 两层防线。① URL 预检（`core/ssrf.py::resolve_and_validate_url`）：HTTP 调用前阻止私有/环回/链路本地 IP 与 metadata.* 主机名，DNS 解析失败时 **fail-closed**。② 连接层 IP pinning（`SSRFPinnedNetworkBackend`，挂在共享客户端的传输后端）：每次 TCP 连接在同一次调用内解析 DNS、校验黑名单、只拨号到已验证 IP——关闭 DNS rebinding TOCTOU；TLS 的 SNI/证书校验仍用原始主机名，https 不受影响。`follow_redirects=False`——每个跳转手动重新预检。
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
| `backend/app/core/ssrf.py` | SSRF 预检 + 连接层 IP pinning 网络后端（防 DNS rebinding） |
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
| `backend/app/recommendation/` | 共享纯函数模块（解释生成、离线评测指标）；生产引擎在 `services/recommendation_service.py` |
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
- **前端端口：** 开发服务器在 **5200**（非 Vite 默认的 5173）。代理目标见 `vite.config.ts`（必须与后端实际端口匹配）。
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
- **组织：** 28 个测试文件，8 个领域模块：`test_api/`、`test_crawler/`、`test_recommendation/`、`test_sources/`、`test_features/`、`test_threads/`、`test_services/`、`test_execution/`
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
| `THREAD_CLUSTER_WINDOW_HOURS` | `72` | Thread 聚类候选活动窗口（小时） |
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
| `star_folders` | 收藏自定义文件夹（`items.star_folder_id` 归属；删夹回落到未分类） |
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
| `/tasks/{id}` | GET/PUT/DELETE | 任务 CRUD（更新用 PUT） |
| `/tasks/{id}/execute` | POST | 手动执行触发（202） |
| `/tasks/{id}/events` | GET | SSE 事件流 |
| `/tasks/{id}/executions` | GET | 执行历史 |
| `/items` | GET | 列出条目（分页、FTS 搜索、过滤） |
| `/items/{id}` | GET/PATCH/DELETE | 条目 CRUD |
| `/items/batch` | PATCH | 批量更新（已读/收藏） |
| `/items/batch` | DELETE | 批量删除（速率限制） |
| `/items/threads` | GET | Thread 列表（分页） |
| `/items/threads/{id}` | GET | Thread 详情含条目 |
| `/items/threads/recompute` | POST | 全量重建 Thread（202 后台执行） |
| `/items/threads/recompute/status` | GET | 后台重建进度 |
| `/items/threads/overview` | GET | 聚合概览（来源数/多来源/待补聚） |
| `/items/threads/consolidate` | POST | 立即聚合（增量合并单条 Thread） |
| `/items/threads/aggregate` | POST | 手动聚合选中条目 |
| `/star-folders` | GET/POST | 收藏文件夹列表/创建 |
| `/star-folders/{id}` | PATCH/DELETE | 重命名/删除收藏文件夹 |
| `/star-folders/assign` | PATCH | 单个或批量移入文件夹 |
| `/items/threads/{id}/merge` | POST | 人工合并 Thread |
| `/items/threads/{id}/split` | POST | 人工拆分 Thread |
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
- 维护 SSRF 防护：所有对外抓取必须走共享客户端（`get_http_client()`，其传输后端自带连接层 IP pinning）；新增出口请求不要自建 `httpx.Client`，主机名策略变更只改 `core/ssrf.py` 预检层
- 遵守 `CRAWLER_MAX_RESPONSE_MB` 截断
- 使用 `tests/test_crawler/` 模式测试（stubs、monkeypatch）

### 修改 Thread/推荐
- Thread 聚类：`threads/clustering.py` + `threads/scoring.py`
- 推荐管线：`recommendation/candidates.py` → `scoring.py` → `ranking.py` → `diversification.py` → `explanations.py`
- 两者均有大量单元测试——修改后运行

### Git 提交规则

  - **提交信息语言（硬性约束，由 `.githooks/commit-msg` 强制）**：标题（首行）必须用英文书写、纯 ASCII、不超过 72 字符；空行后的正文（详情）必填，必须用中文说明改动内容与原因（可夹带代码标识符，但不得以英文句子为主）。

    ```
    fix(items): keep the timeline order stable

    按分钟聚合同一分钟内的事件，避免同一分钟内节点顺序在刷新后抖动；
    同分钟事件按 id 升序回退，保证渲染稳定。
    ```

  - 自动生成的提交（`Merge `、`Revert `、`fixup!`、`squash!`、`amend!`）豁免正文检查，标题仍须为 ASCII。

  - 克隆仓库后执行一次 `git config core.hooksPath .githooks` 启用钩子；**禁止使用 `--no-verify` 绕过**。

  - commit message 中禁止包含任何 `Co-Authored-By` 署名（包括但不限于 Claude、Anthropic、noreply@anthropic.com 等任何 AI 相关署名）——`commit-msg` 钩子同样会拦截

  - 所有提交仅保留用户本人的 git 作者信息（`用户名 <邮箱>`）

  - 创建 PR 时同样不添加任何 AI 合作者信息

### 仓库管理硬性规则（永远不可违反）

  - **禁止修改公共仓库的可见性**：不得将任何公开（public）仓库切换为私有（private）或内部（internal），即使是为了清除 contributor 缓存、刷新索引或其他任何原因。此操作会导致 star 和 fork 数据永久丢失。

  - **禁止通过 `gh repo edit --visibility` 切换任何仓库的可见性**：除非用户明确要求且已书面确认接受丢失 star/fork 的后果。

  - **禁止通过其他任何手段（API、浏览器设置等）修改仓库可见性**：本规则覆盖所有可能的可见性修改方式。

---

## 关键注意事项（非显而易见的坑）

1. **路由顺序很重要**：`threads` 必须在 `router.py` 中注册在 `items` 之前，否则 `/items/{id}` 通配符会吞掉 `/items/threads`。
2. **SSRF fail-closed**：DNS 解析错误返回 `(False, "...")`——不是允许。这对安全至关重要。连接层 pinning 同样 fail-closed：解析失败或全部命中黑名单时抛 `ConnectError`，绝不退化。
3. **POST 5xx 不重试**：重试失败的 POST 可能产生重复副作用。GET/HTML/RSS 5xx 重试 3 次。
4. **线程隔离**：调度器在独立线程运行——不直接调用 async 函数。
5. **WAL 模式**：SQLite 单写入器。`busy_timeout=5000` 处理争用。无连接池——每次 `get_db()` 创建新连接。
6. **FTS5 回退**：如果 FTS 查询失败（语法错误），回退到 LIKE。LIKE 通配符用反斜杠转义。
7. **亲和度衰减**：每次交互应用 `score*0.9 + delta*0.1`——非简单递增。防止亲和度饱和。
8. **EventBus 双重持久化**：事件进入内存队列（实时 SSE）**和** `execution_events` 表（重放）。
9. **迁移幂等性**：使用 `PRAGMA table_info` 检查列是否存在，非错误消息字符串匹配。
10. **启动恢复**：所有来自前一进程的 `running` 执行在加载任务前标记为 `interrupted`。
11. **Nginx SSE 配置**：`/api/tasks/` 需要 `proxy_buffering off` + `proxy_read_timeout 3600s`（流式传输关键）。
12. **Vite 代理端口不匹配**：`vite.config.ts` 的代理目标必须与后端实际监听端口一致（后端默认 8000）。如更改 `APP_PORT`，代理会断。
13. **JWT 响应体不含 token**：登录响应不包含 `access_token`（XSS 缓解）。JWT 仅通过 httpOnly cookie 传递。
14. **无暗色模式切换**：侧边栏始终深色（`#0F1117`），内容始终浅色。`DESIGN.md` 提到暗色模式但未实现为切换。
15. **前端端口为 5200**：非标准，非 Vite 默认 5173。
16. **ItemsPage 的 URL 同步 effect 勿依赖 `setSearchParams`**：其身份随 URL 变化，会让 effect 在每次跳转（含分页点击）后重跑并丢掉 `page`——分页立即弹回第 1 页。经 routerRef（渲染后同步的 effect）取用，深链接 page 仅在首次挂载保留。
17. **Thread 聚类的 content_kind 映射必须覆盖全部任务**：`task_repo.list_active()` 漏掉 paused/软删除任务，其条目会按默认 discussion 聚类——已暂停的条目型任务的历史条目会在重建重放中被错误聚成 Thread（用 `list_all_tasks()`）。
18. **发现器的伪列表复读门与 SPA 组合信号**：列表判定通过后还要求样本标题互异（≥3 个不同标题）——文章详情页的导航/推荐位伪容器会产出同标题复读样本，伪列表比诚实失败更有害。SPA 判定用组合信号（挂载点/打包脚本 + 内容级锚点 `<8` 字符的数量），不能拿正文长度做硬性短路——客户端渲染页的导航/页脚文字量可以很高（少数派标签页实例）。
19. **推荐配置"保存—生效"闭环**：保存后必须同时失效 `queryKeys.userPrefs.recommendationConfig()` **和** `queryKeys.recommendations.all`——只失效前者的实现让列表在 staleTime（30s）内继续显示旧分数，用户无从确认是否生效。手调权重须独立于高级面板显隐（`weightsDirty`），否则"调权重→收起高级→保存"会静默退回模式预设。
20. **推荐分的量纲**：总分是五因子的**归一化加权平均**（分母为权重和）。旧实现直接求和，各模式权重和不同（探索模式曾为 0.6）会让切换模式时全部条目分数整体缩水，并被 `min_score_threshold` 整批过滤。新增因子必须同步更新默认配置、模式预设、Schema、前端滑杆与解释器。
21. **解释徽章不得与时间戳矛盾**："刚刚发布" 只能用于真实年龄 < 1h 的条目（用 `recency_hours` 分档），不能用分数阈值反推时间；否则 20 小时前的条目也挂"刚刚发布"。
22. **负反馈必须被打分路径消费**：`user_negative_feedback` 表与 `POST /api/user-prefs/feedback` 存在不代表生效——`score_candidates` 必须读取 `get_negative_feedback_map()`（not_interested / mute_topic 排除条目，hide_source 排除该条目所属来源）。当前"为你推荐"每条都带「不感兴趣」按钮，负反馈是唯一的人工负向调节信号。
23. **推荐主题候选不得把 ID 当主题**：`user_topic_affinity` 的 task 行 `affinity_value` 是任务 UUID——旧实现直接分词，产生 `64da59ff` 这类编号主题。候选只能来自阅读关键词与**常读来源标题的高频短语**（中文按分隔符拆段，≥2 次复现），并带 `reason` 说明来源；纯数字/UUID/长十六进制一律过滤。
24. **调用记录分页用 keyset + 毫秒时间戳**：offset 分页在"边翻页边有新调用"时会重复/漏项；`model_receipts.created_at` 必须毫秒精度（秒级下同秒记录只能靠随机 UUID 排序，锚点不稳定），`utc_day_start_iso()` 同步用毫秒边界（否则 `'00:00:00Z' > '00:00:00.500Z'` 会漏计零点后消耗）。
25. **LLM 预算需调用前硬闸**：只判"剩余 > 0"时，剩余 50 token 的一次调用仍可能烧掉数千 token。`chat()` 必须以「输入估算（len/2）+ max_tokens」与剩余预算比较，不足则不发请求；`status()` 暴露 `budget_breaker_open` 供界面显示预算熔断。
26. **收藏文件夹的归属语义**：`items.star_folder_id` 在取消收藏后**保留**（文件夹视图只筛 `is_starred=1`，重新收藏自动回位）；删除文件夹走 `ON DELETE SET NULL` 回到未分类，不取消收藏。名称用 `COLLATE NOCASE` 唯一索引，批量归组走 `/api/star-folders/assign`（`folder_id=null` 表示移出）。
27. **Thread 聚合不能只靠采集管线**：采集只让**新条目**找候选 Thread，两个不同批次各自创建的单条 Thread 永远不会互相比较。`consolidate_threads()`（每小时系统任务 + `POST /items/threads/consolidate`）负责补聚孤儿并合并可归并的单条 Thread；手动聚合用 `POST /items/threads/aggregate`。候选窗口默认 72h（`THREAD_CLUSTER_WINDOW_HOURS`），24h 会让跨天报道等不到后续报道。
28. **Thread 评分需要标题内容支持**：`source_score` 必须用任务名比较（items 表没有 source_id），而跨来源加分 + 泛化实体（例如所有 GPT-5 新闻）足以把总分推过 0.35；`MIN_CONTENT_SIMILARITY=0.18` 要求词级或字符级相似度至少一项达标，避免"同一实体、不同故事"被合并。
29. **X 来源走公开嵌入时间线，不是官方 API**：`x:` 模式把 `https://x.com/<账号>` 改写为 `syndication.twitter.com` 的 Next.js 页面并解析 `__NEXT_DATA__`，无需登录；只支持账号时间线（不支持搜索/列表），每次最多 40 条，转推/回复会被过滤。X 嵌入接口按 IP 限流（约 30 次/窗口），模板默认每小时一次，GET 429 有限重试。新增 X 模板时必须同步 `schemas/task.py` 的 `PRESET_TEMPLATES` 与 `_selector_mode`（否则任务创建 400/422），并保留 `selector_title/link/summary` 的非空占位值。
30. **published_at 优先于 fetched_at**：X/RSS 等带原发时间的条目在入库时写 `items.published_at`，Thread 时间因子（`threads/scoring.py`）与展示层都优先使用它；缺失时才回退 `fetched_at`。不要把 `fetched_at` 当成事件发生时间，否则一周前的推文刚抓到就会被当成新热点。
