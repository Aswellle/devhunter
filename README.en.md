<div align="center">

<img src="frontend/src/assets/hero.png" width="120" alt="DevHunter logo" />

# 🔍 DevHunter

**Automatic Content Aggregation & Discovery System for Developers**

Automatically scrape high-value content from Hacker News, V2EX, GitHub Trending, Juejin and more — cluster cross-platform coverage into events, rank them against your reading habits, and keep everything searchable on a schedule.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.11+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](#license)

[**[简体中文]**](./README.md) · [Quick Start](#quick-start) · [Use Cases](#typical-use-cases) · [Features](#features) · [Architecture](#architecture) · [API Docs](#api-documentation) · [Environment Variables](#environment-variables)

</div>

---

## What is DevHunter

DevHunter is a **self-hosted** content aggregation system built for developers, indie hackers and content creators who track multiple platforms.

Configure a crawl task once (source, CSS selector or JSON path, keywords, cron schedule) and the system fetches, three-layer deduplicates, stores and full-text-indexes on schedule — then serves one searchable UI instead of a dozen browser tabs.

Built-in advanced capabilities:

- **Cross-platform Thread Aggregation (V2)**: multi-factor scoring (lexical + entity + semantic + temporal + source) clusters coverage of the same event across platforms into one thread.
- **Personalized Recommendations V2**: candidate generation → multi-factor scoring → diversification → explainable output, with an adaptive exploration/exploitation ratio driven by your reading behaviour.
- **3-Step Template Wizard**: enter a URL → auto-discover the structure → preview and confirm. No CSS Selector knowledge required.
- **Template Marketplace**: share your templates with the community and import others' configurations with one click.

### The problem it removes

| Today | With DevHunter |
|-------|----------------|
| Manually refreshing 10+ sites; miss it and it is gone | One cron config; the scheduler fetches on time, history stays searchable forever |
| The same story repeated on HN / V2EX / Reddit | Multi-factor clustering merges them into a single thread — read it once |
| Bookmarks become a second junk drawer | SQLite FTS5 search plus read/star state and multi-dimension filters |
| 300 unordered items a day, and still anxious | Ranked against your behaviour with an explicit reason — information becomes a decision input |
| Reinstalling scripts on every machine | One-command self-hosting with Docker Compose; your data stays yours |

### Who it is for

- **Indie hackers / side-project builders** — find demand and ideas: `r/SomebodyMakeThis`, V2EX 创意分享, Indie Hackers, Product Hunt
- **Content creators** — topics and material: Bilibili / Douyin / Zhihu hot lists plus tech blogs
- **Tech leads / architects** — technology selection and ecosystem trends: GitHub Trending, Hacker News, Lobste.rs
- **Job seekers / freelancers** — opportunity radar: V2EX jobs, `r/forhire`

---

## Typical Use Cases

| Scenario | How to configure | What you get |
|----------|------------------|--------------|
| **Daily tech briefing** | Three tasks (Hacker News, GitHub Trending, V2EX) on cron `0 9 * * *` | Open the app once in the morning; the day's highlights are already stored and searchable |
| **Topic tracking** | Keywords (e.g. `rust`, `llm`, `saas`) across several platforms | Keyword filtering plus thread aggregation — the same event seen once, across platforms |
| **Demand / idea radar** | Subscribe to `reddit_ideas`, `v2ex_create`, `indiehackers` | Turn other people's complaints and ideas into concrete product leads |
| **Creator topic pool** | Subscribe to Bilibili / Douyin / Zhihu hot-list templates | A material pool with full-text recall instead of endless scrolling |
| **Technology radar** | GitHub Trending + Lobste.rs + Medium | Watch ecosystem heat objectively instead of picking a stack on vibes |
| **Self-calibration** | Browse, star and dwell as usual; the recommendation page explains itself | Recommendations improve with use, and you know *why* each item was shown |

> Every task supports manual triggering (the ⚡ button) and a live execution stream (SSE pushes each fetch / parse / dedup / save step).

---

## Quick Start

### Option 1: Docker Compose (production / self-hosting, recommended)

Requirements: Docker and Docker Compose v2.

```bash
git clone https://github.com/Aswellle/devhunter.git && cd devhunter

cp .env.example .env
# Edit .env with real values:
#   AUTH_PASSWORD=<your strong password>
#   SECRET_KEY=$(openssl rand -hex 32)

docker compose up -d
```

> If your environment ships the standalone `docker-compose` binary instead of the Compose plugin, replace every `docker compose` below with `docker-compose`.

**Where to access it after startup:**

| Entry point | URL | Notes |
|-------------|-----|-------|
| **Frontend UI (main entry)** | **http://localhost** (or `http://<server-ip>`) | Nginx inside the `frontend` container, published on host port **80** (`ports: "80:80"`). For LAN/public access replace `localhost` with the server IP |
| Backend API | `http://localhost/api/...` | The backend port is **not** published in production (the compose file only uses `expose: "8000"`). The API is same-origin and proxied by Nginx to `backend:8000` |
| Health check | http://localhost/health | Nginx proxies to the backend `/health` |
| Swagger / ReDoc | Not reachable in production | The backend is not mapped to the host. To browse the API docs, use the dev override below to publish the backend on 8001 |
| Dev override (publish backend) | http://localhost:8001/docs | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d` (development/debugging only — do not use in production) |

First login: any username (single-user mode; the backend subject is `admin`) with the `AUTH_PASSWORD` from `.env`.
**In production the app validates `AUTH_PASSWORD` / `SECRET_KEY` at startup and refuses to boot with placeholder values.**

Common commands:

```bash
docker compose logs -f backend     # follow backend logs
docker compose ps                  # container and health status
docker compose down                # stop (the devhunter_data volume is kept)
docker compose up -d --build       # rebuild after code changes
```

**Host port 80 already in use?** Change the frontend port mapping in `docker-compose.yml`:

```yaml
    ports:
      - "8080:80"          # then reach the UI on 8080
```

Also update `CORS_ORIGINS` to `http://localhost:8080`, then open **http://localhost:8080**.

### Option 2: Local Development (backend and frontend separately)

**Backend** (requires Python 3.11+):

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # adjust AUTH_PASSWORD / APP_PORT if needed
python run.py
```

- API: **http://127.0.0.1:18100** (port comes from `APP_PORT` in `backend/.env`; the example config uses `18100`)
- API docs: **http://127.0.0.1:18100/docs**

**Frontend** (requires Node.js 18+):

```bash
cd frontend
npm install
npm run dev
```

- UI: **http://127.0.0.1:5200**
- The dev server proxies `/api` to `http://127.0.0.1:18100` (see `frontend/vite.config.ts`). **If you change the backend `APP_PORT` you must update that proxy target too**, otherwise the UI will 404.

On Windows you can run `start.bat` in the repository root to launch both sides.

---

## Features

| Feature | Description |
|---------|-------------|
| 📥 Task Management | Create / edit / delete crawl tasks; 25 preset templates with one-click enable |
| 🧙 3-Step Wizard | Auto-discover a URL's structure (including JSON paths and field detection) — no CSS Selector needed |
| 🏪 Template Marketplace | Share templates with the community, import others' configurations |
| ⏰ Scheduled Crawling | 5-field cron expressions evaluated in UTC, minute precision, manual trigger |
| 🌐 Multi-Mode Engine | HTML CSS Selector / JSON API (GET & POST) / RSS, auto-pagination, retry (3 attempts, exponential backoff) |
| 🔍 Full-Text Search | SQLite FTS5 index, automatic LIKE fallback on query syntax errors |
| 🔗 Thread Aggregation V2 | Multi-factor clustering (lexical + entity + semantic + temporal + source) keeping source and similarity scores |
| 🎯 Recommendations V2 | Candidate generation → scoring → diversification → explanations, adaptive exploration/exploitation |
| 🏥 Source Health | HTTP availability + parse success rate + field coverage + freshness + duplicate rate |
| ✅ Semantic Validation | 3-layer validation (transport → parse → semantic) distinguishing HTTP 200 from real success |
| ⭐ Star & Read | Star / read state per item, batch operations, multi-dimension filtering |
| 📊 Real-Time Monitoring | SSE stream of every execution step, plus execution history and duration stats |
| 🔐 Single-User Auth | JWT in httpOnly Cookie, login rate limiting (5/min, lockout after 5 consecutive failures) |

---

## Supported Sources

**25 preset templates** grouped by category; any other site works too — enter a URL, auto-discover the structure, save the generated config.

### Development Trends

| Template | Platform | Method | Description |
|----------|----------|--------|-------------|
| `hackernews` | Hacker News | RSS | Tech / startup / indie dev aggregation |
| `github_trending` | GitHub Trending | HTML | Trending open-source repositories |
| `trending_github_repos` | GitHub Trending (Daily) | HTML | Daily trending repositories |
| `lobsters` | Lobste.rs | RSS | Tech link aggregation community |

### Creative Discovery

| Template | Platform | Method | Description |
|----------|----------|--------|-------------|
| `hackernews_show` | Hacker News Show HN | RSS | Indie developers showcasing projects |
| `producthunt` | Product Hunt | RSS | Daily new product launches |
| `indiehackers` | Indie Hackers | RSS | Indie products and discussions |
| `v2ex_create` | V2EX 创意分享 | JSON API | Developers sharing projects and ideas |
| `reddit_sideproject` | Reddit r/SideProject | JSON API | Side projects and feedback |

### Community Discussion

| Template | Platform | Method | Description |
|----------|----------|--------|-------------|
| `v2ex` | V2EX Hot | JSON API | Real-time hot topics |
| `reddit_webdev` | Reddit r/webdev | JSON API | Web development discussion |
| `reddit_startups` | Reddit r/startups | JSON API | Startup and business-model discussion |

### Tech Blogs

| Template | Platform | Method | Description |
|----------|----------|--------|-------------|
| `devto` | Dev.to | JSON API | Popular tech articles |
| `hashnode` | Hashnode | JSON API (POST) | Developer blogging platform |
| `juejin` | Juejin | JSON API (POST) | Recommended article feed (with anti-bot headers) |
| `sspai` | Sspai | RSS | Tech / productivity / indie tools |
| `medium_programming` | Medium Programming | RSS | In-depth engineering articles |

### Content Creation (creator material)

| Template | Platform | Method | Description |
|----------|----------|--------|-------------|
| `bilibili_comprehensive` | Bilibili General | JSON API | Trending video material |
| `bilibili_music` | Bilibili Music | JSON API | Trending music video material |
| `douyin_trending` | Douyin Trending | JSON API | Short-video trends |
| `zhihu_hot` | Zhihu Hot | JSON API | Real-time hot topics and discussions |

### Demand Sharing

| Template | Platform | Method | Description |
|----------|----------|--------|-------------|
| `v2ex_jobs` | V2EX Jobs | JSON API | Job openings and hiring |
| `reddit_forhire` | Reddit r/forhire | JSON API | Freelance project opportunities |
| `reddit_ideas` | Reddit r/SomebodyMakeThis | JSON API | Ideas people want built |
| `hackernews_ask` | Hacker News Ask HN | RSS | Developer questions and advice requests |

---

## Architecture

```
devhunter/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── api/                # HTTP routes
│   │   ├── services/           # Business logic
│   │   ├── repositories/       # Data access layer
│   │   ├── scheduler/          # APScheduler module
│   │   ├── crawler/            # Crawling engine (HTML / JSON / RSS)
│   │   ├── sources/            # Template registry / discovery / preview / validation / health
│   │   ├── features/           # Feature extraction (entity / semantic / temporal)
│   │   ├── threads/            # Thread clustering / scoring
│   │   ├── recommendation/     # Recommendation engine (candidates / scoring / ranking / diversification / explanations)
│   │   ├── execution/          # Execution state machine
│   │   ├── schemas/            # Pydantic request / response models
│   │   ├── core/               # Infrastructure: DB, config, logging, event bus
│   │   └── utils/              # Hash / URL / similarity utilities
│   ├── migrations/             # Plain SQL migrations, executed in order on startup
│   ├── templates/              # Preset source templates (JSON)
│   └── run.py                  # Local entry point
│
├── frontend/                   # React + Vite + TypeScript
│   └── src/
│       ├── api/                # axios API client
│       ├── components/         # UI components
│       ├── pages/              # Page components
│       ├── stores/             # Zustand state
│       └── hooks/              # Custom hooks (SSE subscription, etc.)
│
└── docker-compose.yml          # One-command deployment (backend + frontend/Nginx)
```

**Data flow**: API routes → services → repositories → SQLite.

**Scheduler**: APScheduler's `BackgroundScheduler` runs in its own thread, fully isolated from the FastAPI asyncio loop; job state lives in the same SQLite database (`SQLAlchemyJobStore`) and the database task table is the **single source of truth** — all jobs are rebuilt from it on startup (`restore_jobs()`), with an in-process reentrancy lock enforcing `max_instances=1`.

**Crawling engine**: one entry point, four parse modes (HTML CSS Selector / `json:` GET / `json-post:` POST / `rss:`), automatic response-type detection, on-demand pagination, retry (3 attempts, exponential backoff), SSRF protection before every request (private / loopback / link-local addresses and cloud metadata endpoints are blocked, DNS failures fail closed) and redirects re-validated hop by hop.

**Deduplication**: three layers — (1) source-native ID (`external_id`, per task) → (2) URL hash (global) → (3) content fingerprint (SHA256 of title + summary).

**Thread V2 scoring**:

```
thread_score = 0.30 * lexical + 0.25 * entity + 0.20 * semantic + 0.15 * temporal + 0.10 * source
```

**Recommendation V2 flow**: candidate generation (8 sources) → multi-factor scoring → diversification → explainable output.

**Real-time events**: the `EventBus` singleton writes to both an in-memory queue (live SSE stream) and the `execution_events` table, so a dropped client can resume with a `Last-Event-ID` cursor.

**Tech stack**:

| Layer | Technology |
|-------|------------|
| Backend | FastAPI + Uvicorn |
| Scheduler | APScheduler 3.x (SQLAlchemyJobStore) |
| Crawling | httpx + BeautifulSoup4 + chardet |
| Auth | python-jose (JWT) + passlib |
| Database | SQLite (WAL) + FTS5 full-text index |
| Frontend | React 19 + Vite + TypeScript |
| State | TanStack Query (server state) + Zustand (local state) |
| Styling | Tailwind CSS v3 |
| Deployment | Docker Compose + Nginx |

---

## API Documentation

All endpoints live under the `/api` prefix and require authentication (httpOnly cookie or `Authorization: Bearer`), except `/api/auth/login` and `/health`.

**Local development**: `http://127.0.0.1:18100/docs` (Swagger UI) and `/redoc`.
**Docker production**: the backend publishes no host port, so the API docs are not directly reachable; use the dev override to publish it on 8001 and open `http://localhost:8001/docs`.

```
# Auth
POST   /api/auth/login                        Login (rate limited, sets httpOnly cookie)
POST   /api/auth/logout                       Logout

# Crawl tasks
GET    /api/tasks                             Task list (status filter + pagination)
POST   /api/tasks                             Create task
GET    /api/tasks/templates                   Preset templates
GET    /api/tasks/{id}                        Task detail
PUT    /api/tasks/{id}                        Update task
DELETE /api/tasks/{id}                        Delete task (soft delete, data kept 30 days)
POST   /api/tasks/{id}/execute                Manual trigger (202)
GET    /api/tasks/{id}/executions             Execution history
GET    /api/tasks/{id}/events                 SSE stream of execution events

# Collected items
GET    /api/items                             Item list (FTS search / filters / pagination)
GET    /api/items/counts                      Counts per dimension (badges)
GET    /api/items/{id}                        Item detail
PATCH  /api/items/{id}                        Mark read / starred
DELETE /api/items/{id}                        Delete item
PATCH  /api/items/batch                       Batch update (read / starred)
POST   /api/items/batch-delete                Batch delete (rate limited)

# Cross-platform threads
GET    /api/items/threads                     Thread list
GET    /api/items/threads/{thread_id}         Thread detail with items

# Sources and templates
GET    /api/sources                           List templates
POST   /api/sources                           Create template
GET    /api/sources/{id}                      Template detail
POST   /api/sources/discover                  URL auto-discovery (wizard step 1)
POST   /api/sources/preview                   Preview extracted items (wizard step 2)
POST   /api/sources/test                      Test a crawl configuration
POST   /api/sources/{id}/share                Share to marketplace
POST   /api/sources/{id}/unshare              Unshare
GET    /api/sources/marketplace/list          Browse the marketplace
POST   /api/sources/{id}/import               Import from the marketplace
POST   /api/sources/{id}/clone                Clone a template

# Recommendations and preferences
GET    /api/user-prefs/recommendations        Personalized recommendations (For You)
GET    /api/user-prefs/topics                 Followed topics
POST   /api/user-prefs/topics                 Add a topic
PATCH  /api/user-prefs/topics/{topic}         Adjust topic weight
DELETE /api/user-prefs/topics/{topic}         Remove a topic
GET    /api/user-prefs/topics/recommended     Recommended topics (from reading history)
POST   /api/user-prefs/interactions           Record behaviour (view/click/dwell/star/share)
GET    /api/user-prefs/interactions/recent    Recent interactions

# Overview and health
GET    /api/stats                             Dashboard statistics
GET    /health                                Health check (no auth)
```

---

## Environment Variables

See [`backend/.env.example`](backend/.env.example) for the full list (local runs) and the root [`.env.example`](.env.example) for Docker Compose (which only interpolates `AUTH_PASSWORD` and `SECRET_KEY`). All values are read by `pydantic-settings`, case-insensitively.

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | `development` / `production`; production validates secrets at startup and refuses placeholder values |
| `APP_HOST` / `APP_PORT` | `0.0.0.0` / `8000` | Backend bind address and port (`backend/.env.example` uses `18100`) |
| `APP_DEBUG` | `false` | Keep `false` in production to avoid leaking stack traces |
| `AUTH_USERNAME` | `admin` | JWT subject / display name in single-user mode |
| `AUTH_PASSWORD` | `devhunter123` | Login password (plaintext comparison), **must change** |
| `SECRET_KEY` | `change-me-in-production` | JWT signing key, **must change** (`openssl rand -hex 32`) |
| `JWT_ALGORITHM` / `JWT_EXPIRE_MINUTES` | `HS256` / `10080` | Signing algorithm and token lifetime (7 days) |
| `DB_PATH` | `data/devhunter.db` | SQLite path (parent directory is created automatically) |
| `CRAWLER_TIMEOUT` | `15.0` | Per-request timeout in seconds |
| `CRAWLER_MAX_RESPONSE_MB` | `5` | Maximum response body size (larger responses abort) |
| `CRAWLER_USER_AGENT` | Chrome 124 UA | User-Agent used for crawl requests |
| `SCHEDULER_MAX_WORKERS` | `3` | Parallel scheduler workers |
| `SCHEDULER_MISFIRE_GRACE_TIME` | `300` | APScheduler misfire grace time (seconds) |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `json` | Log level and format (`json` or `text`) |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000,http://localhost:5200,http://127.0.0.1:5200` | Allowed frontend origins, comma separated (update when the frontend port/domain changes) |
| `SEMANTIC_BACKEND` | `ngram` | Semantic similarity backend (`ngram` or `embedding`) |

---

## Development

```bash
# Backend tests
cd backend
pytest                                   # full suite
pytest tests/test_crawler/               # single module
pytest -k test_404_is_terminal_no_retry  # by name
pytest --cov=app --cov-report=term       # with coverage
python e2e_test.py                       # standalone E2E (run from backend/)

# Frontend
cd frontend
npm run dev      # dev server (:5200)
npm run build    # production build (tsc -b && vite build)
npm run lint     # ESLint
```

Test coverage:

- Crawling engine (retry / pagination / SSRF protection)
- Task execution pipeline (config guard / transactional insert / execution result persistence)
- Item repository (bulk insert / dedup fields / FTS index synchronisation)
- Template registry / marketplace / sharing / wizard API
- Thread clustering and scoring
- Recommendation engine (candidates / scoring / diversification / explanations)
- Semantic similarity

---

## Security Notice

DevHunter uses a **single-user** authentication model and is intended for self-hosting, a private network, or behind a reverse proxy:

- The login password comes from an environment variable (plaintext comparison) and **must be changed**; production startup refuses placeholder values
- The JWT is delivered as an **httpOnly cookie** (never in the response body), so the frontend never touches the credential
- Login is rate limited (5 requests/minute) with a 5-minute account lockout after 5 consecutive failures
- The crawling engine blocks private / loopback / link-local addresses and cloud metadata endpoints, fails closed on DNS errors, and re-validates every redirect hop
- The frontend Nginx sets baseline security headers (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, …)

Before exposing it to the public internet, add access control and HTTPS at the reverse-proxy layer (and enable the `Secure` flag on cookies).

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

### Risk Warnings

- Target websites may change their structure, APIs or access policies at any time, causing crawl failures or incomplete data
- Large-scale crawling may get your IP address blocked by the target site
- When using publicly scraped data for business decisions, verify the accuracy yourself

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
