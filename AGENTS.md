# OpenSpider — 爬虫管理平台

管理多个爬虫的生命周期，暴露标准化 API + WebSocket 供外部 AI 集成。前后端分离：Python 后端 + React 前端。

## Project

- **Stack**: Python 3.10+, FastAPI, Scrapling, SQLAlchemy (async), APScheduler, MySQL/SQLite, Alembic
- **Frontend**: React 18, TypeScript, Vite, Ant Design, Zustand, Axios
- **Build system**: hatchling (backend), npm (frontend)
- **Package manager**: uv (Python), npm (Node)
- **Entry point**: `openspider/main.py` (FastAPI app), `openspider/cli.py` (CLI via Click)
- **Config**: `openspider/config.py` — pydantic-settings, reads `.env`
- **DB**: MySQL by default; set `MYSQL_HOST=sqlite` for local SQLite

## Commands

```bash
# Install backend (dev)
pip install -e ".[dev]"

# Install frontend
cd web && npm install

# Run backend (dev)
openspider serve
# or: python -m openspider.main

# Run frontend (dev)
cd web && npm run dev    # localhost:5173

# Build frontend
cd web && npm run build  # output → web/dist/

# Test
pytest tests/

# DB migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

## Architecture

| Module | Path | Role |
|---|---|---|
| Core engine | `openspider/core/engine.py` | Lifecycle manager — init registry, scheduler, recovery |
| Registry | `openspider/core/registry.py` | Hot-reload spiders from `openspider/spiders/` via watchdog |
| Runner | `openspider/core/runner.py` | Execute a single spider, wire up pipeline & Scrapling config |
| Pipeline | `openspider/core/pipeline.py` | Dispatch items to sinks (CSV/Excel/JSON/Kafka/Doris/Parquet) |
| Scheduler | `openspider/core/scheduler.py` | APScheduler cron scheduling for spiders |
| Recovery | `openspider/core/recovery.py` | Auto-resume interrupted spiders on startup |
| API | `openspider/api/` | FastAPI routes: auth, spider CRUD, tasks, schedules, WebSocket |
| Models | `openspider/models/` | SQLAlchemy models (User, Spider, Task, Item, Schedule, Log) |
| Spiders | `openspider/spiders/base.py` | BaseSpider class users extend; templates in `templates.py` |
| Storage | `openspider/storage/database.py` | Async engine + session factory |

## Conventions

- **Docstrings**: every module and public function has a Chinese docstring ("""描述""")
- **`from __future__ import annotations`** at top of most files
- **Async-first**: all DB access uses `async_session()` + `sqlalchemy.select()`
- **Error handling**: FastAPI `HTTPException` with Chinese messages; custom `register_error_handlers`
- **Testing**: pytest + pytest-asyncio; fixtures use `tmp_path`; tests in `tests/` root
- **Naming**: snake_case for files/functions, PascalCase for classes, UPPER_SNAKE for constants
- **Logging**: loguru (`from loguru import logger`)
- **Type hints**: modern Python syntax (`str | None`, `list[str]`), not `Optional`/`List`
- **Frontend**: functional React components, Zustand for state, Ant Design components
- **Do not** hardcode secrets; use env vars via `settings`

## Notes

- CORS allows `localhost:5173` (Vite dev server) in dev mode
- Docker: `docker compose up` runs MySQL + app on port 8088
- Spider files in `openspider/spiders/` are auto-discovered — no registration needed
