from __future__ import annotations

import os
import json
import logging as _logging
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel

from .briefing import generate_briefing, latest_briefing
from .collector import collect_once, fetch_url
from .db import connect, init_db, seed_default_sources
from .digest_ai import generate_ai_digest, latest_digest
from .routes.ingest_routes import router as ingest_router
from .task_queue import start_worker, stop_worker
from .translator import translate, translate_title


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, seed sources, start ingest task worker.
    Shutdown: gracefully stop worker."""
    init_db()
    seed_default_sources()
    start_worker()
    yield
    stop_worker()


app = FastAPI(title="知识情报中心", version="0.2.0", lifespan=lifespan)


class CollectRequest(BaseModel):
    source_ids: list[str] | None = None


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:9120",
        "http://localhost:9120",
        "http://10.8.0.105:9120",
        *([f"http://{ip}:9120" for ip in os.getenv("KI_EXTRA_ORIGINS", "").split(",") if ip.strip()]),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SPA fallback: any non-API 404 gets index.html
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

# Optional API token authentication (set KI_API_TOKEN env var to enable)
_API_TOKEN = os.getenv("KI_API_TOKEN", "").strip()

@app.middleware("http")
async def api_auth(request: Request, call_next):
    """Optional API token auth — only enforced when KI_API_TOKEN is set.
    Skips health check, OPTIONS preflight, and non-API paths.
    Accepts Authorization: Bearer <token> or X-API-Key: <token> headers."""
    if _API_TOKEN and request.url.path.startswith("/api") and request.url.path != "/api/health":
        if request.method != "OPTIONS":
            token = (
                request.headers.get("X-API-Key", "") or
                (request.headers.get("Authorization", "").removeprefix("Bearer "))
            )
            if token != _API_TOKEN:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
    return await call_next(request)


@app.middleware("http")
async def spa_fallback(request: Request, call_next):
    response = await call_next(request)
    if response.status_code == 404 and not request.url.path.startswith("/api"):
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
    return response


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"ok": True, "service": "knowledge-intelligence"}


@app.get("/api/ingest/stats")
def ingest_stats() -> dict[str, int]:
    init_db()
    with connect() as conn:
        today = conn.execute(
            "SELECT COUNT(*) FROM events WHERE date(created_at) = date('now') AND source_id IN ('douyin', 'user-upload')"
        ).fetchone()[0]
        processing = conn.execute(
            "SELECT COUNT(*) FROM events WHERE status = 'processing' AND source_id IN ('douyin', 'user-upload')"
        ).fetchone()[0]
        completed = conn.execute(
            "SELECT COUNT(*) FROM events WHERE status = 'new' AND source_id IN ('douyin', 'user-upload')"
        ).fetchone()[0]
    return {"today_submissions": int(today), "processing": int(processing), "completed": int(completed)}


@app.get("/api/dashboard/summary")
def dashboard_summary() -> dict[str, int]:
    init_db()
    with connect() as conn:
        today_events = conn.execute("SELECT COUNT(*) FROM events WHERE date(created_at) = date('now')").fetchone()[0]
        high_priority_events = conn.execute("SELECT COUNT(*) FROM events WHERE importance >= 4").fetchone()[0]
        sources_enabled = conn.execute("SELECT COUNT(*) FROM sources WHERE enabled = 1").fetchone()[0]
    return {
        "today_events": int(today_events),
        "high_priority_events": int(high_priority_events),
        "sources_enabled": int(sources_enabled),
    }


@app.get("/api/dashboard/trend")
def dashboard_trend(days: int = 7) -> list[dict[str, object]]:
    """Return daily event counts for the last N days."""
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """SELECT date(created_at) as day, COUNT(*) as count
               FROM events
               WHERE created_at >= date('now', ?)
               GROUP BY day ORDER BY day""",
            (f"-{days} days",),
        ).fetchall()
    return [{"day": r["day"], "count": r["count"]} for r in rows]


@app.get("/api/sources")
def list_sources() -> list[dict[str, object]]:
    init_db()
    seed_default_sources()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, type, url, topic, priority, enabled, last_checked_at, last_error
            FROM sources
            ORDER BY id
            """
        ).fetchall()
    return [dict(row) for row in rows]


@app.put("/api/sources/{source_id}/toggle")
def toggle_source(source_id: str) -> dict[str, object]:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT id, enabled FROM sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Source not found")
        new_enabled = 0 if row["enabled"] else 1
        conn.execute("UPDATE sources SET enabled = ? WHERE id = ?", (new_enabled, source_id))
    return {"id": source_id, "enabled": bool(new_enabled)}


@app.post("/api/sources/{source_id}/collect")
def collect_source(source_id: str) -> dict[str, object]:
    init_db()
    seed_default_sources()
    from .collector import collect_once, fetch_url
    result = collect_once(source_ids=[source_id], fetcher=fetch_url)
    return result


