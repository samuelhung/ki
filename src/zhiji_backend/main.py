from __future__ import annotations

import os
import logging
import logging.handlers
import hmac
import hashlib
from pathlib import Path
from dotenv import load_dotenv
from .paths import ZHIJI_HOME, FRONTEND_DIST, LOG_DIR, INGEST_ROOT, RELEASES_DIR, ensure_data_dirs

# ---- 数据目录初始化 ----
ensure_data_dirs()

# ---- .env loading ----
_env_path = ZHIJI_HOME / ".env"
if not _env_path.exists():
    # fallback: 开发时可能在项目根目录
    _project_root = Path(__file__).resolve().parents[2]
    _env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)

# ---- Logging setup ----
_LOG_DIR = LOG_DIR
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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from . import __version__
from .db import get_db_path, init_db, seed_default_sources
from .config_manager import load_config
from .migrations import ensure_migrations
from .task_queue import start_worker, stop_worker
from .usage_writer import start_usage_writer, stop_usage_writer

# Route modules
from .routes.dashboard_routes import router as dashboard_router
from .routes.source_routes import router as source_router
from .routes.event_routes import router as event_router
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
from .routes.chain_routes import router as chain_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, seed sources, start ingest task worker.
    Shutdown: gracefully stop worker."""
    logging.getLogger("main").info("KI server starting — init DB + worker")
    ensure_migrations(get_db_path())
    load_config()
    init_db()
    seed_default_sources()
    start_usage_writer()
    try:
        start_worker()
        logging.getLogger("main").info("KI server ready")
        try:
            yield
        finally:
            logging.getLogger("main").info("KI server shutting down")
            stop_worker()
    finally:
        stop_usage_writer()


app = FastAPI(title="知几", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:9120",
        "http://localhost:9120",
        *([f"http://{ip}:9120" for ip in os.getenv("KI_EXTRA_ORIGINS", "").split(",") if ip.strip()]),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 前端静态文件服务 ----
# FRONTEND_DIST 随包分发（pip install 时一起安装到 site-packages）
_HAS_FRONTEND = FRONTEND_DIST.exists()

# API token authentication. Local loopback remains open for the desktop app;
# non-loopback clients must provide KI_API_TOKEN for API and sensitive files.


class ProtectedPathMiddleware(BaseHTTPMiddleware):
    """Tag protected paths so SPA fallback never turns denied files into index.html."""

    async def dispatch(self, request: Request, call_next):
        if _is_protected_path(request.url.path):
            request.state.protected_path = True
        return await call_next(request)


app.add_middleware(ProtectedPathMiddleware)


def _api_token() -> str:
    return os.getenv("KI_API_TOKEN", "").strip()


def _is_loopback_host(host: str | None) -> bool:
    return (host or "").split("%", 1)[0] in {"127.0.0.1", "::1", "localhost", "testclient"}


def _is_protected_path(path: str) -> bool:
    return path.startswith("/api") or path.startswith("/ingest") or path.startswith("/releases")


def _requires_token_for_request(path: str, client_host: str | None) -> bool:
    if path == "/api/health" or not _is_protected_path(path):
        return False
    return not _is_loopback_host(client_host)


def _request_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    api_key_header = request.headers.get("X-API-Key", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return api_key_header


def _session_cookie_value(api_token: str) -> str:
    digest = hmac.new(api_token.encode("utf-8"), b"zhiji-remote-session", hashlib.sha256).hexdigest()
    return digest


def _has_valid_session_cookie(request: Request, api_token: str) -> bool:
    cookie = request.cookies.get("ki_session", "")
    return bool(cookie) and hmac.compare_digest(cookie, _session_cookie_value(api_token))


@app.middleware("http")
async def api_auth(request: Request, call_next):
    """Protect API and sensitive file paths.

    Local loopback clients keep zero-config desktop behavior. Remote clients
    must send KI_API_TOKEN; if unset, remote protected paths are still denied.
    Accepts Authorization: Bearer *** or X-API-Key: *** headers."""
    client_host = request.client.host if request.client else None
    if _requires_token_for_request(request.url.path, client_host):
        api_token = _api_token()
        if request.method == "OPTIONS":
            return await call_next(request)
        if not api_token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if _request_token(request) != api_token and not _has_valid_session_cookie(request, api_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def spa_fallback(request: Request, call_next):
    """Serve index.html for non-API paths (SPA client-side routing).
    Only active when frontend dist exists (dev/browser mode)."""
    response = await call_next(request)
    if _HAS_FRONTEND and response.status_code == 404 and not getattr(request.state, "protected_path", False):
        response = FileResponse(FRONTEND_DIST / "index.html")
    if _HAS_FRONTEND and not request.url.path.startswith("/api"):
        path = request.url.path
        if path in ("", "/") or path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        if _api_token() and (path in ("", "/") or path.endswith(".html") or "." not in Path(path).name):
            response.set_cookie(
                "ki_session",
                _session_cookie_value(_api_token()),
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 30,
            )
    return response


# ---- Register route modules ----

app.include_router(dashboard_router)
app.include_router(source_router)
app.include_router(event_router)
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
app.include_router(study_router)
app.include_router(chain_router)


@app.get("/api/digest/latest", include_in_schema=False)
@app.post("/api/digest/generate", include_in_schema=False)
async def retired_digest_endpoint():
    """Keep retired digest API paths from falling through to static mounts."""
    return JSONResponse({"detail": "Not Found"}, status_code=404)


# ---- Static file mounts ----

INGEST_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/ingest", StaticFiles(directory=str(INGEST_ROOT)), name="ingest")

RELEASES_DIR.mkdir(parents=True, exist_ok=True)
# Use direct route to avoid conflict with root SPA mount (html=True intercepts everything)
@app.get("/releases/{filename:path}")
async def serve_release(filename: str):
    requested = Path(filename)
    if requested.name != filename or requested.suffix.lower() not in {".dmg", ".xml"}:
        return JSONResponse({"error": "not found"}, status_code=404)
    file_path = RELEASES_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(file_path)

if _HAS_FRONTEND:
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
