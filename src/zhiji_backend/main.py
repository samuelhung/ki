from __future__ import annotations

import importlib
import logging as _logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .credential_store import load_hardened_env
from .paths import (
    FRONTEND_DIST,
    INGEST_ROOT,
    LOG_DIR,
    RELEASES_DIR,
    ZHIJI_HOME,
    ensure_data_dirs,
)
from .security.artifacts import (
    ArtifactOpenError,
    PinnedFileResponse,
    open_regular_under,
)
from .security.constraints import safe_identifier
from .security.redaction import RedactingFormatter, SecureTimedRotatingFileHandler

logging = SimpleNamespace(getLogger=_logging.getLogger)

_KI_HANDLER_OWNER = "zhiji"
_KI_HANDLER_OWNER_ATTR = "_zhiji_handler_owner"
_KI_HANDLER_ROLE_ATTR = "_zhiji_handler_role"

ROUTE_NAMES = (
    "dashboard",
    "source",
    "event",
    "translate",
    "brainstorm",
    "briefing",
    "ingest",
    "series",
    "config",
    "task",
    "usage",
    "log",
    "system",
    "prompt",
    "study",
    "chain",
)


def _root_logger():
    return _logging.getLogger()


def _create_console_handler():
    handler = _logging.StreamHandler()
    handler.setLevel(_logging.INFO)
    handler.setFormatter(
        RedactingFormatter(
            "%(asctime)s [%(levelname)-7s] %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    return handler


def _create_file_handler():
    handler = SecureTimedRotatingFileHandler(
        str(LOG_DIR / "ki.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    handler.setLevel(_logging.DEBUG)
    handler.setFormatter(
        RedactingFormatter(
            "%(asctime)s [%(levelname)-7s] %(name)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    return handler


def _remove_runtime_handlers(handlers) -> None:
    try:
        root = _root_logger()
    except BaseException:
        root = None
    for handler in handlers:
        if root is not None:
            try:
                if handler in root.handlers:
                    root.removeHandler(handler)
            except BaseException:
                pass
        try:
            handler.close()
        except BaseException:
            pass


def _prepare_runtime() -> tuple[Any, ...]:
    ensure_data_dirs()
    env_path = ZHIJI_HOME / ".env"
    if not env_path.exists() and not env_path.is_symlink():
        env_path = Path(__file__).resolve().parents[2] / ".env"
    load_hardened_env(env_path, override=True)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = _root_logger()
    root.setLevel(_logging.DEBUG)
    installed = []
    try:
        for role, create_handler in (
            ("console", _create_console_handler),
            ("file", _create_file_handler),
        ):
            if any(
                getattr(handler, _KI_HANDLER_OWNER_ATTR, None) == _KI_HANDLER_OWNER
                and getattr(handler, _KI_HANDLER_ROLE_ATTR, None) == role
                for handler in root.handlers
            ):
                continue
            handler = create_handler()
            setattr(handler, _KI_HANDLER_OWNER_ATTR, _KI_HANDLER_OWNER)
            setattr(handler, _KI_HANDLER_ROLE_ATTR, role)
            installed.append(handler)
            root.addHandler(handler)
        _logging.getLogger("httpx").setLevel(_logging.WARNING)
        _logging.getLogger("httpcore").setLevel(_logging.WARNING)
        _logging.getLogger("urllib3").setLevel(_logging.WARNING)
    except BaseException:
        _remove_runtime_handlers(installed)
        raise
    return tuple(installed)


def _load_dependencies() -> SimpleNamespace:
    module_names = (
        "app_lifecycle",
        "api_middleware",
        "config_manager",
        "db",
        "migrations",
        "static_delivery",
        "task_queue",
        "usage_writer",
    )
    modules = {
        name: importlib.import_module(f".{name}", __package__) for name in module_names
    }
    routes = {
        name: importlib.import_module(f".routes.{name}_routes", __package__)
        for name in ROUTE_NAMES
    }
    return SimpleNamespace(**modules, routes=routes)


def _bootstrap_application(
    *,
    prepare_runtime: Callable[[], Any] = _prepare_runtime,
    load_dependencies: Callable[[], Any] = _load_dependencies,
) -> Any:
    installed_handlers = tuple(prepare_runtime() or ())
    try:
        return load_dependencies()
    except BaseException:
        _remove_runtime_handlers(installed_handlers)
        raise


_dependencies = _bootstrap_application()
app_lifecycle = _dependencies.app_lifecycle
api_middleware = _dependencies.api_middleware
static_delivery = _dependencies.static_delivery

ensure_migrations = _dependencies.migrations.ensure_migrations
get_db_path = _dependencies.db.get_db_path
init_db = _dependencies.db.init_db
seed_default_sources = _dependencies.db.seed_default_sources
load_config = _dependencies.config_manager.load_config
start_usage_writer = _dependencies.usage_writer.start_usage_writer
stop_usage_writer = _dependencies.usage_writer.stop_usage_writer
start_worker = _dependencies.task_queue.start_worker
stop_worker = _dependencies.task_queue.stop_worker

TrustedHostMiddleware = api_middleware.TrustedHostMiddleware
ProtectedPathMiddleware = api_middleware.ProtectedPathMiddleware
api_auth = api_middleware.api_auth
spa_fallback = api_middleware.spa_fallback
hmac = api_middleware.hmac
_csv_env = api_middleware.csv_env
_allowed_hosts = api_middleware.allowed_hosts
_cors_origins = api_middleware.cors_origins
_api_token = api_middleware.api_token
_is_loopback_host = api_middleware.is_loopback_host
_is_protected_path = api_middleware.is_protected_path
_requires_token_for_request = api_middleware.requires_token_for_request
_request_token = api_middleware.request_token
_DEFAULT_ALLOWED_HOSTS = api_middleware.DEFAULT_ALLOWED_HOSTS
_DEFAULT_CORS_ORIGINS = api_middleware.DEFAULT_CORS_ORIGINS
_HAS_FRONTEND = False


def _middleware_dependencies():
    return api_middleware.MiddlewareDependencies(
        api_token=_api_token,
        request_token=_request_token,
        requires_token_for_request=_requires_token_for_request,
        is_protected_path=_is_protected_path,
        compare_digest=hmac.compare_digest,
        has_frontend=_HAS_FRONTEND,
        frontend_dist=FRONTEND_DIST,
    )


api_middleware.register_default_dependency_factory(
    _middleware_dependencies,
    owner=__name__,
)

PUBLIC_INGEST_ARTIFACTS = static_delivery.PUBLIC_INGEST_ARTIFACTS

for _route_name, _route_module in _dependencies.routes.items():
    globals()[f"{_route_name}_router"] = _route_module.router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # app_lifecycle preserves ensure_migrations(get_db_path()) before load_config().
    async with app_lifecycle.lifespan(
        app,
        logger=logging.getLogger("main"),
        ensure_migrations=ensure_migrations,
        get_db_path=get_db_path,
        load_config=load_config,
        init_db=init_db,
        seed_default_sources=seed_default_sources,
        start_usage_writer=start_usage_writer,
        stop_usage_writer=stop_usage_writer,
        start_worker=start_worker,
        stop_worker=stop_worker,
    ) as state:
        yield state


app = FastAPI(title="知几", version=__version__, lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts())
app.add_middleware(ProtectedPathMiddleware)
app.middleware("http")(api_auth)
app.middleware("http")(spa_fallback)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-API-Key",
        "Range",
        "If-Range",
        "If-None-Match",
        "If-Modified-Since",
        "If-Unmodified-Since",
    ],
    expose_headers=[
        "Accept-Ranges",
        "Content-Length",
        "Content-Range",
        "Content-Type",
        "ETag",
        "Last-Modified",
    ],
)

for _route_name in ROUTE_NAMES:
    app.include_router(globals()[f"{_route_name}_router"])


@app.get("/api/digest/latest", include_in_schema=False)
@app.post("/api/digest/generate", include_in_schema=False)
async def retired_digest_endpoint():
    return await static_delivery.retired_digest_endpoint(json_response=JSONResponse)


@app.api_route("/ingest/{kind}/{filename:path}", methods=["GET", "HEAD"])
async def serve_ingest_artifact(kind: str, filename: str):
    return await static_delivery.serve_ingest_artifact(
        kind,
        filename,
        public_ingest_artifacts=PUBLIC_INGEST_ARTIFACTS,
        ingest_root=INGEST_ROOT,
        safe_identifier=safe_identifier,
        open_regular_under=open_regular_under,
        pinned_file_response=PinnedFileResponse,
        artifact_open_error=ArtifactOpenError,
        http_exception=HTTPException,
    )


RELEASES_DIR.mkdir(parents=True, exist_ok=True)


@app.api_route("/releases/{filename:path}", methods=["GET", "HEAD"])
async def serve_release(filename: str):
    return await static_delivery.serve_release(
        filename,
        releases_dir=RELEASES_DIR,
        path_type=Path,
        safe_identifier=safe_identifier,
        open_regular_under=open_regular_under,
        pinned_file_response=PinnedFileResponse,
        artifact_open_error=ArtifactOpenError,
        http_exception=HTTPException,
    )


_HAS_FRONTEND = static_delivery.mount_frontend(app, frontend_dist=FRONTEND_DIST)
