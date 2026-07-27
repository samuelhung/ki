"""Bounded Douyin video download and destination cleanup."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import requests  # type: ignore

from ..security.file_intake import REMOTE_VIDEO_MAX_BYTES
from . import remote_transport

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
MAX_VIDEO_REDIRECTS = 5


def _declared_size(response) -> int | None:
    headers = getattr(response, "headers", None)
    value = headers.get("Content-Length") if hasattr(headers, "get") else None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _download_whole(
    url: str,
    dest: Path,
    headers: dict,
    s: requests.Session | None,
    *,
    max_bytes: int,
    resolver: Callable[[str, int], list[str]],
    max_redirects: int,
    connection_factory,
    safe_get_fn=None,
    declared_size_fn=None,
) -> bool:
    """Download one bounded response, returning False for transport failures."""
    get_safely = safe_get_fn or remote_transport._safe_get
    declared_size = declared_size_fn or _declared_size
    resp = None
    try:
        resp = get_safely(
            s,
            url,
            headers=headers,
            timeout=(30, 600),
            resolver=resolver,
            max_redirects=max_redirects,
            connection_factory=connection_factory,
        )
        resp.raise_for_status()
        declared = declared_size(resp)
        if declared is not None and declared > max_bytes:
            raise ValueError("远程视频大小超过限制")
        downloaded = 0
        with open(dest, "wb") as handle:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                downloaded += len(chunk)
                if downloaded > max_bytes:
                    raise ValueError("远程视频大小超过限制")
                handle.write(chunk)
        return True
    except ValueError:
        dest.unlink(missing_ok=True)
        raise
    except Exception:
        dest.unlink(missing_ok=True)
        return False
    finally:
        if resp is not None:
            resp.close()


def download_video(
    url: str,
    dest: Path,
    session: requests.Session | None = None,
    *,
    max_bytes: int = REMOTE_VIDEO_MAX_BYTES,
    resolver: Callable[[str, int], list[str]] = remote_transport._resolve_host,
    max_redirects: int = MAX_VIDEO_REDIRECTS,
    connection_factory=remote_transport.create_pinned_connection,
    mobile_ua: str = MOBILE_UA,
    safe_get_fn=None,
    download_whole_fn=None,
    declared_size_fn=None,
) -> Path:
    """Download a video with byte limits and remove incomplete destinations."""
    get_safely = safe_get_fn or remote_transport._safe_get
    download_whole = download_whole_fn or _download_whole
    declared_size = declared_size_fn or _declared_size
    headers = {
        "User-Agent": mobile_ua,
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
    }
    total_size = 0
    range_supported = True
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        if total_size == 0 or not range_supported:
            if download_whole(
                url,
                dest,
                headers,
                session,
                max_bytes=max_bytes,
                resolver=resolver,
                max_redirects=max_redirects,
                connection_factory=connection_factory,
            ):
                return dest
            total_size = 0

        segment_size = 1024 * 1024
        downloaded = 0
        range_rejected = False

        with open(dest, "wb") as handle:
            while True:
                if total_size > 0 and downloaded >= total_size:
                    break

                range_start = downloaded
                range_end = (
                    downloaded + segment_size - 1
                    if total_size == 0
                    else min(downloaded + segment_size, total_size - 1)
                )
                segment_headers = {
                    **headers,
                    "Range": f"bytes={range_start}-{range_end}",
                }
                segment = get_safely(
                    session,
                    url,
                    headers=segment_headers,
                    timeout=(30, 120),
                    resolver=resolver,
                    max_redirects=max_redirects,
                    connection_factory=connection_factory,
                )
                try:
                    if segment.status_code not in (200, 206):
                        range_rejected = True
                    else:
                        declared = declared_size(segment)
                        if declared is not None and declared > max_bytes:
                            raise ValueError("远程视频大小超过限制")
                        segment_length = 0
                        for chunk in segment.iter_content(chunk_size=65536):
                            if not chunk:
                                continue
                            segment_length += len(chunk)
                            downloaded += len(chunk)
                            if downloaded > max_bytes:
                                raise ValueError("远程视频大小超过限制")
                            handle.write(chunk)
                finally:
                    segment.close()

                if range_rejected:
                    handle.close()
                    if download_whole(
                        url,
                        dest,
                        headers,
                        session,
                        max_bytes=max_bytes,
                        resolver=resolver,
                        max_redirects=max_redirects,
                        connection_factory=connection_factory,
                    ):
                        return dest
                    raise RuntimeError("Whole-file fallback download failed")

                if segment.status_code == 200:
                    break
                if total_size == 0 and segment_length < segment_size * 0.9:
                    break

        return dest
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
