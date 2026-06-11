"""Affairs API — CRUD + AI analysis pipeline."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import connect, init_db

router = APIRouter(prefix="/api/affairs", tags=["affairs"])


class CreateAffairRequest(BaseModel):
    body: str


class UpdateAffairRequest(BaseModel):
    title: str | None = None
    body: str | None = None
    status: str | None = None
    push_enabled: bool | None = None
    push_targets_json: str | None = None


@router.get("")
def list_affairs(status: str = "", search: str = "", limit: int = 50, offset: int = 0):
    """List affairs, optionally filtered by status and search query."""
    init_db()
    clauses = []
    params: list = []

    if status and status != "all":
        clauses.append("status = ?")
        params.append(status)
    if search:
        clauses.append("(title LIKE ? OR body LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])

    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM affairs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        total_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM affairs {where}",
            params[:-2],
        ).fetchone()

    return {
        "items": [_row_to_dict(r) for r in rows],
        "total": total_row["cnt"] if total_row else 0,
    }


@router.get("/{affair_id}")
def get_affair(affair_id: str):
    """Get a single affair by ID."""
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM affairs WHERE id = ?", (affair_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Affair not found")
    return _row_to_dict(row)


@router.post("")
def create_affair(req: CreateAffairRequest):
    """Create a new affair and trigger AI analysis + event relevance evaluation."""
    init_db()
    affair_id = f"af-{uuid.uuid4().hex[:12]}"

    with connect() as conn:
        conn.execute(
            """INSERT INTO affairs (id, body, status)
               VALUES (?, ?, 'analyzing')""",
            (affair_id, req.body.strip()),
        )

    body = req.body.strip()

    # Step 1: AI judgment
    try:
        _run_affair_analysis(affair_id, body)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Affair %s analysis failed: %s", affair_id, e)
        with connect() as conn:
            conn.execute(
                "UPDATE affairs SET status = 'pending', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (affair_id,),
            )

    # Step 2: Event relevance evaluation (non-blocking — failure doesn't affect affair creation)
    try:
        _run_affair_event_evaluation(affair_id, body)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Affair %s event evaluation failed: %s", affair_id, e)

    return get_affair(affair_id)


@router.put("/{affair_id}")
def update_affair(affair_id: str, req: UpdateAffairRequest):
    """Update an affair (title, body, status, push settings)."""
    init_db()
    with connect() as conn:
        existing = conn.execute("SELECT * FROM affairs WHERE id = ?", (affair_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Affair not found")

    sets = []
    params: list = []
    if req.title is not None:
        sets.append("title = ?")
        params.append(req.title)
    if req.body is not None:
        sets.append("body = ?")
        params.append(req.body)
    if req.status is not None:
        sets.append("status = ?")
        params.append(req.status)
    if req.push_enabled is not None:
        sets.append("push_enabled = ?")
        params.append(1 if req.push_enabled else 0)
    if req.push_targets_json is not None:
        sets.append("push_targets_json = ?")
        params.append(req.push_targets_json)

    if not sets:
        return get_affair(affair_id)

    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(affair_id)

    with connect() as conn:
        conn.execute(
            f"UPDATE affairs SET {', '.join(sets)} WHERE id = ?",
            params,
        )

    return get_affair(affair_id)


@router.post("/{affair_id}/retry")
def retry_analysis(affair_id: str):
    """Retry AI analysis for an affair."""
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM affairs WHERE id = ?", (affair_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Affair not found")

    body = row["body"]
    _run_affair_analysis(affair_id, body)
    _run_affair_event_evaluation(affair_id, body)
    return get_affair(affair_id)


@router.post("/{affair_id}/evaluate")
def evaluate_events(affair_id: str):
    """Evaluate relevance of all events to this affair."""
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM affairs WHERE id = ?", (affair_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Affair not found")
    
    _run_affair_event_evaluation(affair_id, row["body"])
    return get_affair(affair_id)


@router.get("/{affair_id}/relevance")
def get_relevance(affair_id: str):
    """Get event relevance data for an affair."""
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """SELECT aer.event_id, aer.relevance, aer.reason,
                      e.title, e.title_cn, e.topic, e.source_id
               FROM affair_event_relevance aer
               JOIN events e ON aer.event_id = e.id
               WHERE aer.affair_id = ?
               ORDER BY CASE aer.relevance WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END""",
            (affair_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _run_affair_analysis(affair_id: str, body: str):
    """Run AI judgment on an affair and update the record."""
    with connect() as conn:
        conn.execute(
            "UPDATE affairs SET status = 'analyzing', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (affair_id,),
        )
    from ..affairs_ai import analyze_affair
    result = analyze_affair(affair_id, body)
    with connect() as conn:
        if result:
            conn.execute(
                """UPDATE affairs SET
                   title = ?, status = 'judged',
                   ai_judgment_json = ?,
                   related_events_json = ?,
                   related_questions_json = ?,
                   updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (
                    result.get("summary", "")[:200],
                    json.dumps(result, ensure_ascii=False),
                    json.dumps([e["event_id"] for e in result.get("related_events", [])]),
                    json.dumps([q["question_id"] for q in result.get("related_questions", [])]),
                    affair_id,
                ),
            )
        else:
            conn.execute(
                "UPDATE affairs SET status = 'pending', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (affair_id,),
            )


def _run_affair_event_evaluation(affair_id: str, body: str):
    """Evaluate relevance of ALL events to an affair and cache results.
    
    Fetches all events, evaluates in batches (30 per AI call), merges results.
    """
    import logging
    from ..affairs_ai import evaluate_affair_events
    
    # Step 1: Get ALL events
    with connect() as conn:
        events = conn.execute(
            "SELECT id, title, title_cn, raw_summary, summary_cn FROM events WHERE status = 'new' ORDER BY created_at DESC"
        ).fetchall()
    candidates = [dict(e) for e in events]
    
    if not candidates:
        return
    
    # Step 2: Batch evaluate (30 per AI call to keep input/output within limits)
    BATCH_SIZE = 30
    all_results = []
    total = len(candidates)
    
    for i in range(0, total, BATCH_SIZE):
        batch = candidates[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        logging.getLogger(__name__).info("Affair %s: evaluating batch %d/%d (%d events)", 
                                          affair_id, batch_num, total_batches, len(batch))
        results = evaluate_affair_events(affair_id, body, batch)
        all_results.extend(results)
    
    # Step 3: Save all results (replace existing)
    with connect() as conn:
        conn.execute("DELETE FROM affair_event_relevance WHERE affair_id = ?", (affair_id,))
        for r in all_results:
            conn.execute(
                "INSERT INTO affair_event_relevance (affair_id, event_id, relevance, reason, judged_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (affair_id, r.get("event_id", ""), r.get("relevance", "low"), r.get("reason", "")),
            )
    logging.getLogger(__name__).info("Affair %s: saved %d event relevance results (%d batches)", 
                                     affair_id, len(all_results), total_batches)


@router.delete("/{affair_id}")
def delete_affair(affair_id: str):
    """Delete an affair."""
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM affairs WHERE id = ?", (affair_id,))
    return {"deleted": True}


def _row_to_dict(row) -> dict:
    d = dict(row)
    # Parse JSON columns for API response
    for col in ("ai_judgment_json", "related_events_json", "related_questions_json", "push_targets_json"):
        if d.get(col) and isinstance(d[col], str):
            try:
                d[col] = json.loads(d[col])
            except (json.JSONDecodeError, TypeError):
                d[col] = [] if "json" in col else None
    return d
