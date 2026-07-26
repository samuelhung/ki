from __future__ import annotations

import hmac
import os
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from starlette.datastructures import URL, Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import (
    TrustedHostMiddleware as StarletteTrustedHostMiddleware,
)

from .paths import FRONTEND_DIST

DEFAULT_ALLOWED_HOSTS = ["localhost", "127.0.0.1", "::1", "testserver"]
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:9120",
    "http://127.0.0.1:9120",
    "tauri://localhost",
    "https://tauri.localhost",
]


@dataclass(frozen=True)
class MiddlewareDependencies:
    api_token: Callable[[], str]
    request_token: Callable[[Request], str]
    requires_token_for_request: Callable[[str, str | None], bool]
    is_protected_path: Callable[[str], bool]
    is_loopback_host: Callable[[str | None], bool]
    compare_digest: Callable[[str, str], bool]
    has_frontend: bool
    frontend_dist: Path


DefaultDependencyFactory = Callable[[], MiddlewareDependencies]


@dataclass(frozen=True)
class _DefaultFactoryRegistration:
    owner: str
    identity: tuple[str, str]
    factory: DefaultDependencyFactory


@dataclass(frozen=True)
class DefaultFactoryRegistrationChange:
    previous: _DefaultFactoryRegistration | None
    installed: _DefaultFactoryRegistration
    changed: bool


_existing_factory_lock = globals().get("_DEFAULT_FACTORY_LOCK")
if _existing_factory_lock is None or not hasattr(_existing_factory_lock, "_is_owned"):
    _DEFAULT_FACTORY_LOCK = threading.RLock()
if "_DEFAULT_FACTORY_REGISTRATION" not in globals():
    _DEFAULT_FACTORY_REGISTRATION: _DefaultFactoryRegistration | None = None


def csv_env(name: str, defaults: list[str]) -> list[str]:
    value = os.getenv(name, "").strip()
    if not value:
        return defaults.copy()
    return [item.strip() for item in value.split(",") if item.strip()]


