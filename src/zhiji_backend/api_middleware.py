from __future__ import annotations

import hmac
import os

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
_HAS_FRONTEND = FRONTEND_DIST.exists()


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
        if is_protected_path(request.url.path):
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


async def api_auth(request: Request, call_next):
    """Require a configured API token for protected remote requests."""
    client_host = request.client.host if request.client else None
    if requires_token_for_request(request.url.path, client_host):
        token = api_token()
        if request.method == "OPTIONS":
            return await call_next(request)
        if not token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if not hmac.compare_digest(request_token(request), token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


async def spa_fallback(request: Request, call_next):
    """Serve the SPA entry point for missing public frontend routes."""
    response = await call_next(request)
    if (
        _HAS_FRONTEND
        and response.status_code == 404
        and not getattr(request.state, "protected_path", False)
    ):
        response = FileResponse(FRONTEND_DIST / "index.html")
    if _HAS_FRONTEND and not request.url.path.startswith("/api"):
        path = request.url.path
        if path in ("", "/") or path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
    return response
