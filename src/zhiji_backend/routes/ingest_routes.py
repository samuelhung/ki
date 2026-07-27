"""Unified ingest API endpoints for douyin links, audio, video, and documents."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from .. import ingest_service
from ..db import connect, init_db
from ..paths import INGEST_ROOT
from ..security.constraints import MAX_PAGE_SIZE, SafeIdentifier, safe_identifier
from ..security.file_intake import (
    kind_for_filename,
    max_bytes_for_kind,
    stream_upload_to_temp,
    validate_file,
)
from ..security.paths import resolve_under
from ..security.redaction import classify_task_error, sanitize_task_error
from ..task_queue import enqueue as enqueue_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["ingest"])

TRANSCRIPTS_DIR = INGEST_ROOT / "transcripts"
SUMMARIES_DIR = INGEST_ROOT / "summaries"
VIDEOS_DIR = INGEST_ROOT / "videos"
AUDIO_DIR = INGEST_ROOT / "audio"
DOCUMENTS_DIR = INGEST_ROOT / "documents"


class DouyinIngestRequest(BaseModel):
    share_text: str
    topic: str = "uncategorized"


class ConceptCreateRequest(BaseModel):
    title: str
    topic: str = "uncategorized"
    description: str = ""


@router.post("/douyin")
def ingest_douyin(req: DouyinIngestRequest):
    """Submit a douyin share link for ingestion."""
    return _create_event("douyin_share", req.share_text, req.topic)


@router.post("/concept")
def ingest_concept(req: ConceptCreateRequest):
    """Create a concept entry. AI auto-completes if no description provided."""
    return _create_concept(req.title, req.topic, req.description)


_FILE_TYPE_MAP = {
    "document": {".md", ".txt", ".markdown", ".json", ".csv", ".log", ".pdf", ".epub"},
    "audio_file": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"},
    "video_file": {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mts", ".ts", ".flv"},
}


def _detect_ingest_type(filename: str | None) -> str | None:
    """Detect ingest type from file extension. Returns None for unsupported formats."""
    return ingest_service.detect_ingest_type(filename, file_type_map=_FILE_TYPE_MAP)


@router.post("/file")
def ingest_file(
    file: UploadFile = File(...),
    title: str = Form(""),
    topic: str = Form("uncategorized"),
):
    """Submit an audio, video, or document file for ingestion. Type is auto-detected."""
    ingest_type = _detect_ingest_type(file.filename)
    if ingest_type is None:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {Path(file.filename or '').suffix or '未知'}。"
            f"支持的格式: 视频 {', '.join(sorted(_FILE_TYPE_MAP['video_file']))}，"
            f"音频 {', '.join(sorted(_FILE_TYPE_MAP['audio_file']))}，"
            f"文档 {', '.join(sorted(_FILE_TYPE_MAP['document']))}",
        )
    filename = file.filename or "upload.bin"
    kind = kind_for_filename(filename)
    if kind is None:
        raise HTTPException(
            status_code=422, detail="文件内容与扩展名不匹配或文件已损坏"
        )
    tmp_path = stream_upload_to_temp(
        file,
        max_bytes=max_bytes_for_kind(kind),
        suffix=Path(filename).suffix,
    )
    try:
        validate_file(tmp_path, filename=filename)
        return _create_event(ingest_type, tmp_path, topic, title=title)
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/queue")
def ingest_queue(limit: int = Query(30, ge=1, le=MAX_PAGE_SIZE)):
    """List recent ingest tasks with event info for the queue UI panel."""
    with connect() as conn:
        count_rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM ingest_tasks GROUP BY status"
        ).fetchall()
        rows = conn.execute(
            """SELECT t.id, t.event_id, t.ingest_type, t.status, t.error,
                      t.payload_json, t.created_at, t.started_at, t.finished_at,
                      e.title, e.progress_stages
               FROM ingest_tasks t
               LEFT JOIN events e ON e.id = t.event_id
               ORDER BY CASE t.status
                 WHEN 'running' THEN 0
                 WHEN 'error' THEN 1
                 WHEN 'pending' THEN 2
                 ELSE 3
               END, t.created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    status_counts = {"pending": 0, "running": 0, "done": 0, "error": 0}
    for row in count_rows:
        status_counts[row["status"]] = row["count"]
    items = []
    for row in rows:
        item = dict(row)
        if item.get("progress_stages"):
            try:
                item["progress_stages"] = json.loads(item["progress_stages"])
            except (json.JSONDecodeError, TypeError):
                item["progress_stages"] = []
        items.append(item)
    return {"items": items, "status_counts": status_counts}


