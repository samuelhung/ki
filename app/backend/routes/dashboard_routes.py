"""Dashboard, health, stats, and topic-count endpoints."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from ..db import connect, init_db

router = APIRouter()

# Server start timestamp for uptime calculation
_start_time = time.time()


@router.get("/api/health")
def health() -> dict[str, object]:
    uptime_sec = time.time() - _start_time
    db_ok = True
    db_error = None
    db_size_mb = 0
    db_event_count = 0
    try:
        with connect() as conn:
            db_size_mb = round(
                conn.execute("PRAGMA page_count").fetchone()[0]
                * conn.execute("PRAGMA page_size").fetchone()[0]
                / 1024 / 1024,
                2,
            )
            db_event_count = conn.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]
    except Exception as e:
        db_ok = False
        db_error = str(e)

    return {
        "ok": db_ok,
        "service": "knowledge-intelligence",
        "version": "1.7.4",
        "uptime_sec": round(uptime_sec, 1),
        "database": {
            "ok": db_ok,
            "size_mb": db_size_mb,
            "event_count": db_event_count,
            "error": db_error,
        },
    }


@router.get("/api/ingest/stats")
def ingest_stats() -> dict[str, int]:
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


@router.get("/api/dashboard/summary")
def dashboard_summary() -> dict[str, int]:
    with connect() as conn:
        sources_enabled = conn.execute("SELECT COUNT(*) FROM sources WHERE enabled = 1").fetchone()[0]
        today_ingest = conn.execute(
            "SELECT COUNT(*) FROM events WHERE date(created_at) = date('now') AND source_id IN ('douyin','user-upload')"
        ).fetchone()[0]
        today_brainstorm = conn.execute(
            "SELECT COUNT(*) FROM brainstorm_questions WHERE date(created_at) = date('now')"
        ).fetchone()[0]
        ingest_total = conn.execute(
            "SELECT COUNT(*) FROM events WHERE source_id IN ('douyin','user-upload')"
        ).fetchone()[0]
        brainstorm_total = conn.execute("SELECT COUNT(*) FROM brainstorm_questions").fetchone()[0]
    return {
        "sources_enabled": int(sources_enabled),
        "today_new": int(today_ingest) + int(today_brainstorm),
        "ingest_total": int(ingest_total),
        "brainstorm_total": int(brainstorm_total),
    }


@router.get("/api/dashboard/trend")
def dashboard_trend(days: int = 7) -> list[dict[str, object]]:
    """Return daily event counts for the last N days."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT date(created_at) as day, COUNT(*) as count
               FROM events
               WHERE created_at >= date('now', ?)
               GROUP BY day ORDER BY day""",
            (f"-{days} days",),
        ).fetchall()
    return [{"day": r["day"], "count": r["count"]} for r in rows]