@app.get("/api/events")
def list_events(
    topic: str | None = None, status: str | None = None,
    source_id: str | None = None,
    search: str | None = None, offset: int = 0, limit: int = 50,
    count: int = 0,
) -> list[dict[str, object]] | dict[str, object]:
    init_db()
    if search:
        # FTS5 full-text search with trigram tokenizer (works for Chinese + English)
        # For very short terms (< 3 chars) use LIKE fallback since trigram needs >=3 chars
        search_term = search.strip()
        if len(search_term) < 3:
            with connect() as conn:
                like_pattern = f"%{search_term}%"
                rows = conn.execute(
                    """SELECT id, source_id, title, url, published_at, raw_summary, ai_summary,
                       title_cn, summary_cn, translation_status, translation_error,
                       topic, importance, actionability, decision, status, tags_json,
                       last_error, progress_stages, video_path, created_at
                    FROM events
                    WHERE title LIKE ? OR title_cn LIKE ? OR raw_summary LIKE ? OR summary_cn LIKE ? OR ai_summary LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?""",
                    (like_pattern, like_pattern, like_pattern, like_pattern, like_pattern,
                     max(1, min(200, limit)), max(0, offset)),
                ).fetchall()
            return [dict(row) for row in rows]
        with connect() as conn:
            rows = conn.execute(
                """SELECT e.id, e.source_id, e.title, e.url, e.published_at, e.raw_summary, e.ai_summary,
                   e.title_cn, e.summary_cn, e.translation_status, e.translation_error,
                   e.topic, e.importance, e.actionability, e.decision, e.status, e.tags_json,
                   e.last_error, e.progress_stages, e.video_path, e.created_at,
                   snippet(events_fts, 1, '<mark>', '</mark>', '...', 60) as snippet
                FROM events e
                INNER JOIN events_fts fts ON e.id = fts.event_id
                WHERE events_fts MATCH ?
                ORDER BY rank
                LIMIT ? OFFSET ?""",
                (search, max(1, min(200, limit)), max(0, offset)),
            ).fetchall()
        return [dict(row) for row in rows]

    query = (
        "SELECT id, source_id, title, url, published_at, raw_summary, ai_summary,\n"
        "       title_cn, summary_cn, translation_status, translation_error,\n"
        "       topic, importance, actionability, decision, status, tags_json,\n"
        "       last_error, progress_stages, video_path, created_at\n"
        "FROM events\n"
        "WHERE 1=1\n"
    )
    params: dict[str, object] = {}
    if topic:
        query += " AND topic = :topic"
        params["topic"] = topic
    if status:
        query += " AND status = :status"
        params["status"] = status
    if source_id:
        ids = [s.strip() for s in source_id.split(",") if s.strip()]
        if len(ids) == 1:
            query += " AND source_id = :source_id"
            params["source_id"] = ids[0]
        else:
            placeholders = ",".join([f":sid{i}" for i in range(len(ids))])
            query += f" AND source_id IN ({placeholders})"
            for i, sid in enumerate(ids):
                params[f"sid{i}"] = sid
    query += " ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
    params["limit"] = max(1, min(200, limit))
    params["offset"] = max(0, offset)
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    result = [dict(row) for row in rows]
    if count:
        # Also return total count for pagination
        count_params = {}
        count_query = "SELECT COUNT(*) FROM events WHERE 1=1"
        if "topic" in params:
            count_query += " AND topic = :topic"
            count_params["topic"] = params["topic"]
        if "status" in params:
            count_query += " AND status = :status"
            count_params["status"] = params["status"]
        if source_id:
            ids = [s.strip() for s in source_id.split(",") if s.strip()]
            if len(ids) == 1:
                count_query += " AND source_id = :source_id"
                count_params["source_id"] = ids[0]
            else:
                placeholders = ",".join([f":sid{i}" for i in range(len(ids))])
                count_query += f" AND source_id IN ({placeholders})"
                for i, sid in enumerate(ids):
                    count_params[f"sid{i}"] = sid
        with connect() as conn:
            total = conn.execute(count_query, count_params).fetchone()[0]
        return {"items": result, "total": total}
    return result


@app.get("/api/events/{event_id}")
def get_event(event_id: str) -> dict[str, object]:
    """Get full event detail including complete transcript."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            """SELECT id, source_id, title, url, published_at, raw_summary, ai_summary,
               title_cn, summary_cn, translation_status, translation_error,
               topic, importance, actionability, decision, status, tags_json,
               last_error, progress_stages, video_path, created_at
               FROM events WHERE id = ?""",
            (event_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    result = dict(row)
    # Add ingest file paths
    ingest_root = Path(__file__).resolve().parents[2] / "data" / "ingest"
    result["transcript_path"] = str(ingest_root / "transcripts" / f"{event_id}.md")
    result["summary_path"] = str(ingest_root / "summaries" / f"{event_id}.md")
    # Add associated brainstorm questions
    with connect() as conn:
        qrows = conn.execute(
            "SELECT bq.id, bq.question, bq.status, bq.created_at, "
            "(SELECT json_group_array(bel2.event_id) FROM brainstorm_event_links bel2 WHERE bel2.question_id = bq.id) as answered_event_ids "
            "FROM brainstorm_questions bq "
            "INNER JOIN brainstorm_event_links bel ON bel.question_id = bq.id "
            "WHERE bel.event_id = ? ORDER BY bq.created_at DESC",
            (event_id,),
        ).fetchall()
    result["associated_questions"] = [dict(r) for r in qrows]
    return result


@app.delete("/api/events/{event_id}")
def delete_event(event_id: str) -> dict[str, object]:
    """Delete an event and its associated ingest files."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, video_path, audio_path, document_path FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")

    # Clean up ingest files
    ingest_root = Path(__file__).resolve().parents[2] / "data" / "ingest"
    (ingest_root / "transcripts" / f"{event_id}.md").unlink(missing_ok=True)
    (ingest_root / "summaries" / f"{event_id}.md").unlink(missing_ok=True)

    for path_col in ("video_path", "audio_path", "document_path"):
        p = row[path_col]
        if p:
            Path(p).unlink(missing_ok=True)

    with connect() as conn:
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    return {"ok": True, "deleted": event_id}


