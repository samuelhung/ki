"""Unified ingest API endpoints for douyin links, audio, video, and documents."""

import json
import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..db import connect, init_db
from ..task_queue import enqueue as enqueue_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

INGEST_ROOT = Path(__file__).resolve().parents[3] / "data" / "ingest"
TRANSCRIPTS_DIR = INGEST_ROOT / "transcripts"
SUMMARIES_DIR   = INGEST_ROOT / "summaries"
VIDEOS_DIR      = INGEST_ROOT / "videos"
AUDIO_DIR       = INGEST_ROOT / "audio"
DOCUMENTS_DIR   = INGEST_ROOT / "documents"


class DouyinIngestRequest(BaseModel):
    share_text: str
    topic: str = "uncategorized"


@router.post("/douyin")
def ingest_douyin(req: DouyinIngestRequest):
    """Submit a douyin share link for ingestion."""
    return _create_event("douyin_share", req.share_text, req.topic)


# ── File upload (audio / video / document) ──

# Supported file extensions, grouped by ingest type
_FILE_TYPE_MAP = {
    "document":   {".md", ".txt", ".markdown", ".json", ".csv", ".log"},
    "audio_file": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"},
    "video_file": {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mts", ".ts", ".flv"},
}


def _detect_ingest_type(filename: str | None) -> str | None:
    """Detect ingest type from file extension. Returns None for unsupported formats."""
    if not filename:
        return None
    suffix = Path(filename).suffix.lower()
    for itype, exts in _FILE_TYPE_MAP.items():
        if suffix in exts:
            return itype
    return None


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
    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(file.file.read())
        tmp.close()
        return _create_event(ingest_type, Path(tmp.name), topic, title=title)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise


# ── Status endpoint ──

@router.get("/status/{event_id}")
def ingest_status(event_id: str):
    """Query the status of an ingest event."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, status, raw_summary, progress_stages, created_at, source_id FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Event not found")

    d = dict(row)
    if d.get("raw_summary"):
        d["raw_summary_preview"] = d["raw_summary"][:200]
    if d.get("progress_stages"):
        try:
            d["progress_stages"] = json.loads(d["progress_stages"])
        except (json.JSONDecodeError, TypeError):
            d["progress_stages"] = []
    return d


# ── Clear old events ──

@router.delete("/clear-old")
def clear_old_ingest():
    """Delete ingest events (douyin/user-upload) created before today."""
    init_db()
    with connect() as conn:
        result = conn.execute(
            "DELETE FROM events WHERE source_id IN ('douyin', 'user-upload') AND date(created_at) < date('now')"
        )
        deleted = result.rowcount if hasattr(result, 'rowcount') else conn.total_changes
    return {"deleted": deleted}


# ── Internal helpers ──

def _set_progress(event_id: str, stages: list[dict]) -> None:
    """Write progress stages to the event record."""
    with connect() as conn:
        conn.execute(
            "UPDATE events SET progress_stages = ? WHERE id = ?",
            (json.dumps(stages, ensure_ascii=False), event_id),
        )


def _create_event(ingest_type: str, content, topic: str, title: str = "") -> dict:
    """Create an event record and enqueue persistent task for background processing."""
    init_db()

    event_id = f"evt-ingest-{uuid.uuid4().hex[:12]}"
    source_id = "douyin" if ingest_type == "douyin_share" else "user-upload"

    with connect() as conn:
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic,
               importance, actionability, decision, status)
               VALUES (?, ?, ?, '', ?, 4, 4, 'digest', 'processing')""",
            (event_id, source_id, title or "待处理", topic),
        )

    # Enqueue persistent task (survives server restart)
    enqueue_task(event_id, ingest_type, content, topic, title)

    return {
        "event_id": event_id,
        "status": "processing",
        "type": ingest_type,
    }


