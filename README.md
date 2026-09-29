<div align="center">

<img src="frontend/src/assets/hero.png" width="120" alt="DevHunter logo" />

# 🔍 DevHunter

**全网开发需求与创意自动采集系统**

全自动抓取 Hacker News、V2EX、GitHub Trending、掘金等平台的高价值信息，跨平台聚合为事件、按你的阅读习惯排序，集中管理、全文可搜索、支持定时调度。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.11+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](#license)

[快速启动](#快速启动) · [典型场景](#典型使用场景) · [功能概览](#功能概览) · [架构](#架构) · [API 文档](#api-文档) · [环境变量](#环境变量) · [**[English]**](./README.en.md)

</div>

---

## 这是什么

DevHunter 是一个**自托管**的信息采集与聚合系统，专为开发者、独立创业者和内容创作者跟踪多平台动态而设计。

你配置一次采集任务（选来源、CSS Selector 或 JSON 路径、关键词、Cron 周期），系统就按计划自动抓取、三层去重、入库、建全文索引，并提供统一的搜索与浏览界面——不用再挨个刷十几个网站。

内置多个进阶能力：

- **跨平台事件聚合（Threads V2）**：多因素评分（词法 + 实体 + 语义 + 时间 + 来源）的智能聚类，同一事件的多平台报道自动归组，一次看全貌。
- **个性化推荐 V2**：候选生成 → 多因子评分 → 多样性处理 → 可解释推荐，根据你的阅读行为动态调整探索/利用比例。
- **3 步模板向导**：输入 URL → 自动发现结构 → 预览确认，无需学习 CSS Selector。
- **模板市场**：分享你的模板到社区，一键导入他人分享的配置。

### 它替你解决的问题

| 现状 | DevHunter |
|------|-----------|
| 10+ 个站点每天手动刷，漏掉就没了 | 配置一次 Cron，调度器按点替你抓，历史永久可查 |
| 同一条消息在 HN / V2EX / Reddit 各说一遍 | 多因素聚类自动归并为 Thread，只看一次 |
| 收藏夹变成第二个垃圾场，找不回来 | SQLite FTS5 全文检索 + 已读/收藏/多维筛选 |
| 每天面对 300 条无序列表，看完更焦虑 | 按你的行为排序、给出推荐理由，把"信息"变成"决策输入" |
| 换台机器就得重装一堆脚本 | Docker Compose 一条命令自托管，数据留在自己手里 |

### 适合谁

- **独立开发者 / 副业者** — 找需求、找灵感：`r/SomebodyMakeThis`、V2EX 创意分享、Indie Hackers、Product Hunt
- **内容创作者** — 选题与素材：B 站 / 抖音 / 知乎热榜 + 技术博客
- **技术负责人 / 架构师** — 技术选型与生态趋势：GitHub Trending、Hacker News、Lobste.rs
- **求职者 / 自由职业者** — 机会雷达：V2EX 工作、`r/forhire`

---

## 典型使用场景

| 场景 | 配置方式 | 你得到什么 |
|------|----------|------------|
| **每日技术晨报** | 3 个任务分别抓 Hacker News、GitHub Trending、V2EX，Cron `0 9 * * *` | 早上打开一次，三个平台的当日重点已入库，可搜索 |
| **主题追踪** | 关键词（如 `rust`、`llm`、`saas`）+ 跨平台来源 | 关键词命中过滤 + Thread 聚合，同一事件跨平台一次看完 |
| **需求 / 灵感雷达** | 订阅 `reddit_ideas`、`v2ex_create`、`indiehackers` | 从别人的吐槽和创意里找可做的产品点 |
| **创作者选题库** | 订阅 B 站 / 抖音 / 知乎热榜类模板 | 热榜素材池 + 全文回溯，选题不再靠刷手机 |
| **技术雷达** | GitHub Trending + Lobste.rs + Medium | 观察生态热度变化，而不是凭印象选型 |
| **自我校准** | 正常浏览、收藏、停留；推荐页给出理由 | 推荐越用越准，且知道"为什么给你看这条" |

> 全部支持手动触发（任务卡片上的 ⚡）与实时执行流（SSE 推送抓取/解析/去重/入库每一步）。

---

## 快速启动

### 方式一：Docker Compose（生产 / 自托管，推荐）

前置条件：Docker 与 Docker Compose v2。

```bash
git clone https://github.com/Aswellle/devhunter.git && cd devhunter

cp .env.example .env
# 编辑 .env，填入真实值：
#   AUTH_PASSWORD=<你的强密码>
#   SECRET_KEY=$(openssl rand -hex 32)

docker compose up -d
```

> 如果你的环境安装的是独立的 `docker-compose` 可执行文件（而非 Compose 插件），把本文中所有 `docker compose` 换成 `docker-compose`。

**启动后访问地址：**

| 入口 | 地址 | 说明 |
|------|------|------|
| **前端界面（主入口）** | **http://localhost**（或 `http://<服务器IP>`） | `frontend` 容器内的 Nginx，映射宿主机 **80** 端口（`ports: "80:80"`）。同局域网/公网访问把 `localhost` 换成服务器 IP 即可 |
| 后端 API | `http://localhost/api/...` | 生产环境**不单独暴露后端端口**（compose 中仅 `expose: "8000"`），API 与前端同源、由 Nginx 反向代理到 `backend:8000` |
| 健康检查 | http://localhost/health | Nginx 反代到后端 `/health` |
| Swagger / ReDoc | 生产默认不可访问 | 后端未映射到宿主机。需要查看接口文档时用下面的「开发 override」把后端映射到 8001 |
| 开发 override（映射后端） | http://localhost:8001/docs | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`（仅用于开发/调试，勿在生产使用） |

首次登录：用户名任意（单用户模式，后端固定为 `admin`），密码为 `.env` 中的 `AUTH_PASSWORD`。
**生产环境启动时会校验 `AUTH_PASSWORD` / `SECRET_KEY`，使用占位符将拒绝启动。**

常用命令：

```bash
docker compose logs -f backend     # 查看后端日志
docker compose ps                  # 查看容器与健康状态
docker compose down                # 停止（数据卷 devhunter_data 保留）
docker compose up -d --build       # 代码更新后重建
```

**宿主机 80 端口已被占用？** 修改 `docker-compose.yml` 中 frontend 的端口映射：

```yaml
    ports:
      - "8080:80"          # 改为从 8080 访问
```

同时把 `CORS_ORIGINS` 改成 `http://localhost:8080`，然后访问 **http://localhost:8080**。

### 方式二：本地开发（前后端分离）

**后端**（需 Python 3.11+）：

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # 按需修改 AUTH_PASSWORD / APP_PORT
python run.py
```

- API：**http://127.0.0.1:18100**（端口取自 `backend/.env` 的 `APP_PORT`，示例配置为 `18100`）
- 接口文档：**http://127.0.0.1:18100/docs**

**前端**（需 Node.js 18+）：

```bash
cd frontend
npm install
npm run dev
```

- 界面：**http://127.0.0.1:5200**
- 开发服务器把 `/api` 代理到 `http://127.0.0.1:18100`（见 `frontend/vite.config.ts`）。**改了后端 `APP_PORT` 必须同步修改该代理目标**，否则界面会 404。

Windows 用户可直接运行根目录的 `start.bat` 一键启动前后端。

---

## 功能概览

| 功能 | 说明 |
|------|------|
| 📥 采集任务管理 | 创建 / 编辑 / 删除采集任务，25 个预设数据源模板一键接入 |
| 🧙 3 步模板向导 | 输入 URL 自动发现结构（含 JSON 路径与字段探测），无需手写 CSS Selector |
| 🏪 模板市场 | 分享模板到社区，一键导入他人配置 |
| ⏰ 定时调度 | 5 段 Cron 表达式（UTC 求值），分钟级精度，支持手动触发 |
| 🌐 多模式抓取引擎 | HTML CSS Selector / JSON API（GET & POST）/ RSS，自动分页，失败自动重试（最多 3 次指数退避） |
| 🔍 全文搜索 | SQLite FTS5 全文索引，语法错误时自动回退 LIKE 匹配 |
| 🔗 跨平台聚合 V2 | 多因素聚类（词法 + 实体 + 语义 + 时间 + 来源），保留来源与相似度评分 |
| 🎯 个性化推荐 V2 | 候选生成 → 评分 → 多样性 → 可解释，自适应探索/利用比例 |
| 🏥 来源健康监控 | HTTP 可用性 + 解析成功率 + 字段覆盖率 + 新鲜度 + 重复率 |
| ✅ 语义验证 | 三层验证（transport → parse → semantic），区分 HTTP 200 与真实成功 |
| ⭐ 收藏与已读 | 条目 Star / 已读状态标记，支持批量操作与多维度筛选 |
| 📊 实时执行监控 | SSE 推送任务执行全链路事件，含执行历史与耗时统计 |
| 🔐 单用户认证 | JWT + httpOnly Cookie，登录限流（5 次/分钟，连续 5 次失败锁定） |

---

## 支持的数据源

内置 **25 个预设模板**，按类别分组；也支持完全自定义（填入任意 URL，自动发现结构并生成配置）。

### 开发趋势

| 模板 | 平台 | 抓取方式 | 说明 |
|------|------|----------|------|
| `hackernews` | Hacker News | RSS | 技术/创业/独立开发聚合 |
| `github_trending` | GitHub Trending | HTML | 今日热门开源仓库 |
| `trending_github_repos` | GitHub Trending (Daily) | HTML | 每日热门仓库 |
| `lobsters` | Lobste.rs | RSS | 技术链接聚合社区 |

### 创意发现

| 模板 | 平台 | 抓取方式 | 说明 |
|------|------|----------|------|
| `hackernews_show` | Hacker News Show HN | RSS | 独立开发者展示项目 |
| `producthunt` | Product Hunt | RSS | 每日新产品发布 |
| `indiehackers` | Indie Hackers | RSS | 独立开发者产品与讨论 |
| `v2ex_create` | V2EX 创意分享 | JSON API | 开发者分享项目和创意 |
| `reddit_sideproject` | Reddit r/SideProject | JSON API | 开发者分享副项目和创意 |

### 社区讨论

| 模板 | 平台 | 抓取方式 | 说明 |
|------|------|----------|------|
| `v2ex` | V2EX 热门 | JSON API | 实时热门话题 |
| `reddit_webdev` | Reddit r/webdev | JSON API | Web 开发讨论 |
| `reddit_startups` | Reddit r/startups | JSON API | 创业讨论和商业模式 |

### 技术博客

| 模板 | 平台 | 抓取方式 | 说明 |
|------|------|----------|------|
| `devto` | Dev.to | JSON API | 热门技术文章 |
| `hashnode` | Hashnode | JSON API (POST) | 开发者博客平台 |
| `juejin` | 掘金推荐 | JSON API (POST) | 推荐文章流（含反爬请求头） |
| `sspai` | 少数派 | RSS | 科技/效率/独立开发工具 |
| `medium_programming` | Medium Programming | RSS | 技术深度文章 |

### 内容创作（UP主 / 内容创作者素材）

| 模板 | 平台 | 抓取方式 | 说明 |
|------|------|----------|------|
| `bilibili_comprehensive` | 哔哩哔哩 综合 | JSON API | 综合区热门视频素材 |
| `bilibili_music` | 哔哩哔哩 音乐 | JSON API | 音乐区热门视频素材 |
| `douyin_trending` | 抖音 热门 | JSON API | 短视频热门话题与趋势 |
| `zhihu_hot` | 知乎 热榜 | JSON API | 实时热门话题和讨论 |

### 需求分享

| 模板 | 平台 | 抓取方式 | 说明 |
|------|------|----------|------|
| `v2ex_jobs` | V2EX 工作 | JSON API | 工作机会和招聘 |
| `reddit_forhire` | Reddit r/forhire | JSON API | 自由职业项目机会 |
| `reddit_ideas` | Reddit r/SomebodyMakeThis | JSON API | 用户发布创意需求 |
| `hackernews_ask` | Hacker News Ask HN | RSS | 开发者提问和寻求建议 |

---

## 架构

```
devhunter/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/                # HTTP 路由层
│   │   ├── services/           # 业务编排层
│   │   ├── repositories/       # 数据访问层
│   │   ├── scheduler/          # APScheduler 调度模块
│   │   ├── crawler/            # 抓取引擎（HTML / JSON / RSS）
│   │   ├── sources/            # 模板注册 / 发现 / 预览 / 验证 / 健康
│   │   ├── features/           # 特征提取（实体 / 语义 / 时间）
│   │   ├── threads/            # Thread 聚类 / 评分
│   │   ├── recommendation/     # 推荐引擎（候选 / 评分 / 排序 / 多样性 / 解释）
│   │   ├── execution/          # 执行状态机
│   │   ├── schemas/            # Pydantic 请求 / 响应模型
│   │   ├── core/               # 基础设施：DB、Config、日志、事件总线
│   │   └── utils/              # 哈希 / URL / 相似度工具
│   ├── migrations/             # 纯 SQL 迁移文件，启动时按序号自动执行
│   ├── templates/              # 预设数据源模板（JSON）
│   └── run.py                  # 本地启动入口
│
├── frontend/                   # React + Vite + TypeScript 前端
│   └── src/
│       ├── api/                # axios 封装的 API 客户端
│       ├── components/         # UI 组件
│       ├── pages/              # 页面组件
│       ├── stores/             # Zustand 状态管理
│       └── hooks/              # 自定义 Hook（SSE 订阅等）
│
└── docker-compose.yml          # 一键部署（backend + frontend/Nginx）
```

**数据流**：API 路由 → 业务服务层 → 数据访问层 → SQLite。

**调度器**：APScheduler 的 `BackgroundScheduler` 运行在独立线程中，与 FastAPI 的 asyncio 事件循环完全隔离；Job 状态持久化到与业务数据同库的 SQLite 表（`SQLAlchemyJobStore`），启动时以**数据库任务表为唯一真相源**重建全部调度任务（`restore_jobs()`），并用进程内重入锁强制 `max_instances=1`。

**抓取引擎**：单一入口支持四种解析模式（HTML CSS Selector / `json:` GET / `json-post:` POST / `rss:`），自动识别响应类型、按需分页、失败重试（最多 3 次，指数退避），请求前对目标地址做 SSRF 防护（拦截私有网段 / 环回 / 链路本地地址，DNS 解析失败时 fail-closed），重定向逐跳重新校验。

**去重**：三层——(1) 来源原生 ID（`external_id`，按任务）→ (2) URL hash（全局）→ (3) 内容指纹（title + summary 的 SHA256）。

**Thread V2 聚类**：多因素评分公式

```
thread_score = 0.30 * lexical + 0.25 * entity + 0.20 * semantic + 0.15 * temporal + 0.10 * source
```

**推荐 V2 流程**：候选生成（8 源）→ 多因子评分 → 多样性处理 → 可解释输出。

**实时事件**：`EventBus` 单例同时向内存队列（SSE 实时流）与 `execution_events` 表写入，断线后可用 `Last-Event-ID` 游标重放。

**技术栈**：

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + Uvicorn |
| 调度器 | APScheduler 3.x（SQLAlchemyJobStore） |
| 抓取 | httpx + BeautifulSoup4 + chardet |
| 认证 | python-jose (JWT) + passlib |
| 数据库 | SQLite（WAL 模式）+ FTS5 全文索引 |
| 前端框架 | React 19 + Vite + TypeScript |
| 状态管理 | TanStack Query（服务端状态）+ Zustand（本地状态） |
| UI 样式 | Tailwind CSS v3 |
| 部署 | Docker Compose + Nginx |

---

## API 文档

全部端点挂在 `/api` 前缀下，除 `/api/auth/login` 与 `/health` 外均需认证（httpOnly Cookie 或 `Authorization: Bearer`）。

**本地开发**：`http://127.0.0.1:18100/docs`（Swagger UI）、`/redoc`。
**Docker 生产**：后端不暴露端口，接口文档默认不可直接访问；需要时用开发 override 映射到 8001 后访问 `http://localhost:8001/docs`。

```
# 认证
POST   /api/auth/login                        登录（限流，写入 httpOnly Cookie）
POST   /api/auth/logout                       注销

# 采集任务
GET    /api/tasks                             任务列表（状态过滤 + 分页）
POST   /api/tasks                             创建任务
GET    /api/tasks/templates                   预设模板列表
GET    /api/tasks/{id}                        任务详情
PUT    /api/tasks/{id}                        更新任务
DELETE /api/tasks/{id}                        删除任务（软删除，数据保留 30 天）
POST   /api/tasks/{id}/execute                手动触发执行（202）
GET    /api/tasks/{id}/executions             执行历史
GET    /api/tasks/{id}/events                 SSE 实时执行事件流

# 采集结果
GET    /api/items                             条目列表（FTS 搜索 / 过滤 / 分页）
GET    /api/items/counts                      各维度计数（角标用）
GET    /api/items/{id}                        条目详情
PATCH  /api/items/{id}                        标记已读 / 收藏
DELETE /api/items/{id}                        删除条目
PATCH  /api/items/batch                       批量更新（已读 / 收藏）
POST   /api/items/batch-delete                批量删除（限流）

# 跨平台聚合
GET    /api/items/threads                     Thread 列表
GET    /api/items/threads/{thread_id}         Thread 详情（含条目）

# 来源与模板
GET    /api/sources                           列出模板
POST   /api/sources                           创建模板
GET    /api/sources/{id}                      模板详情
POST   /api/sources/discover                  URL 自动发现（向导第一步）
POST   /api/sources/preview                   预览提取结果（向导第二步）
POST   /api/sources/test                      测试抓取配置
POST   /api/sources/{id}/share                分享到市场
POST   /api/sources/{id}/unshare              取消分享
GET    /api/sources/marketplace/list          浏览市场
POST   /api/sources/{id}/import               从市场导入
POST   /api/sources/{id}/clone                克隆模板

# 推荐与用户偏好
GET    /api/user-prefs/recommendations        个性化推荐（For You）
GET    /api/user-prefs/topics                 我的关注主题
POST   /api/user-prefs/topics                 添加主题
PATCH  /api/user-prefs/topics/{topic}         调整主题权重
DELETE /api/user-prefs/topics/{topic}         删除主题
GET    /api/user-prefs/topics/recommended     推荐主题（基于阅读历史）
POST   /api/user-prefs/interactions           记录行为（view/click/dwell/star/share）
GET    /api/user-prefs/interactions/recent    最近交互记录

# 概览与健康
GET    /api/stats                             仪表盘统计
GET    /health                                健康检查（无需认证）
```

---

## 环境变量

完整列表见 [`backend/.env.example`](backend/.env.example)（本地运行）与根目录 [`.env.example`](.env.example)（Docker Compose 只读取 `AUTH_PASSWORD` 与 `SECRET_KEY`）。全部由 `pydantic-settings` 读取，大小写不敏感。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_ENV` | `development` | `development` / `production`；生产环境会校验敏感配置，拒绝占位符启动 |
| `APP_HOST` / `APP_PORT` | `0.0.0.0` / `8000` | 后端绑定地址与端口（`backend/.env.example` 示例为 `18100`） |
| `APP_DEBUG` | `false` | 生产环境务必保持 `false`，避免暴露堆栈跟踪 |
| `AUTH_USERNAME` | `admin` | 单用户模式下的 JWT 主体 / 显示名 |
| `AUTH_PASSWORD` | `devhunter123` | 登录密码（明文比对），**务必修改** |
| `SECRET_KEY` | `change-me-in-production` | JWT 签名密钥，**务必修改**（`openssl rand -hex 32`） |
| `JWT_ALGORITHM` / `JWT_EXPIRE_MINUTES` | `HS256` / `10080` | 签名算法与 Token 有效期（默认 7 天） |
| `DB_PATH` | `data/devhunter.db` | SQLite 路径（父目录自动创建） |
| `CRAWLER_TIMEOUT` | `15.0` | 单次抓取请求超时（秒） |
| `CRAWLER_MAX_RESPONSE_MB` | `5` | 响应体大小上限（超出中止） |
| `CRAWLER_USER_AGENT` | Chrome 124 UA | 抓取请求使用的 User-Agent |
| `SCHEDULER_MAX_WORKERS` | `3` | 调度器并行 Worker 数 |
| `SCHEDULER_MISFIRE_GRACE_TIME` | `300` | APScheduler misfire 宽限（秒） |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `json` | 日志级别与格式（`json` 或 `text`） |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000,http://localhost:5200,http://127.0.0.1:5200` | 允许的前端来源，逗号分隔（改前端端口/域名后需同步） |
| `SEMANTIC_BACKEND` | `ngram` | 语义相似度后端（`ngram` 或 `embedding`） |

---

## 开发

```bash
# 后端测试
cd backend
pytest                                   # 完整套件
pytest tests/test_crawler/               # 单模块
pytest -k test_404_is_terminal_no_retry  # 按名称
pytest --cov=app --cov-report=term       # 带覆盖率
python e2e_test.py                       # 独立 E2E（在 backend/ 下运行）

# 前端
cd frontend
npm run dev      # 开发服务器（:5200）
npm run build    # 生产构建（tsc -b && vite build）
npm run lint     # ESLint
```

测试覆盖：

- 抓取引擎（重试 / 分页 / SSRF 防护）
- 采集任务执行链路（配置守卫 / 事务内入库 / 执行结果落库）
- 条目仓储（批量写入 / 去重字段 / FTS 索引同步）
- 模板注册 / 市场 / 分享 / 向导 API
- Thread 聚类与评分
- 推荐引擎（候选 / 评分 / 多样性 / 解释）
- 语义相似度

---

## 安全说明

DevHunter 采用**单用户认证**模型，适合自托管 / 内网 / 反向代理后使用：

- 登录密码来自环境变量（明文比对），**部署前必须修改**；生产环境启动时会拒绝占位符值
- JWT 通过 **httpOnly Cookie** 下发（响应体不含 token），前端不接触凭证
- 登录接口限流（5 次/分钟），连续 5 次失败后账户锁定 5 分钟
- 抓取引擎内置 SSRF 防护：拒绝私有网段 / 环回 / 链路本地地址与云元数据端点，DNS 解析失败时 fail-closed，重定向逐跳重新校验
- 前端 Nginx 已配置 `X-Frame-Options`、`X-Content-Type-Options`、`Referrer-Policy` 等基础安全响应头

直接暴露到公网前，建议至少在反向代理层再加一层访问控制与 HTTPS（并为 Cookie 启用 `Secure`）。

---

## 法律合规与免责声明

### 使用目的声明

DevHunter 是一个**信息聚合工具**，设计用于以下合法目的：

- 跟踪公开的技术动态与开源项目趋势
- 聚合公开 RSS/Atom Feed 与公开 API 数据
- 个人知识管理与信息整理
- 学术研究与数据分析

### 使用者义务

使用本项目即表示您承诺：

1. **遵守法律法规**：不得利用本项目违反任何适用法律、法规或第三方权利
2. **尊重服务条款**：遵守目标网站的服务条款（ToS）、使用协议与 robots.txt 指令
3. **控制请求频率**：合理设置抓取频率，避免对目标站点造成不当负载或干扰
4. **保护知识产权**：不得抓取、存储或传播受版权保护、商业秘密或其他知识产权保护的未授权内容
5. **尊重隐私**：不得利用本项目收集、存储或处理个人敏感数据

### 禁止用途

严禁将本项目用于以下目的：

- **未经授权的数据抓取**：绕过登录、验证码、IP 封禁等访问控制机制大量抓取受保护内容
- **DDoS 攻击**：以过高频率请求对目标站点造成拒绝服务压力
- **商业竞争情报**：大规模抓取竞品数据用于不正当竞争目的
- **隐私侵犯**：收集、存储或传播个人身份信息（PII）或受保护的健康/金融数据
- **版权侵权**：抓取付费内容、受 DRM 保护材料或其他未授权内容
- **任何非法活动**：包括但不限于间谍活动、骚扰、欺诈或身份盗窃

### 风险提示

- 目标网站可能随时更改其结构、API 或访问策略，导致抓取失败或数据不完整
- 大规模抓取可能导致您的 IP 地址被目标站点封禁
- 使用公开抓取的数据进行商业决策时，请自行核实数据准确性

### 责任限制

**本项目按"原样"提供，作者不承担任何直接或间接责任**，包括但不限于：

- 因滥用本项目导致的任何法律纠纷或赔偿责任
- 因目标站点结构变更导致的功能失效
- 因使用本项目获取的数据导致的任何决策损失
- 因违反第三方服务条款导致的任何后果

### 合规建议

- 在抓取任何网站前，请仔细阅读并理解其服务条款
- 对于商业用途，请咨询法律专业人士确保合规
- 考虑使用官方 API 而非网页抓取（如目标站点提供 API）
- 尊重网站的 `robots.txt` 指令与 Crawl-delay 设置

---

## License

[MIT](LICENSE)

---

<div align="center">

**如果这个项目对你有帮助，欢迎 ⭐ Star 支持！**

⭐ [GitHub Star](https://github.com/Aswellle/devhunter) ⭐

</div>
