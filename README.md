# 🔍 DevHunter

**全网开发需求与创意自动采集系统** — 全自动抓取 Hacker News、V2EX、GitHub Trending、掘金等平台的高价值信息，集中管理、可搜索、定时执行。

---

## 快速启动

### 方式一：Docker Compose（推荐，一条命令）

```bash
# 1. 克隆项目
git clone <repo-url> devhunter && cd devhunter

# 2. 配置（可选，默认密码 devhunter123）
cp .env.example .env
# 编辑 .env 修改 AUTH_PASSWORD 和 SECRET_KEY

# 3. 启动
docker compose up -d

# 4. 访问
# 前端界面：http://localhost
# 后端 API：http://localhost:8000/docs
```

### 方式二：本地开发

**后端（Python 3.11+）**：
```bash
cd backend
pip install -r requirements.txt   # 或 pip install -e .
cp .env.example .env
python run.py
# API 运行在 http://localhost:8000
```

**前端（Node.js 18+）**：
```bash
cd frontend
npm install
npm run dev
# 界面运行在 http://localhost:5173
```

---

## 功能概览

| 功能 | 说明 |
|------|------|
| 📥 采集任务管理 | 创建/编辑/删除采集任务，支持 5 个预设模板 |
| ⏰ 定时调度 | 基于 Cron 表达式，最小精度 1 分钟 |
| 🌐 网页抓取 | httpx + BeautifulSoup4，支持自定义 CSS Selector |
| 🔍 全文搜索 | SQLite FTS5，中文 LIKE 回退 |
| ⭐ 收藏管理 | 条目 Star / 已读状态，筛选查看 |
| 📊 执行监控 | 实时查看任务状态、执行历史、耗时统计 |
| 🔐 单用户认证 | JWT Token，密码通过环境变量配置 |

---

## 预设数据源模板

| 模板 ID | 名称 | 说明 |
|---------|------|------|
| `hackernews` | Hacker News | 技术/创业/独立开发者社区 |
| `v2ex` | V2EX | 中文开发者社区技术分区 |
| `github_trending` | GitHub Trending | 今日热门仓库 |
| `juejin` | 掘金 | 中文前端/后端技术文章 |
| `indiehackers` | Indie Hackers | 独立开发者产品展示 |

---

## 项目结构

```
devhunter/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/             # HTTP 路由层
│   │   ├── services/        # 业务编排层
│   │   ├── repositories/    # 数据访问层
│   │   ├── scheduler/       # APScheduler 调度模块
│   │   ├── crawler/         # 抓取引擎模块
│   │   ├── schemas/         # Pydantic 模型
│   │   └── core/            # 基础设施（DB、Config、日志）
│   ├── migrations/          # SQL 迁移文件
│   ├── templates/           # 预设模板 JSON
│   └── run.py               # 启动脚本
│
├── frontend/                # React + Vite + Tailwind 前端
│   └── src/
│       ├── api/             # API 请求封装
│       ├── components/      # UI 组件
│       ├── pages/           # 页面组件
│       ├── stores/          # Zustand 状态管理
│       └── types/           # TypeScript 类型定义
│
└── docker-compose.yml       # 一键部署
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AUTH_PASSWORD` | `devhunter123` | Web 登录密码（务必修改） |
| `SECRET_KEY` | `change-me...` | JWT 签名密钥（务必修改） |
| `DB_PATH` | `data/devhunter.db` | SQLite 数据库路径 |
| `CRAWLER_TIMEOUT` | `15` | HTTP 请求超时（秒） |
| `SCHEDULER_MAX_WORKERS` | `3` | 调度器并行 Worker 数 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

---

## API 文档

启动后访问 `http://localhost:8000/docs`（Swagger UI）或 `http://localhost:8000/redoc`。

核心端点：

```
POST   /api/auth/login              # 登录获取 Token
GET    /api/tasks                   # 任务列表
POST   /api/tasks                   # 创建任务
PUT    /api/tasks/{id}              # 更新任务
DELETE /api/tasks/{id}              # 删除任务（软删除）
POST   /api/tasks/{id}/execute      # 手动触发执行
GET    /api/tasks/{id}/executions   # 执行历史
GET    /api/items                   # 采集结果列表（支持搜索/过滤）
PATCH  /api/items/{id}              # 更新条目状态
PATCH  /api/items/batch             # 批量更新
GET    /api/tasks/templates         # 预设模板列表
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + Uvicorn |
| 调度器 | APScheduler 3.x (BackgroundScheduler) |
| 抓取 | httpx + BeautifulSoup4 + chardet |
| 数据库 | SQLite (WAL 模式) + FTS5 全文搜索 |
| 前端框架 | React 18 + Vite + TypeScript |
| 状态管理 | TanStack Query + Zustand |
| UI 样式 | Tailwind CSS v3 |
| 部署 | Docker Compose + Nginx |
