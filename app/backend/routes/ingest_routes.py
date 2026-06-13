"""Unified ingest API endpoints for douyin links, audio, video, and documents."""

import json
import logging
import re
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


class ConceptCreateRequest(BaseModel):
    title: str
    topic: str = "uncategorized"
    description: str = ""  # optional manual explanation; AI auto-completes if empty


@router.post("/douyin")
def ingest_douyin(req: DouyinIngestRequest):
    """Submit a douyin share link for ingestion."""
    return _create_event("douyin_share", req.share_text, req.topic)


@router.post("/concept")
def ingest_concept(req: ConceptCreateRequest):
    """Create a concept entry. AI auto-completes if no description provided."""
    return _create_concept(req.title, req.topic, req.description)


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


# ── Queue endpoint ──

@router.get("/queue")
def ingest_queue(limit: int = 30):
    """List recent ingest tasks with event info for the queue UI panel."""
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """SELECT t.id, t.event_id, t.ingest_type, t.status, t.error,
                      t.payload_json, t.created_at, t.started_at, t.finished_at,
                      e.title, e.progress_stages
               FROM ingest_tasks t
               LEFT JOIN events e ON e.id = t.event_id
               ORDER BY t.created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    items = []
    for row in rows:
        item = dict(row)
        if item.get("progress_stages"):
            try:
                item["progress_stages"] = json.loads(item["progress_stages"])
            except (json.JSONDecodeError, TypeError):
                item["progress_stages"] = []
        items.append(item)
    return {"items": items}


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


@router.delete("/queue/{task_id}")
def delete_queue_task(task_id: str):
    """Delete a single ingest task. Also cleans up its associated event."""
    init_db()
    with connect() as conn:
        # Look up the event_id before deleting
        row = conn.execute(
            "SELECT event_id FROM ingest_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        event_id = row["event_id"]

        # Delete the task
        conn.execute("DELETE FROM ingest_tasks WHERE id = ?", (task_id,))

        # Delete the associated event if no other tasks reference it
        remaining = conn.execute(
            "SELECT COUNT(*) as cnt FROM ingest_tasks WHERE event_id = ?", (event_id,)
        ).fetchone()["cnt"]
        if remaining == 0:
            conn.execute("DELETE FROM events WHERE id = ?", (event_id,))

    return {"deleted": task_id}


@router.post("/queue/{task_id}/retry")
def retry_queue_task(task_id: str):
    """Retry a failed task — reset to pending. Also cleans up stuck event status."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, event_id, status FROM ingest_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        if row["status"] not in ("error", "done"):
            raise HTTPException(status_code=400, detail=f"Task is {row['status']}, not retryable")

        # Reset task
        conn.execute(
            "UPDATE ingest_tasks SET status = 'pending', error = NULL, "
            "started_at = NULL, finished_at = NULL, retry_count = COALESCE(retry_count, 0) + 1 WHERE id = ?",
            (task_id,),
        )

        # Clean up orphaned event (stuck in 'processing')
        if row["event_id"]:
            ev = conn.execute(
                "SELECT status FROM events WHERE id = ?", (row["event_id"],)
            ).fetchone()
            if ev and ev["status"] == "processing":
                conn.execute(
                    "UPDATE events SET status = 'pending' WHERE id = ?",
                    (row["event_id"],),
                )

    return {"retried": task_id, "status": "pending"}


# ── Internal helpers ──

def _set_progress(event_id: str, stages: list[dict]) -> None:
    """Write progress stages to the event record."""
    with connect() as conn:
        conn.execute(
            "UPDATE events SET progress_stages = ? WHERE id = ?",
            (json.dumps(stages, ensure_ascii=False), event_id),
        )


