"""Translation endpoints for event content."""
from __future__ import annotations

import os
from fastapi import APIRouter
from ..db import connect
from ..translator import translate, translate_title
from ..models import TranslateRequest

router = APIRouter()


@router.post("/api/translate/run")
def run_translation(request: TranslateRequest | None = None) -> dict[str, object]:
    """Translate all pending events (title_cn IS NULL and translation_status='pending').
    Uses concurrent workers for parallel translation (max 5 at a time)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from threading import Lock

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


@router.post("/api/translate/backfill")
def backfill_translation(request: TranslateRequest | None = None) -> dict[str, object]:
    """Mark all events without Chinese translation as pending, then translate."""
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



