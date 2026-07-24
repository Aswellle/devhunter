<div align="center">

<img src="frontend/src/assets/hero.png" width="120" alt="DevHunter logo" />

# 🔍 DevHunter

**全网开发需求与创意自动采集系统**

全自动抓取 Hacker News、V2EX、GitHub Trending、掘金等平台的高价值信息，集中管理、全文可搜索、支持定时调度。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](#license)

[快速启动](#快速启动) · [功能概览](#功能概览) · [架构](#架构) · [API 文档](#api-文档) · [环境变量](#环境变量)

</div>

---

## 这是什么

DevHunter 是一个自托管的内容采集与聚合系统，专为开发者、独立创业者跟踪多平台动态而设计。你配置一次采集任务（选定来源、CSS Selector 或 JSON 路径、关键词、Cron 周期），系统就会按计划自动抓取、去重、入库，并提供统一的搜索与浏览界面——不用再挨个刷十几个网站。

内置两个进阶能力：

- **跨平台事件聚合（Threads）**：当多个平台报道同一事件时，系统基于标题分词相似度自动把它们归为一组，一次看全貌，而不是看到十条重复信息。
- **个性化推荐**：根据你设置的关注主题、历史交互行为（浏览/点击/停留/收藏），持续计算内容与你的匹配度，越用越懂你。

---

## 快速启动

### 方式一：Docker Compose（推荐）

```bash
git clone https://github.com/Aswellle/devhunter.git && cd devhunter

cp .env.example .env
# 编辑 .env，修改 AUTH_PASSWORD 和 SECRET_KEY

docker compose up -d
```

启动后访问：

- 前端界面：http://localhost
- 后端 API 文档：http://localhost:8001/docs

### 方式二：本地开发

**后端**（需 Python 3.11+）：

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
python run.py
# API 运行在 http://localhost:8000
```

**前端**（需 Node.js 18+）：

```bash
cd frontend
npm install
npm run dev
# 界面运行在 http://localhost:5173
```

首次登录使用 `.env` 中配置的 `AUTH_PASSWORD`（默认 `devhunter123`，**生产环境请务必修改**）。

---

## 功能概览

| 功能 | 说明 |
|------|------|
| 📥 采集任务管理 | 创建 / 编辑 / 删除采集任务，10 个预设数据源模板一键接入 |
| ⏰ 定时调度 | 基于 5 段 Cron 表达式（UTC），最小精度 1 分钟，支持手动触发 |
| 🌐 多模式抓取引擎 | HTML CSS Selector / JSON API（GET & POST）/ RSS，自动分页，失败自动重试 |
| 🔍 全文搜索 | SQLite FTS5 全文索引，中文场景自动回退 LIKE 匹配 |
| 🔗 跨平台聚合 | 同一事件的多平台报道自动归组为 Thread，一览多方视角 |
| 🎯 个性化推荐 | 基于主题偏好 + 行为亲缘度 + 新鲜度 + 参与度的多因子评分 |
| ⭐ 收藏与已读 | 条目 Star / 已读状态标记，支持批量操作与多维度筛选 |
| 📊 实时执行监控 | SSE 推送任务执行全链路事件，执行历史与耗时统计 |
| 🔐 单用户认证 | JWT + httpOnly Cookie，密码通过环境变量配置 |

---

## 支持的数据源

系统内置 10 个预设模板，涵盖技术、创业、内容社区：

| 模板 | 平台 | 抓取方式 |
|------|------|----------|
| `hackernews` | Hacker News | RSS |
| `v2ex` | V2EX 热门 | JSON API |
| `github_trending` | GitHub Trending | HTML |
| `juejin` | 掘金推荐 | JSON API (POST) |
| `indiehackers` | Indie Hackers | RSS |
| `devto` | Dev.to | JSON API |
| `reddit_webdev` | Reddit r/webdev | JSON API |
| `sspai` | 少数派 | RSS |
| `bilibili_comprehensive` | 哔哩哔哩 综合区 | JSON API |
| `bilibili_music` | 哔哩哔哩 音乐区 | JSON API |

也可以完全自定义：填入任意 URL + CSS Selector / JSON 路径 / RSS 地址，即可接入模板之外的任何站点。

---

## 架构

```
devhunter/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/                # HTTP 路由层（auth / tasks / items / threads / ...）
│   │   ├── services/           # 业务编排层
│   │   ├── repositories/       # 数据访问层
│   │   ├── scheduler/          # APScheduler 调度模块
│   │   ├── crawler/            # 抓取引擎（HTML / JSON / RSS 解析 + SSRF 防护）
│   │   ├── schemas/            # Pydantic 请求 / 响应模型
│   │   ├── core/               # 基础设施：DB、Config、日志、事件总线
│   │   └── utils/              # 哈希 / URL / Jaccard 相似度工具
│   ├── migrations/             # 纯 SQL 迁移文件，启动时自动执行
│   ├── templates/               # 预设数据源模板（JSON）
│   └── run.py                  # 启动入口
│
├── frontend/                   # React + Vite + TypeScript 前端
│   └── src/
│       ├── api/                 # axios 封装的 API 客户端
│       ├── components/          # UI 组件（dashboard / items / tasks / layout）
│       ├── pages/                # 页面组件
│       ├── stores/               # Zustand 状态管理
│       └── hooks/                # 自定义 Hook（SSE 订阅等）
│
└── docker-compose.yml           # 一键部署（backend + frontend + Nginx）
```

**数据流**：API 路由 → 业务服务层 → 数据访问层 → SQLite。

**调度器**：APScheduler 的 `BackgroundScheduler` 运行在独立线程中，与 FastAPI 的 asyncio 事件循环完全隔离；Job 状态持久化到与业务数据同库的 SQLite 表（`SQLAlchemyJobStore`），应用启动时以数据库任务表为唯一真相源重建所有调度任务。

**抓取引擎**：单一入口支持四种解析模式（HTML CSS Selector / `json:` GET / `json-post:` POST / `rss:`），自动识别响应类型、按需分页、失败重试（最多 3 次，指数退避），并在请求前对目标地址做 SSRF 防护（拦截私有网段 / 环回 / 链路本地地址）。

**技术栈**：

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + Uvicorn |
| 调度器 | APScheduler 3.x |
| 抓取 | httpx + BeautifulSoup4 + chardet |
| 认证 | python-jose (JWT) + passlib |
| 数据库 | SQLite（WAL 模式）+ FTS5 全文索引 |
| 前端框架 | React 19 + Vite + TypeScript |
| 状态管理 | TanStack Query（服务端状态）+ Zustand（本地状态） |
| UI 样式 | Tailwind CSS v3 |
| 部署 | Docker Compose + Nginx |

---

## API 文档

启动后端后访问 `http://localhost:8000/docs`（Swagger UI）或 `/redoc` 查看完整交互式文档。核心端点一览：

```
POST   /api/auth/login                  登录获取 Token
POST   /api/auth/logout                 注销

GET    /api/tasks                       任务列表（支持状态过滤 + 分页）
POST   /api/tasks                       创建任务
GET    /api/tasks/templates             预设模板列表
PUT    /api/tasks/{id}                  更新任务
DELETE /api/tasks/{id}                  删除任务（软删除）
POST   /api/tasks/{id}/execute          手动触发执行
GET    /api/tasks/{id}/executions       执行历史
GET    /api/tasks/{id}/events           SSE 实时执行事件流

GET    /api/items                       采集结果列表（搜索 / 过滤 / 分页）
GET    /api/items/threads               跨平台聚合事件列表
PATCH  /api/items/{id}                  更新条目状态（已读 / 收藏）
PATCH  /api/items/batch                 批量更新
POST   /api/items/batch-delete          批量删除

GET    /api/stats                       仪表盘统计数据
GET    /api/user_prefs/topics           用户关注主题
POST   /api/user_prefs/interactions     记录用户行为（用于推荐）
```

---

## 环境变量

完整列表见 [`backend/.env.example`](backend/.env.example)，核心项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AUTH_PASSWORD` | `devhunter123` | Web 登录密码，**务必修改** |
| `SECRET_KEY` | `change-me-in-production` | JWT 签名密钥，**务必修改**（建议 `openssl rand -hex 32`） |
| `JWT_EXPIRE_MINUTES` | `10080` | Token 有效期（默认 7 天） |
| `DB_PATH` | `data/devhunter.db` | SQLite 数据库路径 |
| `CRAWLER_TIMEOUT` | `15` | 单次抓取请求超时（秒） |
| `CRAWLER_MAX_RESPONSE_MB` | `5` | 响应体大小上限（超出截断） |
| `SCHEDULER_MAX_WORKERS` | `3` | 调度器并行 Worker 数 |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | 允许的前端来源，逗号分隔 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

---

## 开发

```bash
# 后端测试
cd backend
pytest

# 前端 Lint
cd frontend
npm run lint
```

后端测试当前覆盖抓取引擎的重试与分页逻辑（`tests/test_crawler/`）；API / 仓库层 / 服务层测试目录已搭好骨架，欢迎补充。

---

## 安全须知

DevHunter 面向个人 / 小团队自托管场景设计的 MVP 认证方案（单用户明文密码比较 + JWT），**不建议**未加固直接暴露到公网。若需要公网部署，至少应当：

- 修改默认密码与 `SECRET_KEY`
- 在反向代理层增加登录速率限制
- 为 Cookie 启用 `Secure` 标志（需配合 HTTPS）

---

## License

[MIT](LICENSE)
