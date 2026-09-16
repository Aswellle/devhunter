# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DevHunter is a full-stack web scraping and content aggregation system that automatically collects development-related content from platforms like Hacker News, V2EX, GitHub Trending, Juejin, and Indie Hackers. It features scheduled crawling, full-text search, and a React frontend.

**Tech Stack:**
- Backend: FastAPI + APScheduler (SQLAlchemyJobStore) + SQLite (WAL + FTS5) + httpx + BeautifulSoup4 + chardet; auth via python-jose/passlib
- Frontend: React 19 + Vite + TypeScript + react-router-dom v7 + TanStack Query + Zustand + axios + Tailwind CSS v3 + react-hot-toast
- Deployment: Docker Compose + Nginx

---

## Commands

### Backend

```bash
cd backend
pip install -r requirements.txt   # Install dependencies (or: pip install -e .)
python run.py                     # Start dev server (http://localhost:8000)

# Testing
python e2e_test.py                # E2E test (standalone script — the real test suite)
pytest                            # pytest is configured (pyproject.toml, testpaths=["tests"])
                                  #   Only tests/test_crawler/ has real test files (test_retry.py,
                                  #   test_pagination.py); test_api/, test_repositories/,
                                  #   test_services/ are still empty (__init__.py only).
pytest tests/test_crawler/test_retry.py       # Run a single test file
pytest -k test_404_is_terminal_no_retry       # Run a single test by name
```

`e2e_test.py` is self-contained: it sets `DB_PATH` to a temp `data/test_*.db`, overrides auth env vars, calls `init_database()` + `create_app()`, and drives the API via `fastapi.testclient.TestClient`. Run it from `backend/` (it `os.chdir`s there itself).

### Frontend

```bash
cd frontend
npm install                        # Install dependencies
npm run dev                        # Start dev server (http://localhost:5200)
npm run build                      # Production build
npm run lint                       # Lint with ESLint
```

`vite.config.ts` dev server runs on port **5200** and proxies `/api` to `http://127.0.0.1:8001` (the Docker backend port). For local backend dev on port 8000, change the proxy target accordingly.

### Docker

```bash
docker compose up -d               # Start all services
docker compose logs -f backend     # View backend logs
```

Docker port mapping differs from local dev: the **backend container's 8000 is published to host 8001** (`8001:8000`), and the **frontend (Nginx) serves on host port 80**. In Docker the frontend talks to the backend over the internal `backend` service name, not `localhost:8000`. The backend healthcheck hits `http://localhost:8000/health` *inside* the container.

### Windows one-click

`start.bat` (repo root) opens two `cmd` windows: backend via `venv\Scripts\activate && python run.py`, frontend via `npm run dev`. Expects `backend/venv` to already exist. Note: the frontend dev server runs on **port 5200** (per `vite.config.ts`), not 5173.

---

## Architecture

### Backend Layer Structure

```
backend/app/
├── api/          # FastAPI route handlers (auth, tasks, items, executions, events, stats, threads, user_prefs)
│   ├── deps.py   # require_auth dependency (Bearer header OR httpOnly cookie)
│   └── router.py # Mounts sub-routers under /api; threads MUST be registered before items
├── services/     # Business logic (task, item, execution, thread, recommendation services)
├── repositories/ # Data access layer (task, item, execution, thread, user_prefs repos)
├── scheduler/    # APScheduler job management (manager.py, jobs.py, cleanup.py)
├── crawler/      # HTTP fetching + HTML/JSON/RSS parsing engine (engine.py, dedup.py, templates.py)
├── schemas/      # Pydantic request/response models
├── core/         # Infrastructure: config, database, security, logging, http_client, event_bus, exceptions
└── utils/        # Hash, URL, and similarity (Jaccard) utilities
```

**Data Flow:** API routes → Services → Repositories → SQLite database

**Scheduler:** APScheduler `BackgroundScheduler` runs in a **separate thread** from FastAPI's async event loop. Uses `SQLAlchemyJobStore` backed by the *same* SQLite DB as app data. `restore_jobs()` clears the JobStore and reloads all active tasks from DB on startup — DB is the source of truth. A system cleanup job (`cleanup_old_data`) runs daily at 03:00 UTC to purge 30-day-old soft-deleted data. Cron triggers are 5-field, evaluated in **UTC** (`_parse_cron_trigger`). Worker jobs hold an in-process reentrancy lock (`_running_tasks` in `jobs.py`) so `max_instances=1` is enforced even across manual + scheduled triggers.

### Crawler Parsing Modes

`crawler/engine.py` supports four modes, detected by `selector_list` prefix:
- **HTML** (no prefix) — CSS Selector parsing via BeautifulSoup4
- **json:\<path\>** — JSON API GET, dot-notation path to list
- **json-post:\<path\>\|\|\|\<body\>** — JSON API POST
- **rss:** — RSS 2.0 / Atom feed parsing