@app.post("/api/events/batch-delete")
def batch_delete_events(payload: dict[str, object]) -> dict[str, object]:
    """Delete multiple events and their associated ingest files."""
    event_ids = payload.get("event_ids", [])
    if not isinstance(event_ids, list) or not event_ids:
        raise HTTPException(status_code=400, detail="event_ids must be a non-empty list")
    init_db()
    ingest_root = Path(__file__).resolve().parents[2] / "data" / "ingest"
    deleted = 0
    for event_id in event_ids:
        eid = str(event_id)
        with connect() as conn:
            row = conn.execute("SELECT id, video_path, audio_path, document_path FROM events WHERE id = ?", (eid,)).fetchone()
        if row is None:
            continue
        (ingest_root / "transcripts" / f"{eid}.md").unlink(missing_ok=True)
        (ingest_root / "summaries" / f"{eid}.md").unlink(missing_ok=True)
        for path_col in ("video_path", "audio_path", "document_path"):
            p = row[path_col]
            if p:
                Path(p).unlink(missing_ok=True)
        with connect() as conn:
            conn.execute("DELETE FROM events WHERE id = ?", (eid,))
        deleted += 1
    return {"ok": True, "deleted": deleted}


@app.post("/api/events/{event_id}/summarize")
def summarize_event(event_id: str, background_tasks: BackgroundTasks) -> dict[str, object]:
    """Generate an AI summary for a douyin event using the Knowledge template."""
    from .summarizer import summarize_transcript

    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, raw_summary, ai_summary FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")

    title = row["title"] or ""
    transcript = row["raw_summary"] or ""

    if not transcript.strip():
        raise HTTPException(status_code=400, detail="Event has no transcript content")

    # Return cached summary if already generated
    if row["ai_summary"]:
        return {"event_id": event_id, "summary": row["ai_summary"], "cached": True}

    def _run_summary():
        try:
            summary = summarize_transcript(transcript, title=title)
            if summary:
                with connect() as conn:
                    conn.execute(
                        "UPDATE events SET ai_summary = ? WHERE id = ?",
                        (summary, event_id),
                    )
                # Also write to file system
                summaries_dir = Path(__file__).resolve().parents[2] / "data" / "ingest" / "summaries"
                summaries_dir.mkdir(parents=True, exist_ok=True)
                (summaries_dir / f"{event_id}.md").write_text(summary, encoding="utf-8")
        except Exception as e:
            logger.exception("Background summary failed for %s: %s", event_id, e)

    background_tasks.add_task(_run_summary)
    return {"event_id": event_id, "status": "processing", "cached": False}


@app.post("/api/collect")
def collect(request: CollectRequest) -> dict[str, object]:
    init_db()
    seed_default_sources()
    return collect_once(source_ids=request.source_ids, fetcher=fetch_url)


@app.post("/api/digest/generate")
def generate_digest() -> dict[str, object]:
    init_db()
    return generate_ai_digest()


@app.get("/api/digest/latest")
def get_latest_digest() -> dict[str, object]:
    init_db()
    return latest_digest()


app.include_router(ingest_router)


# ---------------------------------------------------------------------------
# Translation endpoints
# ---------------------------------------------------------------------------

class TranslateRequest(BaseModel):
    limit: int = 20


@app.post("/api/translate/run")
def run_translation(request: TranslateRequest | None = None) -> dict[str, object]:
    """Translate all pending events (title_cn IS NULL and translation_status='pending').
    Uses concurrent workers for parallel translation (max 5 at a time)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from threading import Lock

    init_db()
    limit = request.limit if request else 20
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, title, raw_summary FROM events
               WHERE translation_status = 'pending'
               AND title_cn IS NULL
               LIMIT ?""",
            (limit,),
        ).fetchall()

    if not rows:
        return {"total_pending_at_start": 0, "translated": 0, "failed": 0, "skipped": 0, "remaining": 0}

    translated = 0
    failed = 0
    skipped = 0
    lock = Lock()

    def _translate_one(row) -> dict:
        event_id = row["id"]
        title = row["title"] or ""
        summary = row["raw_summary"] or ""

        title_result = translate_title(title)
        title_cn = title_result.text if title_result.success and title_result.text != title else None

        summary_result = translate(summary) if summary else None
        summary_cn = None
        if summary_result and summary_result.success and summary_result.text != summary:
            summary_cn = summary_result.text

        if title_result.success or (summary_result and summary_result.success):
            status = "done"
            error = None
        elif not title_result.success and not title:
            return {"event_id": event_id, "outcome": "skipped", "error": None}
        else:
            status = "failed"
            error = title_result.error or (summary_result.error if summary_result else "unknown")

        with connect() as conn:
            conn.execute(
                """UPDATE events SET title_cn = ?, summary_cn = ?,
                   translation_status = ?, translation_error = ?
                   WHERE id = ?""",
                (title_cn, summary_cn, status, error, event_id),
            )
        return {"event_id": event_id, "outcome": "translated" if status == "done" else "failed", "error": error}

    with ThreadPoolExecutor(max_workers=min(len(rows), 5)) as executor:
        futures = {executor.submit(_translate_one, row): row["id"] for row in rows}
        for future in as_completed(futures):
            try:
                result = future.result()
                with lock:
                    if result["outcome"] == "translated":
                        translated += 1
                    elif result["outcome"] == "failed":
                        failed += 1
                    elif result["outcome"] == "skipped":
                        skipped += 1
            except Exception as e:
                with lock:
                    failed += 1
                logger.warning("Translation worker crashed for %s: %s", futures[future], e)

    remaining = 0
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM events WHERE translation_status = 'pending' AND title_cn IS NULL"
        ).fetchone()
        remaining = row[0] if row else 0

    return {
        "total_pending_at_start": len(rows),
        "translated": translated,
        "failed": failed,
        "skipped": skipped,
        "remaining": remaining,
    }


