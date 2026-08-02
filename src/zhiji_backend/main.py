from __future__ import annotations

import importlib
import logging as _logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path as _Path
from types import SimpleNamespace
from typing import Any

import fastapi as _fastapi
from fastapi import responses as _responses
from fastapi.middleware import cors as _cors

from . import __version__, runtime_bootstrap
from . import api_middleware as _api_middleware_runtime
from . import credential_store as _credential_store
from . import media_capability as _media_capability
from . import paths as _paths
from .security import artifacts as _artifacts
from .security import constraints as _constraints
from .security import redaction as _redaction

_PREVIOUS_MODULE_STATE = globals().copy()
FastAPI, HTTPException, JSONResponse, Path = (
    _fastapi.FastAPI,
    _fastapi.HTTPException,
    _responses.JSONResponse,
    _Path,
)
CORSMiddleware = _cors.CORSMiddleware
if "FRONTEND_DIST" not in globals():
    FRONTEND_DIST = _paths.FRONTEND_DIST
INGEST_ROOT, LOG_DIR, RELEASES_DIR, ZHIJI_HOME = (
    _paths.INGEST_ROOT,
    _paths.LOG_DIR,
    _paths.RELEASES_DIR,
    _paths.ZHIJI_HOME,
)
ensure_data_dirs = _paths.ensure_data_dirs
load_hardened_env = _credential_store.load_hardened_env
ArtifactOpenError, PinnedFileResponse, open_regular_under = (
    _artifacts.ArtifactOpenError,
    _artifacts.PinnedFileResponse,
    _artifacts.open_regular_under,
)
safe_identifier = _constraints.safe_identifier
RedactingFormatter = _redaction.RedactingFormatter
SecureTimedRotatingFileHandler = _redaction.SecureTimedRotatingFileHandler
logging = SimpleNamespace(getLogger=_logging.getLogger)
_KI_HANDLER_OWNER = runtime_bootstrap.KI_HANDLER_OWNER
_KI_HANDLER_OWNER_ATTR = runtime_bootstrap.KI_HANDLER_OWNER_ATTR
_KI_HANDLER_ROLE_ATTR = runtime_bootstrap.KI_HANDLER_ROLE_ATTR
ROUTE_NAMES = (
    "dashboard",
    "source",
    "event",
    "transcript",
    "translate",
    "brainstorm",
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
    return runtime_bootstrap.create_console_handler(
        _logging,
        RedactingFormatter,
    )


def _create_file_handler():
    return runtime_bootstrap.create_file_handler(
        _logging,
        SecureTimedRotatingFileHandler,
        RedactingFormatter,
        LOG_DIR,
    )


def _remove_runtime_handlers(handlers) -> None:
    try:
        root = _root_logger()
    except BaseException:
        return
    runtime_bootstrap.rollback_runtime(
        runtime_bootstrap.RuntimeResources(tuple(handlers)),
        root_logger=root,
    )


def _rollback_runtime_resources(resources: runtime_bootstrap.RuntimeResources) -> None:
    try:
        root = _root_logger()
    except BaseException:
        root = None
    runtime_bootstrap.rollback_runtime(resources, root_logger=root)


def _prepare_runtime() -> runtime_bootstrap.RuntimeResources:
    ensure_data_dirs()
    env_path = ZHIJI_HOME / ".env"
    if not env_path.exists() and not env_path.is_symlink():
        env_path = Path(__file__).resolve().parents[2] / ".env"
    environment_mutations = runtime_bootstrap.prepare_environment(
        os.environ,
        lambda: load_hardened_env(env_path, override=True),
    )
    environment_resources = runtime_bootstrap.RuntimeResources(
        environment=os.environ,
        environment_mutations=environment_mutations,
    )
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logging_resources = runtime_bootstrap.prepare_logging(
            logging_module=_logging,
            root_logger=_root_logger(),
            create_console_handler=_create_console_handler,
            create_file_handler=_create_file_handler,
        )
    except BaseException:
        _rollback_runtime_resources(environment_resources)
        raise
    return runtime_bootstrap.RuntimeResources(
        handlers=logging_resources.handlers,
        level_mutations=logging_resources.level_mutations,
        environment=os.environ,
        environment_mutations=environment_mutations,
    )


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


def _publish_dependencies(dependencies: SimpleNamespace) -> None:
    global app_lifecycle, api_middleware, static_delivery
    global ensure_migrations, get_db_path, init_db, seed_default_sources, load_config
    global start_usage_writer, stop_usage_writer, start_worker, stop_worker
    global TrustedHostMiddleware, ProtectedPathMiddleware, api_auth, spa_fallback
    global hmac, _csv_env, _allowed_hosts, _cors_origins, _api_token
    global _is_loopback_host, _is_protected_path, _requires_token_for_request
    global _request_token, _DEFAULT_ALLOWED_HOSTS, _DEFAULT_CORS_ORIGINS
    global PUBLIC_INGEST_ARTIFACTS, FRONTEND_DIST

    app_lifecycle = dependencies.app_lifecycle
    api_middleware = dependencies.api_middleware
    static_delivery = dependencies.static_delivery
    ensure_migrations = dependencies.migrations.ensure_migrations
    get_db_path = dependencies.db.get_db_path
    init_db = dependencies.db.init_db
    seed_default_sources = dependencies.db.seed_default_sources
    load_config = dependencies.config_manager.load_config
    start_usage_writer = dependencies.usage_writer.start_usage_writer
    stop_usage_writer = dependencies.usage_writer.stop_usage_writer
    start_worker = dependencies.task_queue.start_worker
    stop_worker = dependencies.task_queue.stop_worker
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
    PUBLIC_INGEST_ARTIFACTS = static_delivery.PUBLIC_INGEST_ARTIFACTS
    FRONTEND_DIST = _paths.FRONTEND_DIST
    for route_name, route_module in dependencies.routes.items():
        globals()[f"{route_name}_router"] = route_module.router


if "_HAS_FRONTEND" not in globals():
    _HAS_FRONTEND = False


def _snapshot_requires_token_policy():
    return _middleware_dependencies().requires_token_for_request


def _middleware_dependencies():
    return api_middleware.create_facade_dependency_factory(globals())()


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


async def retired_digest_endpoint():
    return await static_delivery.retired_digest_endpoint(json_response=JSONResponse)


async def _api_not_found():
    return JSONResponse({"detail": "Not Found"}, status_code=404)


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


async def serve_signed_video(filename: str, expires: str, signature: str):
    return await static_delivery.serve_signed_video(
        filename, expires, signature, ingest_root=INGEST_ROOT, api_token=_api_token,
        verify_video_capability=_media_capability.verify_video_capability,
        open_regular_under=open_regular_under, pinned_file_response=PinnedFileResponse,
        artifact_open_error=ArtifactOpenError,
        http_exception=HTTPException,
    )
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


def _add_middleware(
    application: FastAPI, dependencies: SimpleNamespace | None = None
) -> None:
    middleware = dependencies.api_middleware if dependencies else api_middleware
    application.add_middleware(
        middleware.TrustedHostMiddleware, allowed_hosts=middleware.allowed_hosts()
    )
    application.add_middleware(middleware.ProtectedPathMiddleware)
    application.middleware("http")(middleware.api_auth)
    application.middleware("http")(middleware.spa_fallback)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=middleware.cors_origins(),
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


def _add_routes(
    application: FastAPI, dependencies: SimpleNamespace | None = None
) -> None:
    for route_name in ROUTE_NAMES:
        router = (
            dependencies.routes[route_name].router
            if dependencies
            else globals()[f"{route_name}_router"]
        )
        application.include_router(router)
    application.post("/api/digest/generate", include_in_schema=False)(
        retired_digest_endpoint
    )
    application.get("/api/digest/latest", include_in_schema=False)(
        retired_digest_endpoint
    )
    application.api_route(
        "/api/{path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )(_api_not_found)
    application.api_route(
        "/ingest/{kind}/{filename:path}", methods=["GET", "HEAD"]
    )(serve_ingest_artifact)
    application.api_route("/media/videos/{filename}", methods=["GET", "HEAD"])(serve_signed_video)
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    application.api_route("/releases/{filename:path}", methods=["GET", "HEAD"])(
        serve_release
    )


def _assemble_application(dependencies: SimpleNamespace) -> SimpleNamespace:
    global _HAS_FRONTEND, _assembly, _dependencies, app
    previous_state = globals().copy()
    middleware = dependencies.api_middleware
    dependency_factory = middleware.create_facade_dependency_factory(globals())
    try:
        with middleware.default_dependency_factory_transaction(
            dependency_factory, owner=__name__
        ):
            application = FastAPI(title="知几", version=__version__, lifespan=lifespan)
            _add_middleware(application, dependencies)
            _add_routes(application, dependencies)
            has_frontend = dependencies.static_delivery.mount_frontend(
                application, frontend_dist=_paths.FRONTEND_DIST
            )
            _publish_dependencies(dependencies)
            _HAS_FRONTEND = has_frontend
            _assembly = SimpleNamespace(dependencies=dependencies, app=application)
            _dependencies = dependencies
            app = application
            return _assembly
    except BaseException:
        runtime_bootstrap.restore_module_state(globals(), previous_state)
        raise


def _bootstrap_application(
    *,
    prepare_runtime: Callable[[], Any] = _prepare_runtime,
    load_dependencies: Callable[[], Any] = _load_dependencies,
    assemble_application: Callable[[Any], Any] | None = None,
) -> Any:
    with _api_middleware_runtime.application_bootstrap_transaction():
        resources = runtime_bootstrap.RuntimeResources()
        try:
            prepared = prepare_runtime()
            resources = (
                prepared
                if isinstance(prepared, runtime_bootstrap.RuntimeResources)
                else runtime_bootstrap.RuntimeResources(tuple(prepared or ()))
            )
            dependencies = load_dependencies()
            if assemble_application is None:
                return dependencies
            return assemble_application(dependencies)
        except BaseException:
            _rollback_runtime_resources(resources)
            raise


with _api_middleware_runtime.application_bootstrap_transaction():
    try:
        _bootstrap_application(assemble_application=_assemble_application)
    except BaseException:
        runtime_bootstrap.restore_module_state(globals(), _PREVIOUS_MODULE_STATE)
        raise
    else:
        _PREVIOUS_MODULE_STATE = None
