"""Short-lived capabilities for seekable video playback."""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from pathlib import Path
from urllib.parse import quote, urlencode

from .security.constraints import safe_identifier

MEDIA_URL_TTL_SECONDS = 30 * 60
MAX_CLOCK_SKEW_SECONDS = 30

_VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mts", ".ts", ".flv"}
)
_ASCII_DIGITS = re.compile(r"[0-9]+\Z", re.ASCII)
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def _valid_video_filename(filename: str) -> bool:
    try:
        safe_identifier(filename)
    except (TypeError, ValueError):
        return False
    return Path(filename).suffix.lower() in _VIDEO_EXTENSIONS


def _canonical_message(filename: str, expires: int) -> bytes:
    return f"ki-media-v1\nvideos\n{filename}\n{expires}".encode()


def _signature(filename: str, expires: int, api_token: str) -> str:
    return hmac.new(
        api_token.encode("utf-8"),
        _canonical_message(filename, expires),
        hashlib.sha256,
    ).hexdigest()


def create_video_url(
    filename: str,
    *,
    api_token: str,
    now: int | None = None,
) -> str | None:
    if not api_token or not _valid_video_filename(filename):
        return None
    current = int(time.time()) if now is None else int(now)
    expires = current + MEDIA_URL_TTL_SECONDS
    query = urlencode(
        {
            "expires": str(expires),
            "signature": _signature(filename, expires, api_token),
        }
    )
    return f"/media/videos/{quote(filename, safe='')}?{query}"


def verify_video_capability(
    filename: str,
    *,
    expires: str,
    signature: str,
    api_token: str,
    now: int | None = None,
) -> bool:
    if (
        not api_token
        or not _valid_video_filename(filename)
        or not isinstance(expires, str)
        or not _ASCII_DIGITS.fullmatch(expires)
        or not isinstance(signature, str)
        or not _HEX_SHA256.fullmatch(signature)
    ):
        return False

    current = int(time.time()) if now is None else int(now)
    expiry = int(expires)
    if expiry < current or expiry > current + MEDIA_URL_TTL_SECONDS + MAX_CLOCK_SKEW_SECONDS:
        return False

    expected = _signature(filename, expiry, api_token)
    return hmac.compare_digest(signature, expected)