@router.get("/status/{event_id}")
def ingest_status(event_id: SafeIdentifier):
    """Query the status of an ingest event."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, status, raw_summary, progress_stages, created_at, source_id FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    result = dict(row)
    if result.get("raw_summary"):
        result["raw_summary_preview"] = result["raw_summary"][:200]
    if result.get("progress_stages"):
        try:
            result["progress_stages"] = json.loads(result["progress_stages"])
        except (json.JSONDecodeError, TypeError):
            result["progress_stages"] = []
    return result


@router.delete("/clear-old")
def clear_old_ingest():
    """Delete ingest events (douyin/user-upload) created before today."""
    init_db()
    with connect() as conn:
        result = conn.execute(
            "DELETE FROM events WHERE source_id IN ('douyin', 'user-upload') AND date(created_at) < date('now')"
        )
        deleted = result.rowcount if hasattr(result, "rowcount") else conn.total_changes
    return {"deleted": deleted}


@router.delete("/queue/{task_id}")
def delete_queue_task(task_id: SafeIdentifier):
    """Delete a single ingest task. Also cleans up its associated event."""
    with connect() as conn:
        row = conn.execute(
            "SELECT event_id FROM ingest_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            return {"deleted": task_id, "missing": True}
        event_id = row["event_id"]
        conn.execute("DELETE FROM ingest_tasks WHERE id = ?", (task_id,))
        remaining = conn.execute(
            "SELECT COUNT(*) as cnt FROM ingest_tasks WHERE event_id = ?", (event_id,)
        ).fetchone()["cnt"]
        if remaining == 0:
            conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    return {"deleted": task_id, "missing": False}


@router.post("/queue/{task_id}/retry")
def retry_queue_task(task_id: SafeIdentifier):
    """Retry a failed task — reset to pending. Also cleans up stuck event status."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, event_id, status FROM ingest_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        if row["status"] not in ("error", "done"):
            raise HTTPException(
                status_code=400, detail=f"Task is {row['status']}, not retryable"
            )
        conn.execute(
            "UPDATE ingest_tasks SET status = 'pending', error = NULL, "
            "started_at = NULL, finished_at = NULL, retry_count = COALESCE(retry_count, 0) + 1 WHERE id = ?",
            (task_id,),
        )
        if row["event_id"]:
            event = conn.execute(
                "SELECT status FROM events WHERE id = ?", (row["event_id"],)
            ).fetchone()
            if event and event["status"] == "processing":
                conn.execute(
                    "UPDATE events SET status = 'pending' WHERE id = ?",
                    (row["event_id"],),
                )
    return {"retried": task_id, "status": "pending"}


def _md5_file(path: Path) -> str | None:
    """Compatibility facade for callers that patch the route helper."""
    return ingest_service.md5_file(path)


def _set_progress(event_id: str, stages: list[dict]) -> None:
    """Compatibility facade for progress persistence."""
    return ingest_service.set_progress(event_id, stages, connect_fn=connect)


def _create_event(
    ingest_type: str,
    content,
    topic: str,
    title: str = "",
    content_type: str = "event",
) -> dict:
    """Create an event and enqueue its persistent ingest task."""
    return ingest_service.create_event(
        ingest_type,
        content,
        topic,
        title,
        content_type,
        dependencies={
            "init_db_fn": init_db,
            "connect_fn": connect,
            "enqueue_fn": enqueue_task,
        },
    )


def _create_concept(
    title: str,
    topic: str,
    description: str = "",
    force_ai: bool = False,
    context_docs: list[dict[str, str]] | None = None,
) -> dict:
    """Create a concept while preserving the route-level compatibility seam."""
    return ingest_service.create_concept(
        title,
        topic,
        description,
        force_ai,
        context_docs,
        dependencies={
            "init_db_fn": init_db,
            "connect_fn": connect,
            "ingest_root": INGEST_ROOT,
            "logger": logger,
        },
    )


def _process_ingest(event_id: str, ingest_type: str, content, topic: str, title: str):
    """Run the synchronous pipeline through the extracted application service."""
    return ingest_service.process_ingest(
        event_id,
        ingest_type,
        content,
        topic,
        title,
        dependencies={
            "connect_fn": connect,
            "transcripts_dir": TRANSCRIPTS_DIR,
            "summaries_dir": SUMMARIES_DIR,
            "videos_dir": VIDEOS_DIR,
            "audio_dir": AUDIO_DIR,
            "documents_dir": DOCUMENTS_DIR,
            "resolve_under_fn": resolve_under,
            "set_progress_fn": _set_progress,
            "md5_file_fn": _md5_file,
            "safe_identifier_fn": safe_identifier,
            "sanitize_task_error_fn": sanitize_task_error,
            "classify_task_error_fn": classify_task_error,
            "logger": logger,
            "module_name": __name__,
        },
    )
