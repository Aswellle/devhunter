<div align="center">

<img src="frontend/src/assets/hero.png" width="120" alt="DevHunter logo" />

# 🔍 DevHunter

**全网开发需求与创意自动采集系统**

全自动抓取 Hacker News、V2EX、GitHub Trending、掘金等平台的高价值信息，集中管理、全文可搜索、支持定时调度。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.11+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](#license)

[快速启动](#快速启动) · [功能概览](#功能概览) · [架构](#架构) · [API 文档](#api-文档) · [环境变量](#环境变量) · [**[English]**](./README.en.md)

</div>

---

## 这是什么

DevHunter 是一个自托管的内容采集与聚合系统，专为开发者、独立创业者跟踪多平台动态而设计。你配置一次采集任务（选定来源、CSS Selector 或 JSON 路径、关键词、Cron 周期），系统就会按计划自动抓取、去重、入库，并提供统一的搜索与浏览界面——不用再挨个刷十几个网站。

内置多个进阶能力：

- **跨平台事件聚合（Threads V2）**：基于多因素评分（词法 + 实体 + 语义 + 时间 + 来源）的智能聚类，同一事件的多平台报道自动归组，一次看全貌。
- **个性化推荐 V2**：候选生成 → 多因子评分 → 多样性处理 → 可解释推荐，根据你的阅读习惯动态调整探索/利用比例。
- **3 步模板向导**：输入 URL → 自动发现结构 → 预览确认，无需学习 CSS Selector。
- **模板市场**：分享你的模板到社区，一键导入他人分享的配置。

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
| 🧙 3 步模板向导 | 输入 URL 自动发现结构，无需手写 CSS Selector |
| 🏪 模板市场 | 分享模板到社区，一键导入他人配置 |
| ⏰ 定时调度 | 基于 5 段 Cron 表达式（UTC），最小精度 1 分钟，支持手动触发 |
| 🌐 多模式抓取引擎 | HTML CSS Selector / JSON API（GET & POST）/ RSS，自动分页，失败自动重试 |
| 🔍 全文搜索 | SQLite FTS5 全文索引，中文场景自动回退 LIKE 匹配 |
| 🔗 跨平台聚合 V2 | 多因素智能聚类（词法 + 实体 + 语义 + 时间 + 来源），支持手动合并/拆分 |
| 🎯 个性化推荐 V2 | 候选生成 → 评分 → 多样性 → 可解释，自适应探索/利用比例 |
| 🏥 来源健康监控 | HTTP 可用性 + 解析成功率 + 字段覆盖率 + 新鲜度 + 重复率 |
| ✅ 语义验证 | 三层验证（transport → parse → semantic），区分 HTTP 200 与真实成功 |
| ⭐ 收藏与已读 | 条目 Star / 已读状态标记，支持批量操作与多维度筛选 |
| 📊 实时执行监控 | SSE 推送任务执行全链路事件，执行历史与耗时统计 |
| 🔐 单用户认证 | JWT + httpOnly Cookie，密码通过环境变量配置 |

---

## 支持的数据源

系统内置 **28 个预设模板**，按类别分组，涵盖开发趋势、创意发现、社区讨论、技术博客、内容创作和需求分享：

### 开发趋势

| 模板 | 平台 | 抓取方式 | 说明 |
|------|------|----------|------|
| `hackernews` | Hacker News | RSS | 技术/创业/独立开发聚合 |
| `hackernews_show` | Hacker News Show HN | RSS | 独立开发者展示项目 |
| `hackernews_ask` | Hacker News Ask HN | RSS | 开发者提问和寻求建议 |
| `github_trending` | GitHub Trending | HTML | 今日热门开源仓库 |
| `trending_github_repos` | GitHub Trending Daily | HTML | 每日热门仓库 |
| `lobsters` | Lobste.rs | RSS | 技术链接聚合社区 |

### 创意发现

| 模板 | 平台 | 抓取方式 | 说明 |
|------|------|----------|------|
| `producthunt` | Product Hunt | RSS | 每日新产品发布平台 |
| `indiehackers` | Indie Hackers | RSS | 独立开发者产品与讨论 |
| `v2ex_create` | V2EX 创意分享 | JSON API | 开发者分享项目和创意 |
| `reddit_sideproject` | Reddit r/SideProject | JSON API | 开发者分享副项目和创意 |

### 社区讨论

| 模板 | 平台 | 抓取方式 | 说明 |
|------|------|----------|------|
| `v2ex` | V2EX 热门 | JSON API | 实时热门话题 |
| `v2ex_jobs` | V2EX 工作 | JSON API | 工作机会和招聘 |
| `reddit_webdev` | Reddit r/webdev | JSON API | Web 开发讨论 |
| `reddit_startups` | Reddit r/startups | JSON API | 创业讨论和商业模式 |

### 技术博客

| 模板 | 平台 | 抓取方式 | 说明 |
|------|------|----------|------|
| `devto` | Dev.to | JSON API | 热门技术文章 |
| `hashnode` | Hashnode | GraphQL | 开发者博客平台 |
| `juejin` | 掘金推荐 | JSON API (POST) | 推荐文章流 |
| `sspai` | 少数派 | RSS | 科技/效率/独立开发工具 |
| `medium_programming` | Medium Programming | RSS | 技术深度文章 |

### 内容创作（UP主/内容创作者素材）

| 模板 | 平台 | 抓取方式 | 说明 |
|------|------|----------|------|
| `bilibili_comprehensive` | 哔哩哔哩 综合 | JSON API | 综合区热门视频素材 |
| `bilibili_music` | 哔哩哔哩 音乐 | JSON API | 音乐区热门视频素材 |
| `douyin_trending` | 抖音 热门 | JSON API | 短视频热门话题和趋势 |
| `zhihu_hot` | 知乎 热榜 | JSON API | 实时热门话题和讨论 |

### 需求分享

| 模板 | 平台 | 抓取方式 | 说明 |
|------|------|----------|------|
| `reddit_forhire` | Reddit r/forhire | JSON API | 自由职业项目机会 |
| `reddit_ideas` | Reddit r/SomebodyMakeThis | JSON API | 用户发布创意需求 |

也可以完全自定义：填入任意 URL，系统自动发现结构并生成配置，即可接入任何站点。

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
│   │   ├── sources/            # 模板注册 / 发现 / 验证 / 健康
│   │   ├── features/           # 特征提取（实体 / 语义 / 时间）
│   │   ├── threads/            # Thread 聚类 / 评分 / 合并 / 拆分
│   │   ├── recommendation/     # 推荐引擎（候选 / 评分 / 排序 / 多样性 / 解释）
│   │   ├── execution/          # 执行状态机
│   │   ├── schemas/            # Pydantic 请求 / 响应模型
│   │   ├── core/               # 基础设施：DB、Config、日志、事件总线
│   │   └── utils/              # 哈希 / URL / 相似度工具
│   ├── migrations/             # 纯 SQL 迁移文件，启动时自动执行
│   ├── templates/               # 预设数据源模板（JSON）
│   └── run.py                  # 启动入口
│
├── frontend/                   # React + Vite + TypeScript 前端
│   └── src/
│       ├── api/                # axios 封装的 API 客户端
│       ├── components/         # UI 组件
│       ├── pages/              # 页面组件
│       ├── stores/             # Zustand 状态管理
│       └── hooks/              # 自定义 Hook（SSE 订阅等）
│
└── docker-compose.yml          # 一键部署（backend + frontend + Nginx）
```

**数据流**：API 路由 → 业务服务层 → 数据访问层 → SQLite。

**调度器**：APScheduler 的 `BackgroundScheduler` 运行在独立线程中，与 FastAPI 的 asyncio 事件循环完全隔离；Job 状态持久化到与业务数据同库的 SQLite 表（`SQLAlchemyJobStore`），应用启动时以数据库任务表为唯一真相源重建所有调度任务。

**抓取引擎**：单一入口支持四种解析模式（HTML CSS Selector / `json:` GET / `json-post:` POST / `rss:`），自动识别响应类型、按需分页、失败重试（最多 3 次，指数退避），并在请求前对目标地址做 SSRF 防护（拦截私有网段 / 环回 / 链路本地地址）。

**Thread V2 聚类**：多因素评分公式：
```
thread_score = 0.30 * lexical + 0.25 * entity + 0.20 * semantic + 0.15 * temporal + 0.10 * source
```

**推荐 V2 流程**：候选生成（8 源）→ 多因子评分 → 多样性处理 → 可解释输出。

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

POST   /api/threads/{id}/merge          合并 Thread
POST   /api/threads/{id}/split          拆分 Thread
POST   /api/threads/{id}/feedback       反馈误聚合

GET    /api/sources                     列出模板
POST   /api/sources                     创建模板
POST   /api/sources/discover           URL 自动发现
POST   /api/sources/preview            预览提取
POST   /api/sources/test               测试配置
POST   /api/sources/{id}/share         分享模板
POST   /api/sources/{id}/unshare       取消分享
GET    /api/sources/marketplace/list   浏览市场
POST   /api/sources/{id}/import        从市场导入
POST   /api/sources/{id}/clone         克隆模板

GET    /api/recommendations             个性化推荐
POST   /api/recommendations/feedback    推荐反馈
GET    /api/user/profile                用户画像

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
| `SEMANTIC_BACKEND` | `ngram` | 语义相似度后端（`ngram` 或 `embedding`） |

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

后端测试覆盖：
- 抓取引擎（重试 / 分页 / SSRF 防护）
- 模板注册 / 市场 / 分享
- Thread 聚类 / 评分 / 合并 / 拆分
- 推荐引擎（候选 / 评分 / 多样性 / 解释）
- 语义相似度
- 自适应推荐

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