@app.post("/api/translate/backfill")
def backfill_translation(request: TranslateRequest | None = None) -> dict[str, object]:
    """Mark all events without Chinese translation as pending, then translate."""
    init_db()
    limit = request.limit if request else 50
    with connect() as conn:
        conn.execute(
            """UPDATE events SET translation_status = 'pending'
               WHERE title_cn IS NULL
               AND translation_status IS NULL
               AND source_id NOT IN ('douyin', 'user-upload')"""
        )
        marked = conn.total_changes

    # Run translation on the newly marked
    result = run_translation(TranslateRequest(limit=limit))
    result["marked"] = marked
    return result


# ---------------------------------------------------------------------------
# Brainstorm endpoints
# ---------------------------------------------------------------------------
import uuid as _uuid
import json

logger = _logging.getLogger("knowledge-intelligence")

BRAINSTORM_DIR = Path(__file__).resolve().parents[2] / "data" / "brainstorm"
BRAINSTORM_DIR.mkdir(parents=True, exist_ok=True)


def _brainstorm_md_path(question_id: str) -> Path:
    return BRAINSTORM_DIR / f"{question_id}.md"


@app.get("/api/brainstorm")
def list_brainstorm_questions(status: str | None = None, offset: int = 0, limit: int = 200) -> dict[str, object]:
    """List brainstorm questions, newest first."""
    init_db()
    query = """
        SELECT b.id, b.event_id, b.question, b.status, b.created_at,
               (SELECT json_group_array(bel.event_id) FROM brainstorm_event_links bel WHERE bel.question_id = b.id) as answered_event_ids,
               e.title, e.title_cn, e.source_id, e.url
        FROM brainstorm_questions b
        LEFT JOIN events e ON e.id = b.event_id
        WHERE 1=1
    """
    params: dict[str, object] = {}
    if status:
        query += " AND b.status = :status"
        params["status"] = status
    query += " ORDER BY b.created_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = max(1, min(500, limit))
    params["offset"] = max(0, offset)

    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return {"questions": [dict(row) for row in rows]}


