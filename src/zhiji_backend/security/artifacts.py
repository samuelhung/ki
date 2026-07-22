"""Descriptor-pinned serving for public filesystem artifacts."""
from __future__ import annotations

import email.utils
import errno
import mimetypes
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

import anyio
from starlette.datastructures import Headers
from starlette.responses import Response


_CHUNK_SIZE = 64 * 1024
_ASCII_DIGITS = re.compile(r"[0-9]+\Z", re.ASCII)


class ArtifactOpenError(ValueError):
    """Raised when an artifact cannot be opened beneath its approved root."""


@dataclass
class OpenedArtifact:
    fd: int
    stat_result: os.stat_result

    def close(self) -> None:
        if self.fd < 0:
            return
        fd, self.fd = self.fd, -1
        os.close(fd)


def _component(value: os.PathLike[str] | str) -> str:
    component = os.fspath(value)
    if (
        not component
        or component in {".", ".."}
        or "/" in component
        or "\\" in component
        or "\x00" in component
    ):
        raise ArtifactOpenError("invalid artifact component")
    return component


def open_regular_under(
    root: os.PathLike[str] | str, *parts: os.PathLike[str] | str
) -> OpenedArtifact:
    """Open a regular file beneath root without following any symlink."""
    if not parts:
        raise ArtifactOpenError("artifact path is required")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    directory_fd = -1
    file_fd = -1
    try:
        directory_fd = os.open(Path(root).expanduser(), directory_flags)
        for part in parts[:-1]:
            next_fd = os.open(_component(part), directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd

        file_fd = os.open(_component(parts[-1]), file_flags, dir_fd=directory_fd)
        file_stat = os.fstat(file_fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ArtifactOpenError("regular artifact file required")
        opened = OpenedArtifact(fd=file_fd, stat_result=file_stat)
        file_fd = -1
        return opened
    except ArtifactOpenError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise ArtifactOpenError("artifact is unavailable") from exc
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if directory_fd >= 0:
            os.close(directory_fd)


def _single_range(value: str | None, size: int) -> tuple[int, int, int]:
    if value is None:
        return 200, 0, max(0, size - 1)
    if not value.startswith("bytes=") or "," in value or size == 0:
        return 416, 0, -1

    spec = value[6:]
    if spec.count("-") != 1:
        return 416, 0, -1
    start_text, end_text = spec.split("-", 1)
    if not start_text and not end_text:
        return 416, 0, -1
    if start_text and not _ASCII_DIGITS.fullmatch(start_text):
        return 416, 0, -1
    if end_text and not _ASCII_DIGITS.fullmatch(end_text):
        return 416, 0, -1
    try:
        if not start_text:
            suffix = int(end_text)
            if suffix <= 0:
                return 416, 0, -1
            start = max(0, size - suffix)
            end = size - 1
        else:
            start = int(start_text)
            if start < 0 or start >= size:
                return 416, 0, -1
            end = int(end_text) if end_text else size - 1
            if end < start:
                return 416, 0, -1
            end = min(end, size - 1)
    except ValueError:
        return 416, 0, -1
    return 206, start, end


def _http_date_timestamp(value: str) -> float | None:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        from datetime import timezone

        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        return parsed.timestamp()
    except (OverflowError, OSError, ValueError):
        return None


def _weak_etag_value(value: str) -> str:
    candidate = value.strip()
    if candidate[:2].lower() == "w/":
        candidate = candidate[2:].strip()
    return candidate


def _if_none_match_matches(value: str, etag: str) -> bool:
    for candidate in value.split(","):
        candidate = candidate.strip()
        if candidate == "*" or _weak_etag_value(candidate) == etag:
            return True
    return False


def _not_modified(headers: Headers, *, etag: str, modified_at: float) -> bool:
    if_none_match = headers.get("if-none-match")
    if if_none_match is not None:
        return _if_none_match_matches(if_none_match, etag)

    if_modified_since = headers.get("if-modified-since")
    if if_modified_since is None:
        return False
    timestamp = _http_date_timestamp(if_modified_since)
    return timestamp is not None and int(modified_at) <= int(timestamp)


def _if_range_matches(value: str, *, etag: str, modified_at: float) -> bool:
    candidate = value.strip()
    if candidate[:2].lower() == "w/":
        return False
    if candidate.startswith('"'):
        return candidate == etag
    timestamp = _http_date_timestamp(candidate)
    return timestamp is not None and int(modified_at) == int(timestamp)


class PinnedFileResponse(Response):
    """Serve GET, HEAD, and one byte range from an already-open file."""

    def __init__(self, opened: OpenedArtifact, *, filename: str) -> None:
        self.opened = opened
        file_stat = opened.stat_result
        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_stat.st_size),
            "ETag": f'"{file_stat.st_mtime_ns:x}-{file_stat.st_size:x}-{file_stat.st_ino:x}"',
            "Last-Modified": email.utils.formatdate(file_stat.st_mtime, usegmt=True),
        }
        super().__init__(content=b"", media_type=media_type, headers=headers)

    async def _stream_body(
        self, send, *, offset: int, remaining: int
    ) -> None:
        if remaining == 0:
            await send({"type": "http.response.body", "body": b""})
            return

        while remaining > 0:
            chunk = os.pread(
                self.opened.fd, min(_CHUNK_SIZE, remaining), offset
            )
            if not chunk:
                raise OSError(errno.EIO, "artifact changed while serving")
            remaining -= len(chunk)
            offset += len(chunk)
            await send(
                {
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": remaining > 0,
                }
            )

    async def _stream_until_disconnect(
        self, receive, send, *, offset: int, remaining: int
    ) -> None:
        async with anyio.create_task_group() as task_group:

            async def watch_disconnect() -> None:
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        task_group.cancel_scope.cancel()
                        return

            task_group.start_soon(watch_disconnect)
            await anyio.sleep(0)
            try:
                await self._stream_body(send, offset=offset, remaining=remaining)
            finally:
                task_group.cancel_scope.cancel()

    async def __call__(self, scope, receive, send) -> None:
        try:
            file_stat = self.opened.stat_result
            size = file_stat.st_size
            request_headers = Headers(scope=scope)
            etag = self.headers["etag"]
            if _not_modified(
                request_headers, etag=etag, modified_at=file_stat.st_mtime
            ):
                self.status_code = 304
                if "content-length" in self.headers:
                    del self.headers["content-length"]
                await send(
                    {
                        "type": "http.response.start",
                        "status": self.status_code,
                        "headers": self.raw_headers,
                    }
                )
                await send({"type": "http.response.body", "body": b""})
                return

            range_header = request_headers.get("range")
            if_range = request_headers.get("if-range")
            if range_header is not None and if_range is not None:
                if not _if_range_matches(
                    if_range, etag=etag, modified_at=file_stat.st_mtime
                ):
                    range_header = None

            status, start, end = _single_range(range_header, size)
            self.status_code = status
            if status == 416:
                self.headers["content-length"] = "0"
                self.headers["content-range"] = f"bytes */{size}"
            elif status == 206:
                self.headers["content-length"] = str(end - start + 1)
                self.headers["content-range"] = f"bytes {start}-{end}/{size}"
            else:
                self.headers["content-length"] = str(size)

            await send(
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                }
            )
            if scope["method"].upper() == "HEAD" or status == 416:
                await send({"type": "http.response.body", "body": b""})
                return

            remaining = end - start + 1 if status == 206 else size
            offset = start if status == 206 else 0
            await self._stream_until_disconnect(
                receive, send, offset=offset, remaining=remaining
            )
        finally:
            self.opened.close()