def _create_event(ingest_type: str, content, topic: str, title: str = "", content_type: str = "event") -> dict:
    """Create an event record and enqueue persistent task for background processing."""
    init_db()

    event_id = f"evt-ingest-{uuid.uuid4().hex[:12]}"
    source_id = "douyin" if ingest_type == "douyin_share" else "user-upload"

    with connect() as conn:
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic,
               importance, actionability, decision, status, content_type)
               VALUES (?, ?, ?, '', ?, 4, 4, 'digest', 'processing', ?)""",
            (event_id, source_id, title or "待处理", topic, content_type),
        )

    # Enqueue persistent task (survives server restart)
    enqueue_task(event_id, ingest_type, content, topic, title)

    return {
        "event_id": event_id,
        "status": "processing",
        "type": ingest_type,
    }


def _create_concept(title: str, topic: str, description: str = "", force_ai: bool = False,
                     context_docs: list[dict[str, str]] | None = None) -> dict:
    """Create a concept entry. AI auto-completes if no description provided.
    When force_ai=True, always run AI completion with description as seed context.
    When context_docs is provided, inject original document excerpts for grounded explanation.
    Auto-classifies topic if not provided by user."""
    init_db()
    from ..deepseek_client import chat
    from ..classifier import classify_content

    concept_id = f"evt-concept-{uuid.uuid4().hex[:12]}"
    from datetime import datetime, timezone
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    # Build source doc context block with [文档N] indexing
    docs_block = ""
    docs_index = ""
    if context_docs:
        parts = []
        index_parts = []
        idx = 0
        for d in context_docs:
            title_d = d.get("title", "未知文档")
            content_d = d.get("content", "")
            if content_d.strip():
                idx += 1
                parts.append(f"[文档{idx}] 《{title_d}》\n{content_d.strip()}")
                index_parts.append(f"[文档{idx}] 《{title_d}》")
        if parts:
            docs_block = "\n\n".join(parts)
            docs_index = "\n".join(index_parts)

    # Auto-complete via AI if no manual description, or if force_ai=True
    ai_summary = ""
    if not description.strip() or force_ai:
        try:
            seed = description.strip()
            prompt = (
                f"请为以下概念提供结构化的解释说明：\n\n"
                f"概念名称：{title}\n"
                + (f"参考简述：{seed}\n\n" if seed else "\n") +
                f"请按以下格式输出（使用 Markdown）：\n\n"
                f"## 核心定义\n"
                f"（一到两句话厘清概念）\n\n"
                f"## 关键机制/原理\n"
                f"1. ...\n"
                f"2. ...\n\n"
                + (f"## 原文依据\n"
                   f"（从下方参考文档中摘录与该概念直接相关的原文段落。要求：\n"
                   f"- 每条引用独立成段，末尾标注 [文档N]\n"
                   f"- 引用原文关键句，而非自行概括\n"
                   f"- 若无直接相关原文，标注「参考文档中未直接涉及」）\n\n" if docs_block else "") +
                f"## 适用范围/前提假设\n\n"
                f"## 关联概念\n"
                f"- 概念A\n"
                f"- 概念B"
            )
            if docs_block:
                prompt += f"\n\n参考文档原文：\n{docs_block}\n\n参考文档清单：\n{docs_index}"
            messages = [
                {"role": "system", "content": (
                    "你是严谨的知识整理助手，为概念提供结构化、准确的解释。"
                    "回答简洁专业，避免冗长。如有参考文档，必须基于原文摘录依据，不可凭空发挥。"
                )},
                {"role": "user", "content": prompt},
            ]
            ai_summary = chat(messages, temperature=0.3, max_tokens=1500,
                              module="ingest_pipeline", task="summarize")
        except Exception as e:
            logger.warning("Concept AI auto-complete failed for %s: %s", title, e)
            ai_summary = ""

    # Auto-classify topic if user didn't pick one
    final_topic = topic if topic and topic != "uncategorized" else ""
    if not final_topic:
        classify_text = description.strip() or ai_summary or title
        try:
            final_topic = classify_content(title, classify_text)
            logger.info("Concept '%s' auto-classified as '%s'", title, final_topic)
        except Exception as e:
            logger.warning("Concept classification failed for %s: %s", title, e)
            final_topic = "认知"  # safe default: fall into 认知

    # Write concept to data/ingest/concepts/
    concepts_dir = INGEST_ROOT.parent / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    concept_md = f"# {title}\n\n创建时间：{now_ts}\n\n---\n\n"
    if ai_summary:
        concept_md += ai_summary + "\n"
    elif description.strip():
        concept_md += description.strip() + "\n"

    md_path = concepts_dir / f"{concept_id}.md"
    md_path.write_text(concept_md, encoding="utf-8")

    with connect() as conn:
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic,
               importance, actionability, decision, status, content_type, ai_summary, created_at)
               VALUES (?, 'user-concept', ?, '', ?, 4, 4, 'digest', 'completed', 'concept', ?, ?)""",
            (concept_id, title, final_topic, ai_summary or description, now_ts),
        )

    return {
        "event_id": concept_id,
        "status": "completed",
        "ai_summary": ai_summary,
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
            from ..ingest.volc_transcriber import upload_to_tos, submit_transcription, poll_result

            stages = [
                {"key": "parse", "label": "解析链接", "status": "active"},
                {"key": "download", "label": "下载视频", "status": "pending"},
                {"key": "persist", "label": "保存视频", "status": "pending"},
                {"key": "extract", "label": "提取音频", "status": "pending"},
                {"key": "tos", "label": "上传 TOS", "status": "pending"},
                {"key": "transcribe", "label": "语音转写", "status": "pending"},
                {"key": "summarize", "label": "AI 总结", "status": "pending"},
                {"key": "writedb", "label": "写入数据库", "status": "pending"},
                {"key": "classify", "label": "自动分类", "status": "pending"},
                {"key": "done", "label": "完成", "status": "pending"},
            ]
            _set_progress(event_id, stages)

            share_text = str(content)
            info = parse_share_text(share_text)
            stages[0]["status"] = "done"
            stages[1]["status"] = "active"
            _set_progress(event_id, stages)

            video_path = work_dir / "video.mp4"
            download_video(info["download_url"], video_path, session=info.get("_session"))
            stages[1]["status"] = "done"
            stages[2]["status"] = "active"
            _set_progress(event_id, stages)
            
            # Persist video file (temp dir will be cleaned up)
            VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
            persistent_video = VIDEOS_DIR / f"{event_id}.mp4"
            shutil.copy2(video_path, persistent_video)
            
            stages[2]["status"] = "done"
            stages[3]["status"] = "active"
            _set_progress(event_id, stages)

            audio_path = work_dir / "audio.wav"
            extract_audio(video_path, audio_path)
            stages[3]["status"] = "done"
            stages[4]["status"] = "active"
            _set_progress(event_id, stages)

            # Upload to volc TOS
            audio_url = upload_to_tos(audio_path)
            stages[4]["status"] = "done"
            stages[5]["status"] = "active"
            _set_progress(event_id, stages)

            # Submit + poll volc AUC transcription
            req_id, logid = submit_transcription(audio_url)
            text = poll_result(req_id, logid)
            stages[5]["status"] = "done"
            stages[6]["status"] = "active"
            _set_progress(event_id, stages)

            # Update title from douyin metadata — strip platform hashtags
            raw_title = info.get("platform_title", "")
            if raw_title:
                # Strip trailing #hashtags and @mentions, keep the core title
                clean = re.sub(r'\s*[#＃][^\s#＃@]+', '', raw_title)
                clean = re.sub(r'\s*@\S+', '', clean)
                clean = clean.strip().rstrip('，,。.')
                title = clean if clean else ""
            if not title:
                title = raw_title  # fallback for logging; AI will override below

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
        overview = None
        if ingest_type in ("douyin_share", "video_file", "audio_file", "document"):
            try:
                from ..summarizer import summarize_transcript
                # If title is effectively empty or truncated, ask AI to generate one
                title_is_empty = not title or bool(re.match(r'^[\s#＃@]+$', title or ''))
                # For douyin_share: detect truncated titles (platform desc limited to ~55 chars)
                title_truncated = (
                    ingest_type == "douyin_share"
                    and bool(title)
                    and not re.search(r'[。！？）」\"''」』]$', title)
                )
                # For video_file / audio_file: title is auto-derived from filename,
                # so ALWAYS ask AI to generate one from content
                title_from_filename = ingest_type in ("video_file", "audio_file")
                need_ai_title = title_is_empty or title_truncated or title_from_filename
                result = summarize_transcript(text, title=title, need_title=need_ai_title)
                if result is not None:
                    ai_summary = result.get("summary", "")
                    overview = result.get("overview", "")
                    if need_ai_title and result.get("suggested_title"):
                        old_title = title
                        title = result["suggested_title"]
                        logger.info("AI generated title for %s: %s → %s", event_id, old_title[:40], title)
                    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
                    (SUMMARIES_DIR / f"{event_id}.md").write_text(ai_summary or "", encoding="utf-8")
                else:
                    logger.warning("AI summarization returned None for %s — API may be unavailable", event_id)
            except Exception as e:
                logger.warning("AI summarization failed for %s (%s): %s", event_id, ingest_type, e)

        # Mark summarization done, activate write-db stage
        if ingest_type == "douyin_share":
            stages[6]["status"] = "done"
            stages[7]["status"] = "active"
            _set_progress(event_id, stages)

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
                   overview = COALESCE(?, overview),
                   status = 'completed', last_error = NULL,
                   video_path = ?, audio_path = ?, document_path = ?,
                   title = CASE WHEN title = '待处理' OR title = '' THEN ? ELSE title END
                   WHERE id = ?""",
                (text, ai_summary, overview, video_path, audio_path_col, document_path_col, title or "待处理", event_id),
            )

        # DB write done → move to classify
        if ingest_type == "douyin_share":
            stages[7]["status"] = "done"
            stages[8]["status"] = "active"
            _set_progress(event_id, stages)

        # Auto-classify into cognitive layer (outside the connection block —
        # classifier manages its own DB connection)
        try:
            from ..classifier import classify_event as _classify_event
            _classify_event(event_id)
        except Exception:
            logger.warning("Classification failed for %s — non-blocking", event_id, exc_info=True)

        # Mark final stage as done
        stages[-1]["status"] = "done"
        _set_progress(event_id, stages)

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
