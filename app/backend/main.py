from __future__ import annotations

import os
import logging as _logging
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db, seed_default_sources
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
from .routes.affairs_routes import router as affairs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, seed sources, start ingest task worker.
    Shutdown: gracefully stop worker."""
    init_db()
    seed_default_sources()
    start_worker()
    yield
    stop_worker()


app = FastAPI(title="知识情报中心", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:9120",
        "http://localhost:9120",
        *([f"http://{ip}:9120" for ip in os.getenv("KI_EXTRA_ORIGINS", "").split(",") if ip.strip()]),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SPA fallback: any non-API 404 gets index.html
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

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
    """Serve index.html for non-API paths (SPA client-side routing)."""
    response = await call_next(request)
    if response.status_code == 404 and not request.url.path.startswith("/api"):
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
app.include_router(affairs_router)


# ---- Static file mounts ----

INGEST_ROOT = Path(__file__).resolve().parents[2] / "data" / "ingest"
INGEST_ROOT.mkdir(parents=True, exist_ok=True)

app.mount("/ingest", StaticFiles(directory=str(INGEST_ROOT)), name="ingest")
app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