@app.get("/api/brainstorm/{question_id}")
def get_brainstorm_question(question_id: str) -> dict[str, object]:
    """Get a single brainstorm question with its answered_event_ids and latest answer."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, event_id, question, status, created_at FROM brainstorm_questions WHERE id = ?",
            (question_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Question not found")
    result = dict(row)
    # Get linked event IDs from join table
    with connect() as conn:
        event_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    result["answered_event_ids"] = json.dumps([r["event_id"] for r in event_rows])
    # Get judged (contemplated) event IDs with relevance
    with connect() as conn:
        judged_rows = conn.execute(
            "SELECT event_id, relevance FROM brainstorm_contemplate_cache WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    result["judged_events"] = json.dumps([{"event_id": r["event_id"], "relevance": r["relevance"]} for r in judged_rows])
    # Read latest answer from .md file
    md = _brainstorm_md_path(question_id)
    result["md_content"] = md.read_text(encoding="utf-8") if md.exists() else ""
    # Extract latest answer text
    result["answer"] = _extract_latest_answer(md)
    return result


def _extract_latest_answer(md_path: Path) -> str:
    """Extract the latest answer from a brainstorm .md file."""
    if not md_path.exists():
        return ""
    content = md_path.read_text(encoding="utf-8")
    blocks = content.split("## 回答")
    if len(blocks) < 2:
        return ""
    last = blocks[-1]
    lines = last.strip().split("\n")
    answer_lines = []
    started = False
    for line in lines:
        if not started:
            # Skip timestamp line like "(2026-06-08 14:58)"
            started = True
            continue
        if line.strip() == "---":
            break
        answer_lines.append(line)
    return "\n".join(answer_lines).strip()


class CreateQuestionRequest(BaseModel):
    question: str


@app.post("/api/brainstorm")
def create_brainstorm_question(request: CreateQuestionRequest) -> dict[str, object]:
    """Manually create a brainstorm question and its .md file."""
    init_db()
    q_id = str(_uuid.uuid4())
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with connect() as conn:
        conn.execute(
            "INSERT INTO brainstorm_questions (id, event_id, question) VALUES (?, '', ?)",
            (q_id, request.question),
        )
    # Create .md file and sync content_md
    md = _brainstorm_md_path(q_id)
    md_content = (
        f"# 问题\n\n{request.question}\n\n"
        f"创建时间：{now}\n\n"
        f"---\n\n"
    )
    md.write_text(md_content, encoding="utf-8")
    with connect() as conn:
        conn.execute("UPDATE brainstorm_questions SET content_md = ? WHERE id = ?", (md_content, q_id))
    return {"ok": True, "id": q_id, "question": request.question}


@app.delete("/api/brainstorm/{question_id}")
def delete_brainstorm_question(question_id: str) -> dict[str, object]:
    """Delete a brainstorm question and its .md file."""
    init_db()
    with connect() as conn:
        existing = conn.execute("SELECT id FROM brainstorm_questions WHERE id = ?", (question_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Question not found")
        conn.execute("DELETE FROM brainstorm_questions WHERE id = ?", (question_id,))
    # Also delete .md file
    md = _brainstorm_md_path(question_id)
    md.unlink(missing_ok=True)
    return {"ok": True, "deleted": question_id}


@app.post("/api/brainstorm/batch-delete")
def batch_delete_brainstorm_questions(payload: dict[str, object]) -> dict[str, object]:
    """Delete multiple brainstorm questions and their .md files."""
    question_ids = payload.get("question_ids", [])
    if not isinstance(question_ids, list) or not question_ids:
        raise HTTPException(status_code=400, detail="question_ids must be a non-empty list")
    init_db()
    deleted = 0
    for qid in question_ids:
        qid_str = str(qid)
        with connect() as conn:
            existing = conn.execute("SELECT id FROM brainstorm_questions WHERE id = ?", (qid_str,)).fetchone()
            if existing is None:
                continue
            conn.execute("DELETE FROM brainstorm_questions WHERE id = ?", (qid_str,))
        md = _brainstorm_md_path(qid_str)
        md.unlink(missing_ok=True)
        deleted += 1
    return {"ok": True, "deleted": deleted}


@app.post("/api/brainstorm/{question_id}/done")
def mark_brainstorm_done(question_id: str) -> dict[str, object]:
    """Mark a brainstorm question as done."""
    init_db()
    with connect() as conn:
        existing = conn.execute("SELECT id FROM brainstorm_questions WHERE id = ?", (question_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Question not found")
        conn.execute("UPDATE brainstorm_questions SET status = 'done' WHERE id = ?", (question_id,))
    return {"ok": True, "id": question_id, "status": "done"}


class AnswerRequest(BaseModel):
    question_id: str
    question: str
    event_ids: list[str]


@app.post("/api/brainstorm/answer")
def get_answer_for_question(request: AnswerRequest) -> dict[str, object]:
    """Given a brainstorm question and selected events, find the answer from the articles.
    Saves the answer to the question's .md file and tracks answered_event_ids.
    """
    if not request.event_ids:
        return {"answer": "请至少选择一个事件作为参考文档。", "event_ids": []}

    init_db()
    articles: list[dict[str, str]] = []
    with connect() as conn:
        placeholders = ",".join(["?" for _ in request.event_ids])
        rows = conn.execute(
            f"SELECT id, ai_summary, raw_summary, title FROM events WHERE id IN ({placeholders})",
            tuple(request.event_ids),
        ).fetchall()

    if not rows:
        return {"answer": "未找到所选事件。", "event_ids": request.event_ids}

    for row in rows:
        text = (row["ai_summary"] or "") or (row["raw_summary"] or "")
        if text.strip():
            title = row["title"] or "未命名"
            articles.append({"title": title, "text": text[:3000] if len(text) > 3000 else text})

    if not articles:
        return {"answer": "所选事件没有可用的文本内容。", "event_ids": request.event_ids}

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "***":
        return {"answer": "DeepSeek API 未配置，无法生成回答。", "event_ids": request.event_ids}

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    url = f"{base_url}/v1/chat/completions"

    # Generate answer for each article independently
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    md_parts: list[str] = []
    display_parts: list[str] = []

    for art in articles:
        prompt = (
            "你是一个文章分析助手。请严格基于以下文章内容，回答用户的问题。\n"
            "规则：只使用文章中的信息；如果文章没有涉及该问题，请明确说明'本文未涉及该问题'；\n"
            "回答简洁，控制在300字以内。\n\n"
            f"问题：{request.question}\n\n"
            f"文章内容：\n{art['text']}"
        )

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是严谨的文章分析助手，只基于给定文章回答问题，绝不编造。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 800,
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                answer = body["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning("Answer extraction failed for article '%s': %s", art['title'], e)
            answer = "（AI 回答生成失败）"

        md_parts.append(f"### 基于「{art['title']}」回答\n\n{answer}\n")
        display_parts.append(f"### 基于「{art['title']}」回答\n\n{answer}\n")

    combined_display = "\n---\n\n".join(display_parts)
    combined_md = "\n".join(md_parts) + "\n"

    # Save answer to .md file
    md = _brainstorm_md_path(request.question_id)
    answer_block = (
        f"## 回答 ({now})\n\n"
        f"{combined_md}"
        f"---\n\n"
    )
    with open(md, "a", encoding="utf-8") as f:
        f.write(answer_block)

    # Update event links + content_md in DB
    with connect() as conn:
        for eid in request.event_ids:
            conn.execute(
                "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
                (request.question_id, eid),
            )
        # Read full .md content for sync
        full_md = md.read_text(encoding="utf-8") if md.exists() else ""
        conn.execute(
            "UPDATE brainstorm_questions SET content_md = ? WHERE id = ?",
            (full_md, request.question_id),
        )
        # Get merged event_ids
        event_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            (request.question_id,),
        ).fetchall()
    merged = [r["event_id"] for r in event_rows]

    return {"answer": combined_display, "event_ids": request.event_ids, "answered_event_ids": merged}


# ---------------------------------------------------------------------------
# Contemplate: bidirectional matching between events and brainstorm questions
# ---------------------------------------------------------------------------

class ContemplateRequest(BaseModel):
    direction: str   # "event_to_questions" or "question_to_events"
    entity_id: str


@app.post("/api/brainstorm/contemplate")
def contemplate(request: ContemplateRequest) -> dict[str, object]:
    """Bidirectional smart matching:
    - event_to_questions: given an event, find brainstorm questions it might answer
    - question_to_events: given a question, find events that might answer it
    Skips already-linked pairs.
    """
    init_db()
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "***":
        return {"entity_id": request.entity_id, "suggestions": [], "error": "DeepSeek API 未配置"}

    if request.direction == "event_to_questions":
        return _contemplate_event_to_questions(request.entity_id, api_key)
    elif request.direction == "question_to_events":
        return _contemplate_question_to_events(request.entity_id, api_key)
    else:
        return {"entity_id": request.entity_id, "suggestions": [], "error": "invalid direction"}


def _contemplate_event_to_questions(event_id: str, api_key: str) -> dict[str, object]:
    """Given an event, find which brainstorm questions it might answer.
    Uses cache table so repeated contemplation skips already-judged pairs.
    """
    # 1. Get the event
    with connect() as conn:
        event = conn.execute(
            "SELECT id, title, ai_summary, raw_summary FROM events WHERE id = ?", (event_id,)
        ).fetchone()
    if not event:
        return {"entity_id": event_id, "suggestions": [], "error": "事件不存在"}

    event_text = (event["ai_summary"] or "") or (event["raw_summary"] or "")
    if not event_text.strip():
        return {"entity_id": event_id, "suggestions": [], "error": "事件没有文本内容"}

    # 2. Get already-linked question IDs
    with connect() as conn:
        linked_rows = conn.execute(
            "SELECT question_id FROM brainstorm_event_links WHERE event_id = ?", (event_id,)
        ).fetchall()
    linked_ids = {r["question_id"] for r in linked_rows}

    # 3. Get cached judgments for this event
    with connect() as conn:
        cached_rows = conn.execute(
            "SELECT question_id, relevance, reason FROM brainstorm_contemplate_cache WHERE event_id = ?",
            (event_id,),
        ).fetchall()
    cached: dict[str, dict] = {r["question_id"]: {"relevance": r["relevance"], "reason": r["reason"]} for r in cached_rows}
    cached_ids = set(cached.keys())

    # 4. Get all open questions
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, question FROM brainstorm_questions WHERE status = 'open' ORDER BY created_at DESC LIMIT 50"
        ).fetchall()

    # Split: linked, cached (unlinked), new candidates
    all_questions = [dict(r) for r in rows]
    candidates = [q for q in all_questions if q["id"] not in linked_ids and q["id"] not in cached_ids]

    # Build linked suggestions (always at the end)
    linked_suggestions = []
    for q in all_questions:
        if q["id"] in linked_ids:
            # Look up relevance from cache if available, else mark as linked
            j = cached.get(q["id"])
            linked_suggestions.append({
                "question_id": q["id"],
                "question_text": q["question"],
                "relevance": j["relevance"] if j else "high",
                "reason": j["reason"] if j else "已关联",
                "link_status": "linked",
            })

    # Build cached suggestions (unlinked, already judged)
    cached_suggestions = []
    for q in all_questions:
        if q["id"] not in linked_ids and q["id"] in cached_ids:
            j = cached[q["id"]]
            cached_suggestions.append({
                "question_id": q["id"],
                "question_text": q["question"],
                "relevance": j["relevance"],
                "reason": j["reason"] or "",
                "link_status": "unlinked",
            })

    # 5. Ask DeepSeek for new candidates
    new_suggestions: list[dict] = []
    if candidates:
        event_title = event["title"] or ""
        event_snippet = event_text[:3000] if len(event_text) > 3000 else event_text

        question_lines = []
        for i, q in enumerate(candidates):
            question_lines.append(f"[{i}] {q['question']}")

        prompt = (
            "你是一个内容匹配助手。以下是一篇文章，请判断它能回答下面哪些问题。\n"
            "对每个问题，判断是否可以基于文章内容回答：\n"
            "- 如果文章直接涉及该问题的主题，标为 high\n"
            "- 如果文章部分相关或可提供背景，标为 medium\n"
            "- 如果完全无关，标为 low\n"
            "注意：不要因为问题关键词看起来匹配就误判，必须基于文章内容的实质关联。\n"
            "只输出 JSON 数组，不要其他内容。格式：\n"
            '[{"index": 0, "relevance": "high", "reason": "一句话原因"}, ...]\n'
            "只输出 relevance 为 high 或 medium 的项，low 的跳过不输出。\n\n"
            f"文章标题：{event_title}\n"
            f"文章内容：\n{event_snippet}\n\n"
            f"待评估问题：\n" + "\n".join(question_lines)
        )

        matches = _call_contemplate_deepseek(api_key, prompt)

        # 6. Persist results to cache (including low for unmatched candidates)
        matched_indices: set[int] = set()
        with connect() as conn:
            for m in matches:
                idx = m.get("index")
                if idx is not None and 0 <= idx < len(candidates):
                    matched_indices.add(idx)
                    q = candidates[idx]
                    relevance = m.get("relevance", "medium")
                    reason = m.get("reason", "")
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (q["id"], event_id, relevance, reason),
                    )
                    new_suggestions.append({
                        "question_id": q["id"],
                        "question_text": q["question"],
                        "relevance": relevance,
                        "reason": reason,
                        "link_status": "unlinked",
                    })
            # Cache unmatched candidates as "low"
            for i, q in enumerate(candidates):
                if i not in matched_indices:
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (q["id"], event_id, "low", ""),
                    )
                    new_suggestions.append({
                        "question_id": q["id"],
                        "question_text": q["question"],
                        "relevance": "low",
                        "reason": "",
                        "link_status": "unlinked",
                    })

    # 7. Sort: new (high→medium→low) → cached (high→medium→low) → linked
    def _sort_key(s: dict) -> tuple:
        group = 0 if s.get("link_status") != "linked" and s not in cached_suggestions else (
            1 if s.get("link_status") != "linked" else 2
        )
        rel_order = {"high": 0, "medium": 1, "low": 2}
        return (group, rel_order.get(s.get("relevance", "low"), 2))

    new_suggestions.sort(key=_sort_key)
    cached_suggestions.sort(key=_sort_key)
    linked_suggestions.sort(key=_sort_key)

    all_suggestions = new_suggestions + cached_suggestions + linked_suggestions

    return {
        "entity_id": event_id,
        "entity_title": event["title"],
        "suggestions": all_suggestions,
    }


def _contemplate_question_to_events(question_id: str, api_key: str) -> dict[str, object]:
    """Given a question, find which events might answer it.
    Uses full text for matching; persists results so repeated contemplation skips already-judged pairs.
    """
    # 1. Get the question
    with connect() as conn:
        q = conn.execute(
            "SELECT id, question FROM brainstorm_questions WHERE id = ?", (question_id,)
        ).fetchone()
    if not q:
        return {"entity_id": question_id, "suggestions": [], "error": "问题不存在"}

    # 2. Get already-linked event IDs
    with connect() as conn:
        linked = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?", (question_id,)
        ).fetchall()
    linked_ids = {r["event_id"] for r in linked}

    # 3. Get cached judgments for this question
    with connect() as conn:
        cached_rows = conn.execute(
            "SELECT event_id, relevance, reason FROM brainstorm_contemplate_cache WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    cached: dict[str, dict] = {r["event_id"]: {"relevance": r["relevance"], "reason": r["reason"]} for r in cached_rows}
    cached_ids = set(cached.keys())

    # 4. Get all non-RSS events with text, excluding linked AND cached
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, title, ai_summary, raw_summary FROM events
               WHERE source_id IN ('douyin', 'user-upload')
                 AND (ai_summary != '' OR raw_summary != '')
                 AND status = 'new'
               ORDER BY created_at DESC LIMIT 60"""
        ).fetchall()

    candidates = [dict(r) for r in rows if r["id"] not in linked_ids and r["id"] not in cached_ids]

    # Build cached suggestions (skipped from AI call)
    cached_suggestions = []
    for event_id, judgment in cached.items():
        if event_id not in linked_ids:
            # Look up title from rows
            evt_row = next((r for r in rows if r["id"] == event_id), None)
            title = evt_row["title"] if evt_row else event_id
            cached_suggestions.append({
                "event_id": event_id,
                "event_title": title,
                "relevance": judgment["relevance"],
                "reason": judgment["reason"] or "",
            })

    if not candidates and not cached_suggestions:
        return {"entity_id": question_id, "entity_title": q["question"], "suggestions": [], "note": "所有内容已关联或已判断"}

    # 5. Ask DeepSeek for new candidates (full text, not snippet)
    new_suggestions: list[dict] = []
    if candidates:
        event_lines = []
        for i, evt in enumerate(candidates):
            text = (evt["ai_summary"] or "") or (evt["raw_summary"] or "")
            full_text = text[:3000] if len(text) > 3000 else text
            event_lines.append(f"[{i}] {evt['title']}\n内容：{full_text}")

        prompt = (
            "你是一个内容匹配助手。以下是一个问题，请判断下面哪些文章可以用于回答它。\n"
            "对每篇文章，仔细阅读全文后判断是否可基于其内容回答问题：\n"
            "- 如果文章直接涉及该问题的核心，标为 high\n"
            "- 如果文章部分相关或可提供背景信息，标为 medium\n"
            "- 如果完全无关，标为 low\n"
            "注意：不要因为文章标题或关键词看起来相关就误判，必须基于内容的实质关联。\n"
            "只输出 JSON 数组：[{\"index\": 0, \"relevance\": \"high\", \"reason\": \"一句话原因\"}, ...]\n"
            "只输出 high 或 medium，low 跳过。\n\n"
            f"问题：{q['question']}\n\n"
            f"待评估文章：\n" + "\n\n".join(event_lines)
        )

        matches = _call_contemplate_deepseek(api_key, prompt)

        # 6. Persist results to cache (including low for unmatched candidates)
        matched_indices: set[int] = set()
        with connect() as conn:
            for m in matches:
                idx = m.get("index")
                if idx is not None and 0 <= idx < len(candidates):
                    matched_indices.add(idx)
                    evt = candidates[idx]
                    relevance = m.get("relevance", "medium")
                    reason = m.get("reason", "")
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (question_id, evt["id"], relevance, reason),
                    )
                    new_suggestions.append({
                        "event_id": evt["id"],
                        "event_title": evt["title"],
                        "relevance": relevance,
                        "reason": reason,
                    })
            # Cache unmatched candidates as "low"
            for i, evt in enumerate(candidates):
                if i not in matched_indices:
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (question_id, evt["id"], "low", ""),
                    )

    # Combine cached + new
    all_suggestions = cached_suggestions + new_suggestions
    # Sort: high first, then medium
    all_suggestions.sort(key=lambda s: (0 if s["relevance"] == "high" else 1))

    return {
        "entity_id": question_id,
        "entity_title": q["question"],
        "suggestions": all_suggestions,
    }


