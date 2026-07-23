"""Source CRUD and collection endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..collector import collect_once, fetch_url
from ..db import connect, seed_default_sources

router = APIRouter()

@router.get("/api/sources")
def list_sources() -> list[dict[str, object]]:
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


@router.put("/api/sources/{source_id}/toggle")
def toggle_source(source_id: str) -> dict[str, object]:
    with connect() as conn:
        row = conn.execute("SELECT id, enabled FROM sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Source not found")
        new_enabled = 0 if row["enabled"] else 1
        conn.execute("UPDATE sources SET enabled = ? WHERE id = ?", (new_enabled, source_id))
    return {"id": source_id, "enabled": bool(new_enabled)}


@router.post("/api/sources/{source_id}/collect")
def collect_source(source_id: str) -> dict[str, object]:
    seed_default_sources()
    result = collect_once(source_ids=[source_id], fetcher=fetch_url)
    return result


