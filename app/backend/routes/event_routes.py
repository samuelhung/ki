"""Event CRUD, collection, summarization, tagging, similar, and classification endpoints."""
from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from ..db import connect, init_db, seed_default_sources
from ..summarizer import summarize_transcript
from ..collector import collect_once, fetch_url
from ..tagger import tag_event
from ..classifier import classify_event, classify_batch
from ..models import CollectRequest

router = APIRouter()


@router.get("/api/events")
def list_events(
    topic: str | None = None, status: str | None = None,
    source_id: str | None = None, content_type: str | None = None,
    search: str | None = None, offset: int = 0, limit: int = 50,
    count: int = 0,
) -> list[dict[str, object]] | dict[str, object]:
    # Lightweight columns for list views (omit large text fields: raw_summary, ai_summary)
    _LIST_COLS = (
        "id, source_id, title, url, published_at,"
        " title_cn, summary_cn, translation_status, translation_error,"
        " topic, importance, actionability, decision, status,"
        " video_path, content_type, created_at"
    )
    if search:
        # FTS5 full-text search with trigram tokenizer (works for Chinese + English)
        # For very short terms (< 3 chars) use LIKE fallback since trigram needs >=3 chars
        search_term = search.strip()
        # Quote each word to prevent FTS5 from misinterpreting AND/OR/NOT as operators
        search = ' '.join(f'"{w}"' for w in search_term.split() if w)
        if len(search_term) < 3:
            with connect() as conn:
                like_pattern = f"%{search_term}%"
                rows = conn.execute(
                    f"""SELECT {_LIST_COLS}
                    FROM events
                    WHERE title LIKE ? OR title_cn LIKE ? OR raw_summary LIKE ? OR summary_cn LIKE ? OR ai_summary LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?""",
                    (like_pattern, like_pattern, like_pattern, like_pattern, like_pattern,
                     max(1, min(200, limit)), max(0, offset)),
                ).fetchall()
            return [dict(row) for row in rows]
        # Prefix each column with 'e.' for the JOIN with events_fts
        _fts_cols = ', '.join(f'e.{c.strip()}' for c in _LIST_COLS.split(','))
        with connect() as conn:
            rows = conn.execute(
                f"""SELECT {_fts_cols},
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
        "SELECT id, source_id, title, url, published_at,\n"
        "       title_cn, summary_cn, translation_status, translation_error,\n"
        "       topic, importance, actionability, decision, status,\n"
        "       video_path, content_type, created_at\n"
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
    if content_type:
        query += " AND content_type = :content_type"
        params["content_type"] = content_type
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


@router.get("/api/events/topic-counts")
def event_topic_counts() -> dict[str, int]:
    """Return event counts per topic for content ingest tabs."""
    topics = ["格局", "财富", "认知", "前瞻"]
    result: dict[str, int] = {}
    with connect() as conn:
        for t in topics:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM events WHERE topic = ? AND source_id IN ('douyin','user-upload','user-concept')",
                (t,),
            ).fetchone()[0]
            result[t] = int(cnt)
        # briefing count: events from RSS sources (not douyin/user-upload)
        briefing_cnt = conn.execute(
            "SELECT COUNT(*) FROM events WHERE source_id NOT IN ('douyin','user-upload','user-concept','')"
        ).fetchone()[0]
        result["briefing"] = int(briefing_cnt)
    return result


@router.get("/api/events/{event_id}")
def get_event(event_id: str) -> dict[str, object]:
    """Get full event detail including complete transcript."""
    with connect() as conn:
        row = conn.execute(
            """SELECT id, source_id, title, url, published_at, raw_summary, ai_summary,
               title_cn, summary_cn, translation_status, translation_error,
               topic, importance, actionability, decision, status, tags_json,
               last_error, progress_stages, video_path, created_at, overview
               FROM events WHERE id = ?""",
            (event_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    result = dict(row)
    # Add ingest file paths
    ingest_root = Path(__file__).resolve().parents[3] / "data" / "ingest"
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


@router.delete("/api/events/{event_id}")
def delete_event(event_id: str) -> dict[str, object]:
    """Delete an event and its associated ingest files."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, video_path, audio_path, document_path FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")

    # Clean up ingest files
    ingest_root = Path(__file__).resolve().parents[3] / "data" / "ingest"
    (ingest_root / "transcripts" / f"{event_id}.md").unlink(missing_ok=True)
    (ingest_root / "summaries" / f"{event_id}.md").unlink(missing_ok=True)

    for path_col in ("video_path", "audio_path", "document_path"):
        p = row[path_col]
        if p:
            Path(p).unlink(missing_ok=True)

    with connect() as conn:
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    return {"ok": True, "deleted": event_id}


@router.post("/api/events/batch-delete")
def batch_delete_events(payload: dict[str, object]) -> dict[str, object]:
    """Delete multiple events and their associated ingest files."""
    event_ids = payload.get("event_ids", [])
    if not isinstance(event_ids, list) or not event_ids:
        raise HTTPException(status_code=400, detail="event_ids must be a non-empty list")
    ingest_root = Path(__file__).resolve().parents[3] / "data" / "ingest"
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


