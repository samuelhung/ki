from __future__ import annotations

from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

PUBLIC_INGEST_ARTIFACTS = frozenset(
    {"videos", "audio", "documents", "transcripts", "summaries"}
)


async def retired_digest_endpoint(*, json_response=JSONResponse):
    return json_response({"detail": "Not Found"}, status_code=404)


async def serve_ingest_artifact(
    kind: str,
    filename: str,
    *,
    public_ingest_artifacts: Collection[str],
    ingest_root: Any,
    safe_identifier: Callable[[str], str],
    open_regular_under: Callable[..., Any],
    pinned_file_response: Callable[..., Any],
    artifact_open_error: type[BaseException],
    http_exception: type[HTTPException],
):
    if kind not in public_ingest_artifacts:
        raise http_exception(status_code=404, detail="Not Found")
    if "/" in filename or "\\" in filename:
        raise http_exception(status_code=422, detail="Invalid artifact path")
    try:
        safe_identifier(filename)
    except ValueError as exc:
        raise http_exception(status_code=422, detail="Invalid artifact path") from exc
    try:
        opened = open_regular_under(ingest_root, kind, filename)
    except artifact_open_error:
        raise http_exception(status_code=404, detail="Not Found") from None
    try:
        return pinned_file_response(opened, filename=filename)
    except BaseException:
        opened.close()
        raise


async def serve_signed_video(
    filename: str,
    expires: str,
    signature: str,
    *,
    ingest_root: Any,
    api_token: Callable[[], str],
    verify_video_capability: Callable[..., bool],
    open_regular_under: Callable[..., Any],
    pinned_file_response: Callable[..., Any],
    artifact_open_error: type[BaseException],
    http_exception: type[HTTPException],
):
    if not verify_video_capability(
        filename,
        expires=expires,
        signature=signature,
        api_token=api_token(),
    ):
        raise http_exception(status_code=404, detail="Not Found")
    try:
        opened = open_regular_under(ingest_root, "videos", filename)
    except artifact_open_error:
        raise http_exception(status_code=404, detail="Not Found") from None
    try:
        return pinned_file_response(opened, filename=filename)
    except BaseException:
        opened.close()
        raise


async def serve_release(
    filename: str,
    *,
    releases_dir: Any,
    path_type: type[Path],
    safe_identifier: Callable[[str], str],
    open_regular_under: Callable[..., Any],
    pinned_file_response: Callable[..., Any],
    artifact_open_error: type[BaseException],
    http_exception: type[HTTPException],
):
    requested = path_type(filename)
    if any(part in {".", ".."} for part in requested.parts):
        raise http_exception(status_code=422, detail="Invalid release path")
    if requested.name != filename or requested.suffix.lower() not in {".dmg", ".xml"}:
        raise http_exception(status_code=404, detail="Not Found")
    try:
        safe_identifier(filename)
    except ValueError as exc:
        raise http_exception(status_code=422, detail="Invalid release path") from exc
    try:
        opened = open_regular_under(releases_dir, filename)
    except artifact_open_error:
        raise http_exception(status_code=404, detail="Not Found") from None
    try:
        return pinned_file_response(opened, filename=filename)
    except BaseException:
        opened.close()
        raise


def mount_frontend(
    app: Any,
    *,
    frontend_dist: Path,
    static_files=StaticFiles,
) -> bool:
    if not frontend_dist.exists():
        return False
    app.mount(
        "/",
        static_files(directory=frontend_dist, html=True),
        name="frontend",
    )
    return True