Link fields support `PREF:\<prefix\>|\<path\>` syntax for URL prefix拼接.

**SSRF protection:** `engine.py` blocks requests whose resolved host falls in private/loopback/link-local/TEST-NET/multicast/reserved IP ranges (`_PRIVATE_IP_BLOCKS`) before the HTTP call. Response bodies larger than `CRAWLER_MAX_RESPONSE_MB` (default 5 MB) are **truncated** to `MAX_RESPONSE_BYTES` (not rejected). Encoding is detected with `chardet`.

**Retry + pagination:** each page fetch goes through `_fetch_page_with_retry` — up to `MAX_RETRY_ATTEMPTS` (3) attempts with `RETRY_DELAY_SECONDS` (2s) between them; 4xx responses are treated as terminal (no retry), 5xx/network errors retry. Tasks with a non-null `selector_next_page` (added in migration `005_pagination.sql`; CSS selector for HTML mode, `json:`/`json-post:`-prefixed path for JSON modes; ignored in RSS mode) are followed page-by-page up to `MAX_PAGES` (10) via `_paginate`/`_resolve_next_page_url`, stopping early on a repeated/duplicate page URL (loop guard) or an empty next-page match. Any page exhausting its retries fails the whole crawl (no partial items saved).

### Cross-Platform Threads & Recommendations

Two higher-level features sit on top of the item layer:

- **Threads** (`thread_service` + `thread_repo`, migration `003_threads.sql`) — after each crawl, `compute_threads_for_items()` groups newly fetched items with same-topic items from other platforms using `utils/similarity.py` (Jaccard over tokenized titles). Result: `threads` + `thread_items` (M:N, with a `similarity` score). `/items/threads` exposes these; note the router registers `threads` **before** `items` so `/items/{id}` doesn't shadow `/items/threads`.
- **Personalized recommendations** (`recommendation_service` + `user_prefs_repo`, migration `004_user_prefs.sql`) — scores items by topic match, behavioral affinity, recency, and engagement (weights in `DEFAULT_CONFIG`). User-set topics live in `user_topics`; behavioral tracking in `user_interactions` and `user_topic_affinity` (note: the repo singletons are named `user_interaction_repo` / `user_affinity_repo` — singular, no `_topic_` — but the underlying tables are plural / prefixed). Surfaced on the frontend `RecommendPage` and dashboard `ForYouSection`.

### Frontend Pages

```
frontend/src/pages/
├── DashboardPage.tsx   # Home — task overview + recent executions + ForYouSection
├── TasksPage.tsx       # Task CRUD + manual trigger + ExecutionHistoryPanel
├── ItemsPage.tsx       # Scraped items list with search/filter + thread view
├── StarredPage.tsx     # Starred items
├── CloudPage.tsx       # Tag/category cloud view
├── RecommendPage.tsx   # Personalized recommendations
└── LoginPage.tsx       # Password login

frontend/src/api/       # API client wrappers (axios-based client.ts + per-domain: auth, tasks, items, stats, threads, user_prefs)
frontend/src/stores/    # Zustand stores (authStore — just an isAuthenticated flag)
frontend/src/hooks/     # useTaskEventStream — SSE subscription for live execution progress
frontend/src/components/layout/AppLayout.tsx  # Nav shell wrapping all authenticated routes
```

**Routing:** `App.tsx` uses `react-router-dom` v7 with `BrowserRouter`. `AuthGuard` redirects unauthenticated users to `/login`; `AuthExpiredHandler` listens for a `devhunter:auth-expired` window event (dispatched by the axios 401 interceptor) and logs out + navigates. `TanStack Query` (`QueryClient`, `staleTime: 30s`, `retry: 1`) for server state; `Zustand` only for the auth flag.

**API client:** `frontend/src/api/client.ts` is a shared axios instance (`baseURL: '/api'`, `withCredentials: true`). Its response interceptor dispatches the `devhunter:auth-expired` event on 401 and clears the `devhunter_auth` localStorage flag. Per-domain API wrappers (`auth.ts`, `tasks.ts`, `items.ts`, etc.) build on this client.

**Realtime events:** `useTaskEventStream` hook (`frontend/src/hooks/useTaskEventStream.ts`) consumes the SSE stream via `fetch` + `ReadableStream` (not `EventSource`, so credentials carry). It maps raw events (`step_init`, `fetch_*`, `parse_*`, etc.) to a step state machine (`init→fetch→parse→filter→dedup→save`) with retry/auto-reconnect logic.

### Key Patterns

