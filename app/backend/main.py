from __future__ import annotations

import os
import logging
import logging.handlers
from pathlib import Path
from dotenv import load_dotenv
from .paths import PROJECT_ROOT, FRONTEND_DIST

# ---- KI_HOME: data directory ----
# In Tauri release: Rust sets KI_HOME=~/Documents/KI/
# In dev: falls back to project root's data/ directory
_IS_TAURI = os.getenv("KI_TAURI", "").strip() == "1"
KI_HOME = PROJECT_ROOT
KI_HOME.mkdir(parents=True, exist_ok=True)

# ---- .env loading ----
_env_path = KI_HOME / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)

# ---- Logging setup ----
_LOG_DIR = KI_HOME / "data" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Root logger config — captures all "knowledge-intelligence" + module loggers
_root = logging.getLogger()
_root.setLevel(logging.DEBUG)

# Console handler: INFO+ to stderr (visible in uvicorn output)
_console = logging.StreamHandler()
_console.setLevel(logging.INFO)
_console.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-7s] %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
_root.addHandler(_console)

# File handler: DEBUG+ with daily rotation, keep 30 days
_file = logging.handlers.TimedRotatingFileHandler(
    str(_LOG_DIR / "ki.log"),
    when="midnight",
    interval=1,
    backupCount=30,
    encoding="utf-8",
)
_file.setLevel(logging.DEBUG)
_file.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-7s] %(name)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
_root.addHandler(_file)

# Silence noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import get_db_path, init_db, seed_default_sources
from .migrations import ensure_migrations
from .task_queue import start_worker, stop_worker

# Route modules
from .routes.dashboard_routes import router as dashboard_router
from .routes.source_routes import router as source_router
from .routes.event_routes import router as event_router
from .routes.digest_routes import router as digest_router
from .routes.translate_routes import router as translate_router
from .routes.brainstorm_routes import router as brainstorm_router
from .routes.briefing_routes import router as briefing_router
from .routes.ingest_routes import router as ingest_router
from .routes.series_routes import router as series_router
from .routes.config_routes import router as config_router
from .routes.task_routes import router as task_router
from .routes.usage_routes import router as usage_router
from .routes.log_routes import router as log_router
from .routes.study_routes import router as study_router
from .routes.system_routes import router as system_router
from .routes.prompt_routes import router as prompt_router
from .routes.entity_routes import router as entity_router
from .routes.chain_routes import router as chain_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, seed sources, start ingest task worker.
    Shutdown: gracefully stop worker."""
    logging.getLogger("main").info("KI server starting — init DB + worker")
    ensure_migrations(get_db_path())
    init_db()
    seed_default_sources()
    start_worker()
    logging.getLogger("main").info("KI server ready")
    yield
    logging.getLogger("main").info("KI server shutting down")
    stop_worker()


app = FastAPI(title="知几", version="1.8.6", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:9120",
        "http://localhost:9120",
        "tauri://localhost",
        "https://tauri.localhost",
        *([f"http://{ip}:9120" for ip in os.getenv("KI_EXTRA_ORIGINS", "").split(",") if ip.strip()]),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Frontend serving (dev mode only) ----
# In Tauri mode, the frontend is embedded in the Tauri binary — no need to serve.
# FRONTEND_DIST is imported from paths.py
_HAS_FRONTEND = FRONTEND_DIST.exists() and not _IS_TAURI

# Optional API token authentication (set KI_API_TOKEN env var to enable)
_API_TOKEN = os.getenv("KI_API_TOKEN", "").strip()


@app.middleware("http")
async def api_auth(request: Request, call_next):
    """Optional API token auth — only enforced when KI_API_TOKEN is set.
    Skips health check, OPTIONS preflight, and non-API paths.
    Accepts Authorization: Bearer *** or X-API-Key: <token> headers."""
    if _API_TOKEN and request.url.path.startswith("/api") and request.url.path != "/api/health":
        if request.method == "OPTIONS":
            return await call_next(request)
        auth_header = request.headers.get("Authorization", "")
        api_key_header = request.headers.get("X-API-Key", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        elif api_key_header:
            token = api_key_header
        if token != _API_TOKEN:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def spa_fallback(request: Request, call_next):
    """Serve index.html for non-API paths (SPA client-side routing).
    Only active when frontend dist exists (dev/browser mode)."""
    response = await call_next(request)
    if _HAS_FRONTEND and response.status_code == 404 and not request.url.path.startswith("/api"):
        return FileResponse(FRONTEND_DIST / "index.html")
    return response


# ---- Register route modules ----

app.include_router(dashboard_router)
app.include_router(source_router)
app.include_router(event_router)
app.include_router(digest_router)
app.include_router(translate_router)
app.include_router(brainstorm_router)
app.include_router(briefing_router)
app.include_router(ingest_router)
app.include_router(series_router)
app.include_router(config_router)
app.include_router(task_router)
app.include_router(usage_router)
app.include_router(log_router)
app.include_router(system_router)
app.include_router(prompt_router)
app.include_router(entity_router)
app.include_router(study_router)
app.include_router(chain_router)


# ---- Static file mounts ----

INGEST_ROOT = KI_HOME / "data" / "ingest"
INGEST_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/ingest", StaticFiles(directory=str(INGEST_ROOT)), name="ingest")

if _HAS_FRONTEND:
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