def allowed_hosts() -> list[str]:
    return csv_env("KI_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS)


def cors_origins() -> list[str]:
    return csv_env("KI_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)


class TrustedHostMiddleware(StarletteTrustedHostMiddleware):
    """TrustedHostMiddleware with bracketed IPv6 Host parsing."""

    async def __call__(self, scope, receive, send) -> None:
        if self.allow_any or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        host_header = Headers(scope=scope).get("host", "")
        if host_header.startswith("[") and "]" in host_header:
            closing_bracket = host_header.index("]")
            suffix = host_header[closing_bracket + 1 :]
            valid_suffix = not suffix
            if suffix.startswith(":") and suffix[1:].isdigit():
                port = int(suffix[1:])
                valid_suffix = 1 <= port <= 65535
            host = host_header[1:closing_bracket] if valid_suffix else ""
        else:
            host = host_header.split(":", 1)[0]

        is_valid_host = False
        found_www_redirect = False
        for pattern in self.allowed_hosts:
            if host == pattern or (
                pattern.startswith("*") and host.endswith(pattern[1:])
            ):
                is_valid_host = True
                break
            if "www." + host == pattern:
                found_www_redirect = True

        if is_valid_host:
            await self.app(scope, receive, send)
        elif found_www_redirect and self.www_redirect:
            url = URL(scope=scope)
            response = RedirectResponse(url=str(url.replace(netloc="www." + url.netloc)))
            await response(scope, receive, send)
        else:
            response = PlainTextResponse("Invalid host header", status_code=400)
            await response(scope, receive, send)


class ProtectedPathMiddleware(BaseHTTPMiddleware):
    """Tag protected paths so SPA fallback never serves index.html for them."""

    async def dispatch(self, request: Request, call_next):
        dependencies = _request_dependencies(request)
        if dependencies.is_protected_path(request.url.path):
            request.state.protected_path = True
        return await call_next(request)


def api_token() -> str:
    return os.getenv("KI_API_TOKEN", "").strip()


def is_loopback_host(host: str | None) -> bool:
    return (host or "").split("%", 1)[0] in {
        "127.0.0.1",
        "::1",
        "localhost",
        "testclient",
    }


def is_protected_path(path: str) -> bool:
    return path.startswith("/api") or path.startswith("/ingest") or path.startswith(
        "/releases"
    )


def requires_token_for_request(path: str, client_host: str | None) -> bool:
    if path == "/api/health" or not is_protected_path(path):
        return False
    return not is_loopback_host(client_host)


def request_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    api_key_header = request.headers.get("X-API-Key", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return api_key_header


def _local_dependencies() -> MiddlewareDependencies:
    return MiddlewareDependencies(
        api_token=api_token,
        request_token=request_token,
        requires_token_for_request=requires_token_for_request,
        is_protected_path=is_protected_path,
        is_loopback_host=is_loopback_host,
        compare_digest=hmac.compare_digest,
        has_frontend=FRONTEND_DIST.exists(),
        frontend_dist=FRONTEND_DIST,
    )


def register_default_dependency_factory(
    factory: DefaultDependencyFactory,
    *,
    owner: str,
) -> DefaultFactoryRegistrationChange:
    """Register one application resolver; same-owner reloads may refresh it."""
    if not callable(factory):
        raise TypeError("default dependency factory must be callable")
    if not isinstance(owner, str) or not owner:
        raise ValueError("default dependency factory owner must be a non-empty string")
    module = getattr(factory, "__module__", None)
    qualname = getattr(factory, "__qualname__", None)
    if not isinstance(module, str) or not isinstance(qualname, str):
        raise TypeError("default dependency factory must be a named callable")

    registration = _DefaultFactoryRegistration(
        owner=owner,
        identity=(module, qualname),
        factory=factory,
    )
    global _DEFAULT_FACTORY_REGISTRATION
    with _DEFAULT_FACTORY_LOCK:
        current = _DEFAULT_FACTORY_REGISTRATION
        if current is None:
            _DEFAULT_FACTORY_REGISTRATION = registration
        elif current.factory is factory:
            return DefaultFactoryRegistrationChange(current, current, False)
        elif current.owner == owner and current.identity == registration.identity:
            _DEFAULT_FACTORY_REGISTRATION = registration
        else:
            raise RuntimeError(
                f"default dependency factory already registered by {current.owner}"
            )
    return DefaultFactoryRegistrationChange(current, registration, True)


@contextmanager
def default_dependency_factory_transaction(
    factory: DefaultDependencyFactory,
    *,
    owner: str,
):
    """Keep dependency resolution on the last committed factory during assembly."""
    global _DEFAULT_FACTORY_REGISTRATION
    with _DEFAULT_FACTORY_LOCK:
        change = register_default_dependency_factory(factory, owner=owner)
        try:
            yield change
        except BaseException:
            if change.changed:
                _DEFAULT_FACTORY_REGISTRATION = change.previous
            raise


def rollback_default_dependency_factory(
    change: DefaultFactoryRegistrationChange,
) -> bool:
    """Restore the registration replaced by a failed application assembly."""
    if not isinstance(change, DefaultFactoryRegistrationChange):
        raise TypeError("registration change must be DefaultFactoryRegistrationChange")
    if not change.changed:
        return False
    global _DEFAULT_FACTORY_REGISTRATION
    with _DEFAULT_FACTORY_LOCK:
        if _DEFAULT_FACTORY_REGISTRATION is not change.installed:
            return False
        _DEFAULT_FACTORY_REGISTRATION = change.previous
    return True


def _current_dependencies() -> MiddlewareDependencies:
    with _DEFAULT_FACTORY_LOCK:
        registration = _DEFAULT_FACTORY_REGISTRATION
        dependencies = (
            registration.factory() if registration is not None else _local_dependencies()
        )
        if not isinstance(dependencies, MiddlewareDependencies):
            raise TypeError("default dependency factory must return MiddlewareDependencies")
        return dependencies


_REQUEST_DEPENDENCIES_KEY = "zhiji.middleware_dependencies"


def _request_dependencies(request: Request) -> MiddlewareDependencies:
    state = request.scope.setdefault("state", {})
    dependencies = state.get(_REQUEST_DEPENDENCIES_KEY)
    if dependencies is None:
        dependencies = _current_dependencies()
        state[_REQUEST_DEPENDENCIES_KEY] = dependencies
    if not isinstance(dependencies, MiddlewareDependencies):
        raise TypeError("request middleware dependencies are invalid")
    return dependencies


async def api_auth(request: Request, call_next):
    """Require a configured API token for protected remote requests."""
    dependencies = _request_dependencies(request)
    client_host = request.client.host if request.client else None
    if dependencies.requires_token_for_request(request.url.path, client_host):
        token = dependencies.api_token()
        if request.method == "OPTIONS":
            return await call_next(request)
        if not token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if not dependencies.compare_digest(dependencies.request_token(request), token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


async def spa_fallback(request: Request, call_next):
    """Serve the SPA entry point for missing public frontend routes."""
    dependencies = _request_dependencies(request)
    response = await call_next(request)
    if (
        dependencies.has_frontend
        and response.status_code == 404
        and not getattr(request.state, "protected_path", False)
    ):
        response = FileResponse(dependencies.frontend_dist / "index.html")
    if dependencies.has_frontend and not request.url.path.startswith("/api"):
        path = request.url.path
        if path in ("", "/") or path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
    return response