- **Lifespan management:** `backend/app/main.py` uses FastAPI lifespan context manager for startup/shutdown of scheduler, DB, and HTTP client.
- **Scheduler DB sync:** `scheduler_manager.restore_jobs()` clears JobStore and reloads all active tasks from DB on startup — DB is the source of truth.
- **Crawler error handling:** `crawler/engine.py` never raises exceptions; all errors are returned in `CrawlResult.error`.
- **DB migrations:** Plain SQL files in `backend/migrations/` (`001_init`, `002_fts`, `003_threads`, `004_user_prefs`, `005_pagination`); applied on startup via `init_database()`. `_split_sql_statements` correctly handles `BEGIN...END` blocks inside triggers.
- **Auth:** Single-user JWT (HS256, 7-day expiry). Password compared as plaintext against `AUTH_PASSWORD` (`verify_password` — MVP, not hashed). The JWT is delivered via an **httpOnly cookie** (`devhunter_token`) set by the backend on `/api/auth/login`; `require_auth` reads the Bearer header first, falling back to the cookie. The **frontend never touches the JWT** — it only stores a `devhunter_auth='1'` flag in `localStorage` (XSS mitigation). `withCredentials: true` on the axios client carries the cookie. Login response body does **not** contain `access_token` (S4 fix — prevents XSS token theft).
- **Real-time execution events:** `event_bus.py` (EventBus singleton) publishes task execution progress via SSE. Worker thread calls `publish_event()`; frontend subscribes via `/api/tasks/{task_id}/events` (`useTaskEventStream` hook, consumed with `fetch` + `ReadableStream` so credentials are carried — not `EventSource`). `jobs.py` emits granular events at each stage (`start`, `step_init`, `dedup_*`, `save_*`, `thread_*`, `items_preview`, `success`/`failure`/`warning`); the crawler engine additionally emits `fetch_*` / `parse_*` / `filter_*` events via a callback that `jobs.py` wires in.
- **URL deduplication:** Items are deduplicated by `url_hash` (SHA256 of URL). New items are bulk-inserted after dedup check.
- **Rate limiting:** Login endpoint uses `slowapi` (`core/rate_limit.py` — a shared `Limiter` singleton wired to `main.py`'s `app.state.limiter`). The limiter instance must be the same object across `main.py` and route decorators or limits won't take effect.
- **Error response shape:** All errors return `{"error": {"code": ..., "message": ...}}`. `HTTPException(detail={"code":..,"message":..})` is normalized by the handler in `main.py`; custom `DevHunterError` subclasses carry `status_code` + `error_code`.

### Database

SQLite with WAL mode (`PRAGMA journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`, `synchronous=NORMAL`). FTS5 virtual table (`items_fts`) for full-text search on items. Tables: `tasks` (includes `selector_next_page`, nullable — single-page crawl when absent), `items`, `task_executions`, `items_fts` (virtual), `threads`, `thread_items`, `user_topics`, `user_interactions`, `user_topic_affinity`, `recommendation_config`. Soft delete used on `tasks` (`deleted_at`).

### Preset Templates

Located in `backend/templates/` as JSON files. Each template defines URL, CSS selectors, and keywords for a specific platform (hackernews, v2ex, github_trending, juejin, indiehackers).

### Global Singletons

- `scheduler_manager` — `scheduler/manager.py` — APScheduler wrapper
- `event_bus` — `core/event_bus.py` — Thread-safe SSE event broadcaster
- `settings` — `core/config.py` — Pydantic settings (cached via `lru_cache`; `.env` resolved relative to `backend/` regardless of CWD)
- `get_http_client()` — `core/http_client.py` — Shared httpx.AsyncClient

---

## Environment Variables

All read by `pydantic-settings` from `.env` (case-insensitive, `extra="ignore"`). Defaults shown.

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | `development` / `production` (disables docs/redoc + validates secrets when `production`) |
| `APP_HOST` | `0.0.0.0` | Bind host |
| `APP_PORT` | `8000` | Bind port |
| `APP_DEBUG` | `false` | Debug flag |
| `AUTH_PASSWORD` | `devhunter123` | Web login password (plaintext-compared) |
| `AUTH_USERNAME` | `admin` | JWT `sub` claim / displayed username |
| `SECRET_KEY` | `change-me-in-production` | JWT signing key |
| `JWT_EXPIRE_MINUTES` | `10080` | Token expiry (7 days) |
| `DB_PATH` | `data/devhunter.db` | SQLite path (parent dir auto-created) |
| `CRAWLER_TIMEOUT` | `15.0` | HTTP timeout in seconds (float) |
| `CRAWLER_MAX_RESPONSE_MB` | `5` | Max response body size before abort |
| `CRAWLER_USER_AGENT` | Chrome 124 UA | User-Agent for crawl requests |
| `SCHEDULER_MAX_WORKERS` | `3` | Max parallel crawl jobs (ThreadPoolExecutor) |
| `SCHEDULER_MISFIRE_GRACE_TIME` | `300` | APScheduler misfire grace (seconds) |
| `LOG_LEVEL` | `INFO` | Log level |
| `LOG_FORMAT` | `json` | `json` or `text` |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Comma-separated allowed origins |