def _call_contemplate_deepseek(api_key: str, prompt: str) -> list[dict]:
    """Call DeepSeek for contemplation matching. Returns parsed JSON list."""
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a JSON-only API. Always output valid JSON array, nothing else."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
    }
    data = json.dumps(payload).encode("utf-8")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    url = f"{base_url}/v1/chat/completions"

    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        raw = body["choices"][0]["message"]["content"].strip()

    # Parse JSON — handle markdown code fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3]
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Briefing endpoints
# ---------------------------------------------------------------------------

class BriefingRequest(BaseModel):
    type: str = "quick"  # 'quick' or 'daily'
    limit: int = 80


@app.post("/api/briefing/generate")
def generate_news_briefing(request: BriefingRequest | None = None) -> dict[str, object]:
    """Generate a structured AI-powered Chinese news briefing."""
    from .briefing import generate_briefing as _gen
    try:
        result = _gen(
            briefing_type=(request.type if request else "quick"),
            limit=(request.limit if request else 80),
        )
        return {
            "ok": True,
            "id": result["id"],
            "type": result["type"],
            "events_used": result["events_used"],
        }
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/briefing/latest")
def get_latest_briefing(briefing_type: str = "quick") -> dict[str, object]:
    """Get the latest briefing of the given type."""
    result = latest_briefing(briefing_type)
    if not result:
        raise HTTPException(status_code=404, detail=f"No {briefing_type} briefing found")
    return result