@router.post("/api/events/{event_id}/summarize")
def summarize_event(event_id: str, background_tasks: BackgroundTasks, force: bool = False) -> dict[str, object]:
    """Generate an AI summary for a douyin event using the Knowledge template.

    Set ?force=true to bypass the cache and regenerate from scratch.
    """

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

    # Return cached summary if already generated (unless forced)
    if row["ai_summary"] and not force:
        return {"event_id": event_id, "summary": row["ai_summary"], "cached": True}

    # When forcing regeneration, clear the old summary so polling doesn't pick it up
    if force and row["ai_summary"]:
        with connect() as conn:
            conn.execute("UPDATE events SET ai_summary = NULL, overview = NULL WHERE id = ?", (event_id,))

    def _run_summary():
        try:
            result = summarize_transcript(transcript, title=title)
            if result:
                summary = result.get("summary", "")
                overview = result.get("overview", "")
                with connect() as conn:
                    conn.execute(
                        "UPDATE events SET ai_summary = ?, overview = COALESCE(?, overview) WHERE id = ?",
                        (summary, overview, event_id),
                    )
                # Also write to file system
                summaries_dir = Path(__file__).resolve().parents[3] / "data" / "ingest" / "summaries"
                summaries_dir.mkdir(parents=True, exist_ok=True)
                (summaries_dir / f"{event_id}.md").write_text(summary, encoding="utf-8")
        except Exception as e:
            logger.exception("Background summary failed for %s: %s", event_id, e)

    background_tasks.add_task(_run_summary)
    return {"event_id": event_id, "status": "processing", "cached": False}


@router.post("/api/collect")
def collect(request: CollectRequest) -> dict[str, object]:
    seed_default_sources()
    return collect_once(source_ids=request.source_ids, fetcher=fetch_url)


class TagRequest(BaseModel):
    limit: int = 50


@router.post("/api/events/{event_id}/tag")
def tag_single_event(event_id: str) -> dict[str, object]:
    """Extract tags for a single event using DeepSeek NER."""

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


@router.post("/api/tag/batch")
def tag_batch(request: TagRequest | None = None) -> dict[str, object]:
    """Batch-tag untagged events (max N at a time)."""

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


@router.get("/api/events/{event_id}/similar")
def similar_events(event_id: str, limit: int = 5) -> list[dict[str, object]]:
    """Find events similar to the given event by FTS5 + title/content overlap."""
    import difflib

    with connect() as conn:
        target = conn.execute(
            "SELECT id, title, title_cn, raw_summary FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Event not found")

        target_title = (target["title_cn"] or target["title"] or "")
        # FTS5 trigram pre-filter: use cleaned title keywords to narrow candidates
        # Remove special chars, split into words
        clean = "".join(c if c.isalnum() or c.isspace() else " " for c in target_title)
        keywords = [w for w in clean.split() if len(w) > 1]
        if keywords:
            fts_query = " OR ".join(keywords[:12])  # limit keywords to avoid FTS5 complexity
            try:
                candidates = conn.execute(
                    """SELECT e.id, e.source_id, e.title, e.title_cn, e.raw_summary, e.url, e.topic, e.created_at
                       FROM events e
                       INNER JOIN events_fts fts ON e.id = fts.event_id
                       WHERE e.id != ? AND e.status = 'new' AND events_fts MATCH ?
                       ORDER BY rank LIMIT 100""",
                    (event_id, fts_query),
                ).fetchall()
            except Exception:
                candidates = []
        else:
            candidates = []
        # Fallback: if FTS5 returned nothing or failed, use recent events
        if not candidates:
            candidates = conn.execute(
                """SELECT id, source_id, title, title_cn, raw_summary, url, topic, created_at
                   FROM events WHERE id != ? AND status = 'new'
                   ORDER BY created_at DESC LIMIT 100""",
                (event_id,),
            ).fetchall()

    target_title_lower = target_title.lower()
    target_text = (target["raw_summary"] or "")[:500].lower()

    scored = []
    for c in candidates:
        c_title = (c["title_cn"] or c["title"] or "").lower()
        c_text = (c["raw_summary"] or "")[:500].lower()

        # Title similarity (SequenceMatcher)
        title_sim = difflib.SequenceMatcher(None, target_title_lower, c_title).ratio()

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


@router.post("/api/classify/batch")
def batch_classify(source_ids: str | None = None, limit: int = 200) -> dict[str, int]:
    """Classify all unclassified non-RSS events into 4 cognitive layers."""
    ids = source_ids.split(",") if source_ids else None
    return classify_batch(source_ids=ids, limit=limit)


@router.post("/api/classify/event/{event_id}")
def classify_single(event_id: str) -> dict[str, object]:
    """Classify a single event."""
    result = classify_event(event_id)
    return {"event_id": event_id, "classified_as": result}
