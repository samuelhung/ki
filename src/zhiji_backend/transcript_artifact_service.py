"""Atomic publication for transcript compatibility artifacts."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from .security.constraints import safe_identifier
from .security.paths import resolve_under


def publish_transcript_artifact(
    event_id: str, content: str, *, transcripts_dir: Path
) -> None:
    safe_identifier(event_id)
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    target = resolve_under(transcripts_dir, f"{event_id}.md", must_exist=False)
    stage = resolve_under(
        transcripts_dir, f".{event_id}.{uuid.uuid4().hex}.tmp", must_exist=False
    )
    try:
        stage.write_text(content, encoding="utf-8")
        os.replace(stage, target)
    finally:
        if stage.exists():
            stage.unlink()