def _process_ingest(event_id: str, ingest_type: str, content, topic: str, title: str):
    """Background task: run the appropriate ingest pipeline."""
    work_dir = Path(tempfile.mkdtemp())
    try:
        if ingest_type == "document":
            from ..ingest.document import process_document

            stages = [
                {"key": "parse", "label": "解析文档", "status": "active"},
                {"key": "done", "label": "完成", "status": "pending"},
            ]
            _set_progress(event_id, stages)

            result = process_document(content, title=title, topic=topic)
            text = result["text"]

            stages[0]["status"] = "done"
            stages[1]["status"] = "active"
            _set_progress(event_id, stages)

        elif ingest_type in ("audio_file",):
            from ..ingest.volc_transcriber import transcribe

            stages = [
                {"key": "transcribe", "label": "语音转写", "status": "active"},
                {"key": "done", "label": "完成", "status": "pending"},
            ]
            _set_progress(event_id, stages)

            text = transcribe(Path(content))

            stages[0]["status"] = "done"
            stages[1]["status"] = "active"
            _set_progress(event_id, stages)

        elif ingest_type in ("video_file",):
            from ..ingest.media import extract_audio
            from ..ingest.volc_transcriber import transcribe

            stages = [
                {"key": "extract", "label": "提取音频", "status": "active"},
                {"key": "transcribe", "label": "语音转写", "status": "pending"},
                {"key": "done", "label": "完成", "status": "pending"},
            ]
            _set_progress(event_id, stages)

            # Persist video file before temp dir is cleaned up
            VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
            persistent_video = VIDEOS_DIR / f"{event_id}{Path(content).suffix}"
            shutil.copy2(content, persistent_video)

            audio_path = work_dir / "extracted.wav"
            extract_audio(Path(content), audio_path)
            stages[0]["status"] = "done"
            stages[1]["status"] = "active"
            _set_progress(event_id, stages)

            text = transcribe(audio_path)
            stages[1]["status"] = "done"
            stages[2]["status"] = "active"
            _set_progress(event_id, stages)

        elif ingest_type == "douyin_share":
            from ..ingest.douyin import parse_share_text, download_video
            from ..ingest.media import extract_audio
            from ..ingest.volc_transcriber import transcribe

            stages = [
                {"key": "parse", "label": "解析链接", "status": "active"},
                {"key": "download", "label": "下载视频", "status": "pending"},
                {"key": "extract", "label": "提取音频", "status": "pending"},
                {"key": "transcribe", "label": "语音转写", "status": "pending"},
                {"key": "summarize", "label": "AI 总结", "status": "pending"},
                {"key": "done", "label": "完成", "status": "pending"},
            ]
            _set_progress(event_id, stages)

            share_text = str(content)
            info = parse_share_text(share_text)
            stages[0]["status"] = "done"
            stages[1]["status"] = "active"
            _set_progress(event_id, stages)

            video_path = work_dir / "video.mp4"
            download_video(info["download_url"], video_path)
            
            # Persist video file (temp dir will be cleaned up)
            VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
            persistent_video = VIDEOS_DIR / f"{event_id}.mp4"
            shutil.copy2(video_path, persistent_video)
            
            stages[1]["status"] = "done"
            stages[2]["status"] = "active"
            _set_progress(event_id, stages)

            audio_path = work_dir / "audio.wav"
            extract_audio(video_path, audio_path)
            stages[2]["status"] = "done"
            stages[3]["status"] = "active"
            _set_progress(event_id, stages)

            text = transcribe(audio_path)
            stages[3]["status"] = "done"
            stages[4]["status"] = "active"
            _set_progress(event_id, stages)

            # Update title from douyin metadata
            if not title:
                title = info.get("platform_title", "")

            # Update URL with share URL
            with connect() as conn:
                conn.execute(
                    "UPDATE events SET url = ? WHERE id = ?",
                    (info.get("share_url", ""), event_id),
                )
        else:
            raise ValueError(f"Unknown ingest type: {ingest_type}")

        # Save transcription to disk
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        (TRANSCRIPTS_DIR / f"{event_id}.md").write_text(text, encoding="utf-8")

        # AI summarization for all text-producing ingest types
        ai_summary = None
        if ingest_type in ("douyin_share", "video_file", "audio_file", "document"):
            try:
                from ..summarizer import summarize_transcript
                ai_summary = summarize_transcript(text, title=title)
                if ai_summary is not None:
                    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
                    (SUMMARIES_DIR / f"{event_id}.md").write_text(ai_summary, encoding="utf-8")
                else:
                    logger.warning("AI summarization returned None for %s — API may be unavailable", event_id)
            except Exception as e:
                logger.warning("AI summarization failed for %s (%s): %s", event_id, ingest_type, e)

        # Build file path columns
        if ingest_type == "video_file":
            video_path = str(VIDEOS_DIR / f"{event_id}{Path(content).suffix}")
            audio_path_col = None
            document_path_col = None
        elif ingest_type == "douyin_share":
            video_path = str(VIDEOS_DIR / f"{event_id}.mp4")
            audio_path_col = None
            document_path_col = None
        elif ingest_type == "audio_file":
            video_path = None
            AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            persistent_audio = AUDIO_DIR / f"{event_id}{Path(content).suffix}"
            shutil.copy2(content, persistent_audio)
            audio_path_col = str(persistent_audio)
            document_path_col = None
        elif ingest_type == "document":
            video_path = None
            audio_path_col = None
            DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
            persistent_doc = DOCUMENTS_DIR / f"{event_id}{Path(content).suffix}"
            shutil.copy2(content, persistent_doc)
            document_path_col = str(persistent_doc)
        else:
            video_path = None
            audio_path_col = None
            document_path_col = None

        # Update event
        with connect() as conn:
            conn.execute(
                """UPDATE events SET raw_summary = ?, ai_summary = COALESCE(?, ai_summary),
                   status = 'new', last_error = NULL,
                   video_path = ?, audio_path = ?, document_path = ?,
                   title = CASE WHEN title = '待处理' OR title = '' THEN ? ELSE title END
                   WHERE id = ?""",
                (text, ai_summary, video_path, audio_path_col, document_path_col, title or "待处理", event_id),
            )

        # Auto-classify into cognitive layer (outside the connection block —
        # classifier manages its own DB connection)
        try:
            from ..classifier import classify_event as _classify_event
            _classify_event(event_id)
        except Exception:
            logger.warning("Classification failed for %s — non-blocking", event_id, exc_info=True)

    except Exception as e:
        logger.exception("Ingest pipeline failed for %s (%s): %s", event_id, ingest_type, e)
        error_msg = str(e)[:500] if str(e) else "unknown error"
        with connect() as conn:
            conn.execute(
                "UPDATE events SET status = 'error', last_error = ? WHERE id = ?",
                (error_msg, event_id),
            )
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
