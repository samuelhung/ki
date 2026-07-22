"""Server-owned policy for OpenAI-compatible provider base URLs."""

from __future__ import annotations

import os
from urllib.parse import SplitResult, urlsplit, urlunsplit

from .config_manager import DEFAULT_AI_BASE_URL


def canonicalize_base_url(value: str) -> str:
    if not value or value != value.strip() or any(char in value for char in "\r\n\x00"):
        raise ValueError("invalid AI provider base URL")

    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid AI provider base URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("invalid AI provider base URL")
    if parsed.query or parsed.fragment:
        raise ValueError("invalid AI provider base URL")
    try:
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid AI provider base URL") from exc
    if not host:
        raise ValueError("invalid AI provider base URL")

    canonical_host = host.lower()
    if ":" in canonical_host:
        canonical_host = f"[{canonical_host}]"
    netloc = f"{canonical_host}:{port}" if port is not None else canonical_host
    path = parsed.path.rstrip("/")
    return urlunsplit(
        SplitResult(parsed.scheme.lower(), netloc, path, "", "")
    )


def allowed_base_urls() -> frozenset[str]:
    values = [DEFAULT_AI_BASE_URL]
    values.extend(
        item.strip()
        for item in os.getenv("KI_AI_BASE_URL_ALLOWLIST", "").split(",")
        if item.strip()
    )
    return frozenset(canonicalize_base_url(value) for value in values)


def validate_allowed_base_url(value: str) -> str:
    canonical = canonicalize_base_url(value)
    if canonical not in allowed_base_urls():
        raise ValueError("AI provider base URL is not allowed")
    return canonical