# ---------------------------------------------------------------------------
# Tagging endpoints
# ---------------------------------------------------------------------------

class TagRequest(BaseModel):
    limit: int = 50


@app.post("/api/events/{event_id}/tag")
def tag_single_event(event_id: str) -> dict[str, object]:
    """Extract tags for a single event using DeepSeek NER."""
    from .tagger import tag_event

    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, title_cn, raw_summary, ai_summary FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Event not found")

    title = row["title"] or ""
    title_cn = row["title_cn"]
    text = row["ai_summary"] or row["raw_summary"] or ""

    tags = tag_event(title, text, title_cn=title_cn)

    with connect() as conn:
        conn.execute(
            "UPDATE events SET tags_json = ? WHERE id = ?",
            (json.dumps(tags, ensure_ascii=False), event_id),
        )

    return {"event_id": event_id, "tags": tags}


@app.post("/api/tag/batch")
def tag_batch(request: TagRequest | None = None) -> dict[str, object]:
    """Batch-tag untagged events (max N at a time)."""
    from .tagger import tag_event

    init_db()
    limit = min(request.limit if request else 50, 100)

    with connect() as conn:
        rows = conn.execute(
            """SELECT id, title, title_cn, raw_summary, ai_summary
               FROM events
               WHERE (tags_json IS NULL OR tags_json = '[]')
               AND raw_summary IS NOT NULL
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    tagged = 0
    failed = 0

    for row in rows:
        try:
            title = row["title"] or ""
            title_cn = row["title_cn"]
            text = row["ai_summary"] or row["raw_summary"] or ""
            tags = tag_event(title, text, title_cn=title_cn)
            with connect() as conn:
                conn.execute(
                    "UPDATE events SET tags_json = ? WHERE id = ?",
                    (json.dumps(tags, ensure_ascii=False), row["id"]),
                )
            tagged += 1
        except Exception:
            failed += 1

    return {"tagged": tagged, "failed": failed, "total_pending": len(rows)}


@app.get("/api/events/{event_id}/similar")
def similar_events(event_id: str, limit: int = 5) -> list[dict[str, object]]:
    """Find events similar to the given event by title/content overlap."""
    import difflib

    init_db()
    with connect() as conn:
        target = conn.execute(
            "SELECT id, title, title_cn, raw_summary FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Event not found")

        candidates = conn.execute(
            """SELECT id, source_id, title, title_cn, url, topic, created_at
               FROM events WHERE id != ? AND status = 'new'
               ORDER BY created_at DESC LIMIT 200""",
            (event_id,),
        ).fetchall()

    target_title = (target["title_cn"] or target["title"] or "").lower()
    target_text = (target["raw_summary"] or "")[:500].lower()

    scored = []
    for c in candidates:
        c_title = (c["title_cn"] or c["title"] or "").lower()
        c_text = (c["raw_summary"] or "")[:500].lower()

        # Title similarity (SequenceMatcher)
        title_sim = difflib.SequenceMatcher(None, target_title, c_title).ratio()

        # Content overlap (Jaccard on word bigrams)
        def bigrams(s: str) -> set:
            words = s.split()
            return {f"{words[i]}_{words[i+1]}" for i in range(len(words)-1)} if len(words) > 1 else set(words)

        target_grams = bigrams(target_text)
        candidate_grams = bigrams(c_text)
        if target_grams and candidate_grams:
            jaccard = len(target_grams & candidate_grams) / len(target_grams | candidate_grams)
        else:
            jaccard = 0.0

        # Combined score (weighted)
        score = title_sim * 0.6 + jaccard * 0.4
        if score > 0.2:
            scored.append((score, c))

    # Sort by score descending, return top N
    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, row in scored[:limit]:
        r = dict(row)
        r["similarity"] = round(score, 3)
        results.append(r)

    return results


@app.post("/api/classify/batch")
def batch_classify(source_ids: str | None = None, limit: int = 200) -> dict[str, int]:
    """Classify all unclassified non-RSS events into 4 cognitive layers."""
    from .classifier import classify_batch
    ids = source_ids.split(",") if source_ids else None
    return classify_batch(source_ids=ids, limit=limit)


@app.post("/api/classify/event/{event_id}")
def classify_single(event_id: str) -> dict[str, object]:
    """Classify a single event."""
    from .classifier import classify_event
    result = classify_event(event_id)
    return {"event_id": event_id, "classified_as": result}


# Mount ingest directory for video/audio/document file access
INGEST_ROOT = Path(__file__).resolve().parents[2] / "data" / "ingest"
INGEST_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/ingest", StaticFiles(directory=str(INGEST_ROOT)), name="ingest")

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
