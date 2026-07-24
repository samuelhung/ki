"""Candidate de-duplication, cleanup, and persistence for series discovery."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from typing import Any

from .series_service import member_overlap_score, name_similarity

type ConnectFn = Callable[[], AbstractContextManager[sqlite3.Connection]]


def _find_duplicate(
    conn: sqlite3.Connection,
    new_name: str,
    new_member_ids: list[str],
    threshold_name: float = 0.7,
    threshold_member: float = 0.5,
) -> tuple[bool, dict[str, Any] | None]:
    """Check whether a candidate duplicates a candidate or published series."""
    rows = conn.execute(
        "SELECT id, name, description, member_ids, status FROM series "
        "WHERE status IN ('candidate', 'published')"
    ).fetchall()
    for row in rows:
        name_sim = name_similarity(new_name, row["name"])
        try:
            existing_ids = json.loads(row["member_ids"])
        except (json.JSONDecodeError, TypeError):
            existing_ids = []
        member_sim = member_overlap_score(new_member_ids, existing_ids)
        if name_sim >= threshold_name or (
            name_sim >= 0.5 and member_sim >= threshold_member
        ):
            return True, dict(row)
    return False, None


def _cleanup_stale_candidates(conn: sqlite3.Connection, max_age_days: int = 7) -> int:
    """Delete candidate series older than ``max_age_days``."""
    cutoff = (datetime.now() - timedelta(days=max_age_days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    cursor = conn.execute(
        "DELETE FROM series WHERE status = 'candidate' AND created_at < ?", (cutoff,)
    )
    return cursor.rowcount


def persist_candidate(
    conn: sqlite3.Connection,
    candidate: dict[str, Any],
    member_ids: list[str],
    *,
    now_ts: str | None = None,
) -> str:
    """Insert a candidate, or update an existing candidate with the same name."""
    now_ts = now_ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing_candidate = conn.execute(
        "SELECT id FROM series WHERE name = ? AND status = 'candidate'",
        (candidate["name"],),
    ).fetchone()

    if existing_candidate:
        conn.execute(
            "UPDATE series SET description = ?, member_ids = ?, updated_at = ? WHERE id = ?",
            (
                candidate.get("description", ""),
                json.dumps(member_ids),
                now_ts,
                existing_candidate["id"],
            ),
        )
        return existing_candidate["id"]

    series_id = f"series-{uuid.uuid4().hex[:12]}"
    conn.execute(
        "INSERT INTO series (id, name, description, member_ids, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'candidate', ?, ?)",
        (
            series_id,
            candidate.get("name", ""),
            candidate.get("description", ""),
            json.dumps(member_ids),
            now_ts,
            now_ts,
        ),
    )
    return series_id


def persist_discovered_candidates(
    candidates: list[dict[str, Any]],
    *,
    connect_fn: ConnectFn,
    clean_stale: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Resolve titles, skip duplicates, and persist discovery candidates."""
    member_id_set = {
        member_id
        for candidate in candidates
        for member_id in candidate.get("member_ids", [])
    }
    persisted: list[dict[str, Any]] = []
    skipped_dupes: list[dict[str, Any]] = []
    stale_cleaned = 0
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with connect_fn() as conn:
        if clean_stale:
            stale_cleaned = _cleanup_stale_candidates(conn)

        title_map: dict[str, str] = {}
        if member_id_set:
            placeholders = ",".join(["?" for _ in member_id_set])
            title_rows = conn.execute(
                f"SELECT id, title FROM events WHERE id IN ({placeholders})",
                list(member_id_set),
            ).fetchall()
            title_map = {row["id"]: row["title"] for row in title_rows}

        for candidate in candidates:
            member_ids = candidate.get("member_ids", [])
            candidate["member_titles"] = [
                title_map.get(member_id, "(已删除)") for member_id in member_ids
            ]

            is_duplicate, existing = _find_duplicate(
                conn, candidate.get("name", ""), member_ids
            )
            if is_duplicate:
                candidate["_duplicate_of"] = {
                    "id": existing["id"],
                    "name": existing["name"],
                    "status": existing["status"],
                }
                skipped_dupes.append(candidate)
                continue

            candidate["_persisted_id"] = persist_candidate(
                conn, candidate, member_ids, now_ts=now_ts
            )
            persisted.append(candidate)

    return persisted, skipped_dupes, stale_cleaned
