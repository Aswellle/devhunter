<div align="center">

<img src="frontend/src/assets/hero.png" width="120" alt="DevHunter logo" />

# 🔍 DevHunter

**Automatic Content Aggregation & Discovery System for Developers**

Automatically scrape high-value content from Hacker News, V2EX, GitHub Trending, and more. Centralized management, full-text search, scheduled crawling.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.11+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](#license)

[**[简体中文]**](./README.md) · [Quick Start](#quick-start) · [Features](#features) · [Architecture](#architecture) · [API Docs](#api-documentation) · [Environment Variables](#environment-variables)

</div>

---

## What is DevHunter

DevHunter is a self-hosted content aggregation system designed for developers and indie hackers to track multi-platform trends. Configure once (select sources, CSS selectors or JSON paths, keywords, cron schedule) and the system automatically scrapes, deduplicates, and stores content — no more visiting dozens of websites individually.

Built-in advanced capabilities:

- **Cross-platform Thread Aggregation (V2)**: Multi-factor scoring (lexical + entity + semantic + temporal + source) clusters coverage from multiple platforms into unified event threads.
- **Personalized Recommendations V2**: Candidate generation → multi-factor scoring → diversification → explainable output, with adaptive exploration/exploitation ratio based on your reading habits.
- **3-Step Template Wizard**: Enter URL → auto-discover structure → preview & confirm. No CSS Selector knowledge required.
- **Template Marketplace**: Share your templates to the community, import others' configurations with one click.

---

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
git clone https://github.com/Aswellle/devhunter.git && cd devhunter

cp .env.example .env
# Edit .env, change AUTH_PASSWORD and SECRET_KEY

docker compose up -d
```

After startup:

- Frontend: http://localhost
- Backend API Docs: http://localhost:8001/docs

### Option 2: Local Development

**Backend** (requires Python 3.11+):

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
python run.py
# API runs at http://localhost:8000
```

**Frontend** (requires Node.js 18+):

```bash
cd frontend
npm install
npm run dev
# UI runs at http://localhost:5173
```

First login uses `AUTH_PASSWORD` from `.env` (default `devhunter123`, **must change in production**).

---

## Features

| Feature | Description |
|---------|-------------|
| 📥 Task Management | Create / edit / delete crawling tasks, 28 preset templates |
| 🧙 3-Step Wizard | Auto-discover URL structure, no CSS Selector needed |
| 🏪 Template Marketplace | Share templates, import community configurations |
| ⏰ Scheduled Crawling | 5-field cron expressions (UTC), 1-minute precision, manual trigger |
| 🌐 Multi-Mode Engine | HTML CSS Selector / JSON API (GET & POST) / RSS, auto-pagination, retry |
| 🔍 Full-Text Search | SQLite FTS5, Chinese fallback to LIKE |
| 🔗 Thread Aggregation V2 | Multi-factor clustering (lexical + entity + semantic + temporal + source), manual merge/split |
| 🎯 Recommendations V2 | Candidate generation → scoring → diversification → explanations |
| 🏥 Source Health | HTTP availability + parse success + field coverage + freshness + dedup rate |
| ✅ Semantic Validation | 3-layer validation (transport → parse → semantic) |
| ⭐ Star & Read | Star / read status, batch operations, multi-dimension filtering |
| 📊 Real-Time Monitoring | SSE push for execution events, history & duration stats |
| 🔐 Single-User Auth | JWT + httpOnly Cookie, password via env var |

---

## Supported Sources

**28 preset templates** across 6 categories:

### Development Trends

| Template | Platform | Method | Description |
|----------|----------|--------|-------------|
| `hackernews` | Hacker News | RSS | Tech/startup/indie dev aggregation |
| `hackernews_show` | HN Show HN | RSS | Indie devs showcase projects |
| `hackernews_ask` | HN Ask HN | RSS | Developer Q&A |
| `github_trending` | GitHub Trending | HTML | Trending open-source repos |
| `trending_github_repos` | GH Trending Daily | HTML | Daily trending repos |
| `lobsters` | Lobste.rs | RSS | Tech link aggregation |

### Creative Discovery

| Template | Platform | Method | Description |
|----------|----------|--------|-------------|
| `producthunt` | Product Hunt | RSS | Daily new product launches |
| `indiehackers` | Indie Hackers | RSS | Indie dev products & discussions |
| `v2ex_create` | V2EX Create | JSON API | Devs share projects & ideas |
| `reddit_sideproject` | r/SideProject | JSON API | Side projects & feedback |

### Community Discussion

| Template | Platform | Method | Description |
|----------|----------|--------|-------------|
| `v2ex` | V2EX Hot | JSON API | Real-time hot topics |
| `v2ex_jobs` | V2EX Jobs | JSON API | Job opportunities |
| `reddit_webdev` | r/webdev | JSON API | Web development discussion |
| `reddit_startups` | r/startups | JSON API | Startup discussions |

### Tech Blogs

| Template | Platform | Method | Description |
|----------|----------|--------|-------------|
| `devto` | Dev.to | JSON API | Popular tech articles |
| `hashnode` | Hashnode | GraphQL | Developer blog platform |
| `juejin` | Juejin | JSON API (POST) | Recommended articles |
| `sspai` | Sspai | RSS | Tech/efficiency tools |
| `medium_programming` | Medium | RSS | Programming articles |

### Content Creation (Creators/Influencers)

| Template | Platform | Method | Description |
|----------|----------|--------|-------------|
| `bilibili_comprehensive` | Bilibili | JSON API | Trending video content |
| `bilibili_music` | Bilibili Music | JSON API | Music video content |
| `douyin_trending` | Douyin | JSON API | Short video trends |
| `zhihu_hot` | Zhihu | JSON API | Hot topics |

### Demand Sharing

| Template | Platform | Method | Description |
|----------|----------|--------|-------------|
| `reddit_forhire` | r/forhire | JSON API | Freelance opportunities |
| `reddit_ideas` | r/SomebodyMakeThis | JSON API | Creative ideas needed |

Also fully custom: enter any URL, auto-discover structure, configure any site.

---

## Architecture

```
devhunter/
├── backend/                    # FastAPI Backend
│   ├── app/
│   │   ├── api/                # HTTP routes
│   │   ├── services/           # Business logic
│   │   ├── repositories/       # Data access layer
│   │   ├── scheduler/          # APScheduler module
│   │   ├── crawler/            # Crawling engine (HTML/JSON/RSS)
│   │   ├── sources/            # Template registry/discovery/validation/health
│   │   ├── features/           # Feature extraction (entity/semantic/temporal)
│   │   ├── threads/            # Thread clustering/scoring/merge/split
│   │   ├── recommendation/     # Recommendation engine
│   │   ├── execution/          # Execution state machine
│   │   ├── schemas/            # Pydantic models
│   │   ├── core/               # Infrastructure (DB/Config/Logging/EventBus)
│   │   └── utils/              # Hash/URL/similarity utils
│   ├── migrations/             # SQL migrations, auto-executed on startup
│   ├── templates/              # Preset templates (JSON)
│   └── run.py                  # Entry point
│
├── frontend/                   # React + Vite + TypeScript
│   └── src/
│       ├── api/                # API client
│       ├── components/         # UI components
│       ├── pages/              # Page components
│       ├── stores/             # Zustand state management
│       └── hooks/              # Custom hooks (SSE, etc.)
│
└── docker-compose.yml          # One-click deployment
```

**Data Flow**: API routes → Services → Repositories → SQLite.

**Scheduler**: APScheduler `BackgroundScheduler` runs in separate thread, isolated from FastAPI asyncio loop.

**Crawling Engine**: Single entry for 4 modes (HTML / `json:` GET / `json-post:` POST / `rss:`), auto-detect response type, pagination, retry (3 attempts, exponential backoff), SSRF protection.

**Thread V2 Scoring**:
```
thread_score = 0.30*lexical + 0.25*entity + 0.20*semantic + 0.15*temporal + 0.10*source
```

**Recommendation V2 Flow**: Candidate generation (8 sources) → Multi-factor scoring → Diversification → Explainable output.

**Tech Stack**:

| Layer | Technology |
|-------|------------|
| Backend | FastAPI + Uvicorn |
| Scheduler | APScheduler 3.x |
| Crawling | httpx + BeautifulSoup4 + chardet |
| Auth | python-jose (JWT) + passlib |
| Database | SQLite (WAL) + FTS5 |
| Frontend | React 19 + Vite + TypeScript |
| State | TanStack Query + Zustand |
| Styling | Tailwind CSS v3 |
| Deployment | Docker Compose + Nginx |

---

## API Documentation

Visit `http://localhost:8000/docs` (Swagger UI) or `/redoc` after starting backend.

```
POST   /api/auth/login                  Login
POST   /api/auth/logout                 Logout

GET    /api/tasks                       Task list (filter + pagination)
POST   /api/tasks                       Create task
GET    /api/tasks/templates             Preset templates
PUT    /api/tasks/{id}                  Update task
DELETE /api/tasks/{id}                  Delete task (soft)
POST   /api/tasks/{id}/execute          Manual trigger
GET    /api/tasks/{id}/executions       Execution history
GET    /api/tasks/{id}/events           SSE real-time events

GET    /api/items                       Items list (search/filter/pagination)
GET    /api/items/threads               Thread list
PATCH  /api/items/{id}                  Update item status
PATCH  /api/items/batch                 Batch update
POST   /api/items/batch-delete          Batch delete

POST   /api/threads/{id}/merge          Merge threads
POST   /api/threads/{id}/split          Split thread
POST   /api/threads/{id}/feedback       Feedback on mis-clustering

GET    /api/sources                     List templates
POST   /api/sources                     Create template
POST   /api/sources/discover           URL auto-discovery
POST   /api/sources/preview            Preview extraction
POST   /api/sources/test               Test configuration
POST   /api/sources/{id}/share         Share template
POST   /api/sources/{id}/unshare       Unshare template
GET    /api/sources/marketplace/list   Browse marketplace
POST   /api/sources/{id}/import        Import from marketplace
POST   /api/sources/{id}/clone         Clone template

GET    /api/recommendations             Personalized recommendations
POST   /api/recommendations/feedback    Recommendation feedback
GET    /api/user/profile               User profile

GET    /api/stats                       Dashboard stats
GET    /api/user_prefs/topics           User topics
POST   /api/user_prefs/interactions     Record interactions
```

---

## Environment Variables

See [`backend/.env.example`](backend/.env.example) for full list:

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_PASSWORD` | `devhunter123` | Login password, **must change** |
| `SECRET_KEY` | `change-me-in-production` | JWT signing key, **must change** |
| `JWT_EXPIRE_MINUTES` | `10080` | Token expiry (7 days) |
| `DB_PATH` | `data/devhunter.db` | SQLite path |
| `CRAWLER_TIMEOUT` | `15` | Request timeout (seconds) |
| `CRAWLER_MAX_RESPONSE_MB` | `5` | Max response size |
| `SCHEDULER_MAX_WORKERS` | `3` | Parallel workers |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Allowed origins |
| `LOG_LEVEL` | `INFO` | Log level |
| `SEMANTIC_BACKEND` | `ngram` | Semantic backend (`ngram` or `embedding`) |

---

## Development

```bash
# Backend tests
cd backend
pytest

# Frontend lint
cd frontend
npm run lint
```

Test coverage:
- Crawling engine (retry/pagination/SSRF)
- Template registry/marketplace/sharing
- Thread clustering/scoring/merge/split
- Recommendation engine (candidates/scoring/diversification/explanations)
- Semantic similarity
- Adaptive recommendations

---

## Security Notice

DevHunter uses MVP authentication (single-user plaintext comparison + JWT). **Not recommended** for direct public exposure without hardening:

- Change default password and `SECRET_KEY`
- Add rate limiting at reverse proxy
- Enable `Secure` flag on cookies (requires HTTPS)

---

## Legal Compliance & Disclaimer

### Intended Use

DevHunter is an **information aggregation tool** designed for:

- Tracking public tech trends and open-source projects
- Aggregating public RSS/Atom Feeds and public API data
- Personal knowledge management
- Academic research and data analysis

### User Obligations

By using this project, you agree to:

1. **Comply with laws**: Not violate any applicable laws or third-party rights
2. **Respect ToS**: Abide by target websites' terms of service and robots.txt
3. **Control frequency**: Use reasonable crawl rates to avoid undue load
4. **Protect IP**: Not scrape unauthorized copyrighted or proprietary content
5. **Respect privacy**: Not collect or process personal sensitive data

### Prohibited Uses

- Unauthorized data scraping (bypassing login, captcha, IP bans)
- DDoS attacks or excessive request loads
- Commercial espionage or competitive intelligence
- Privacy violations (collecting PII)
- Copyright infringement (paid content, DRM-protected material)
- Any illegal activity

### Limitation of Liability

**This project is provided "as-is". Authors assume no liability** for:

- Legal disputes arising from misuse
- Feature failures due to target site changes
- Decisions made based on scraped data
- Consequences of violating third-party ToS

### Compliance Recommendations

- Read and understand target website ToS before scraping
- Consult legal professionals for commercial use
- Prefer official APIs over web scraping
- Respect `robots.txt` and Crawl-delay settings

---

## License

[MIT](LICENSE)

---

<div align="center">

**If you find DevHunter useful, please consider giving it a star!**

⭐ [Star on GitHub](https://github.com/Aswellle/devhunter) ⭐

</div>
