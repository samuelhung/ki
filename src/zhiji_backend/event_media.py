"""Safe event media lookup and cleanup helpers."""
from __future__ import annotations

import logging
from pathlib import Path

from . import api_middleware
from .media_capability import create_video_url
from .security.artifacts import ArtifactOpenError, open_regular_under
from .security.constraints import safe_identifier
from .security.paths import safe_unlink_under

logger = logging.getLogger(__name__)


def add_video_url(event: dict[str, object], ingest_root: Path) -> None:
    video_path = event.get("video_path")
    api_token = api_middleware.api_token()
    if not isinstance(video_path, str) or not video_path or not api_token:
        return
    filename = Path(video_path).name
    try:
        safe_identifier(filename)
        opened = open_regular_under(ingest_root, "videos", filename)
    except (ArtifactOpenError, ValueError):
        return
    opened.close()
    video_url = create_video_url(filename, api_token=api_token)
    if video_url:
        event["video_url"] = video_url


def safe_unlink(path_value: str | None, root: Path) -> None:
    if not path_value:
        return
    try:
        safe_unlink_under(root, Path(path_value).expanduser())
    except Exception:
        logger.warning("Refusing to delete unsafe ingest artifact", exc_info=True)
