"""Persistence and CRUD operations for thematic series."""

from __future__ import annotations

import difflib
import json
import sqlite3
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Protocol

from fastapi import HTTPException

from .db import connect, init_db

type Identifier = str
type IdentifierList = list[Identifier]
type ConnectFn = Callable[[], AbstractContextManager[sqlite3.Connection]]
type InitDbFn = Callable[[], None]


class SeriesCreateData(Protocol):
    name: str
    member_ids: IdentifierList
    description: str


class SeriesOrderData(Protocol):
    member_ids: IdentifierList


class SeriesMembersData(Protocol):
    event_ids: IdentifierList


class SeriesMergeData(Protocol):
    source_id: Identifier
    target_id: Identifier


def name_similarity(a: str, b: str) -> float:
    """Return the difflib similarity ratio for two normalized series names."""
    return difflib.SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def member_overlap_score(ids_a: IdentifierList, ids_b: IdentifierList) -> float:
    """Return the Jaccard similarity for two member ID collections."""
    if not ids_a or not ids_b:
        return 0.0
    set_a, set_b = set(ids_a), set(ids_b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def list_series(
    include_candidates: bool = False,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    """List series with their member event titles."""
    init_db_fn()
    with connect_fn() as conn:
        fields = "id, name, description, member_ids, status, created_at, updated_at"
        if include_candidates:
            rows = conn.execute(f"SELECT {fields} FROM series ORDER BY created_at DESC").fetchall()
        else:
            rows = conn.execute(
                f"SELECT {fields} FROM series WHERE status != 'candidate' ORDER BY created_at DESC"
            ).fetchall()

        parsed_ids = {}
        all_member_ids = []
        for row in rows:
            try:
                member_ids = json.loads(row["member_ids"] or "[]")
            except (json.JSONDecodeError, TypeError):
                member_ids = []
            parsed_ids[row["id"]] = member_ids
            all_member_ids.extend(member_ids)

        title_map = {}
        unique_member_ids = list(dict.fromkeys(all_member_ids))
        if unique_member_ids:
            placeholders = ",".join(["?" for _ in unique_member_ids])
            event_rows = conn.execute(
                f"SELECT id, title FROM events WHERE id IN ({placeholders})",
                unique_member_ids,
            ).fetchall()
            title_map = {row["id"]: row["title"] for row in event_rows}

        items = []
        for row in rows:
            series = dict(row)
            series["members"] = [
                {"id": member_id, "title": title_map.get(member_id, "(已删除)")}
                for member_id in parsed_ids[row["id"]]
            ]
            items.append(series)

    return {"items": items}


def list_candidates(
    *, connect_fn: ConnectFn = connect, init_db_fn: InitDbFn = init_db
) -> dict[str, Any]:
    """List candidate series with member titles and duplicate hints."""
    init_db_fn()
    with connect_fn() as conn:
        candidate_rows = conn.execute(
            "SELECT * FROM series WHERE status = 'candidate' ORDER BY created_at DESC"
        ).fetchall()

    items = []
    for row in candidate_rows:
        series = dict(row)
        try:
            member_ids = json.loads(series.get("member_ids", "[]"))
        except (json.JSONDecodeError, TypeError):
            member_ids = []
        series["member_count"] = len(member_ids)

        members = []
        if member_ids:
            with connect_fn() as conn:
                placeholders = ",".join(["?" for _ in member_ids])
                event_rows = conn.execute(
                    f"SELECT id, title FROM events WHERE id IN ({placeholders})",
                    member_ids,
                ).fetchall()
                title_map = {event["id"]: event["title"] for event in event_rows}
                for member_id in member_ids:
                    members.append(
                        {"id": member_id, "title": title_map.get(member_id, "(已删除)")}
                    )
        series["members"] = members

        similar = []
        with connect_fn() as conn:
            all_others = conn.execute(
                "SELECT id, name, status, member_ids FROM series WHERE id != ? AND status IN ('candidate', 'published')",
                (series["id"],),
            ).fetchall()
        for other in all_others:
            name_sim = name_similarity(series["name"], other["name"])
            if name_sim >= 0.5:
                try:
                    other_ids = json.loads(other["member_ids"])
                except (json.JSONDecodeError, TypeError):
                    other_ids = []
                member_sim = member_overlap_score(member_ids, other_ids)
                similar.append(
                    {
                        "id": other["id"],
                        "name": other["name"],
                        "status": other["status"],
                        "name_similarity": round(name_sim, 3),
                        "member_overlap": round(member_sim, 3),
                    }
                )
        series["similar_to"] = similar
        items.append(series)

    return {"items": items, "total": len(items)}


def create_series(
    data: SeriesCreateData,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    """Create a published series or upgrade a same-name candidate."""
    init_db_fn()
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="专题名称不能为空")
    member_ids = data.member_ids
    description = data.description.strip()
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with connect_fn() as conn:
        existing = conn.execute(
            "SELECT id FROM series WHERE name = ? AND status = 'candidate'",
            (name,),
        ).fetchone()
        if existing:
            series_id = existing["id"]
            conn.execute(
                "UPDATE series SET description = ?, member_ids = ?, status = 'published', updated_at = ? WHERE id = ?",
                (description, json.dumps(member_ids), now_ts, series_id),
            )
        else:
            series_id = f"series-{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO series (id, name, description, member_ids, status, updated_at) VALUES (?, ?, ?, ?, 'published', ?)",
                (series_id, name, description, json.dumps(member_ids), now_ts),
            )

    return {"id": series_id, "name": name}


def delete_series(
    series_id: Identifier,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    """Delete a series."""
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute("SELECT id FROM series WHERE id = ?", (series_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")
        conn.execute("DELETE FROM series WHERE id = ?", (series_id,))
    return {"deleted": series_id}


def update_series(
    series_id: Identifier,
    data: dict[str, Any],
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    """Update the supported series metadata fields."""
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute("SELECT id FROM series WHERE id = ?", (series_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")
        updates = []
        params = []
        for field in ["name", "description", "status"]:
            if field in data:
                updates.append(f"{field} = ?")
                params.append(data[field])
        if updates:
            params.append(series_id)
            conn.execute(
                f"UPDATE series SET {', '.join(updates)}, updated_at = datetime('now', 'localtime') WHERE id = ?",
                params,
            )
    return {"updated": series_id}


def merge_series(
    data: SeriesMergeData,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    """Merge a source series into a target series."""
    init_db_fn()
    source_id = data.source_id
    target_id = data.target_id
    if source_id == target_id:
        raise HTTPException(status_code=400, detail="不能合并同一个专题")

    with connect_fn() as conn:
        source = conn.execute("SELECT * FROM series WHERE id = ?", (source_id,)).fetchone()
        if not source:
            raise HTTPException(status_code=404, detail=f"源专题不存在: {source_id}")
        target = conn.execute("SELECT * FROM series WHERE id = ?", (target_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail=f"目标专题不存在: {target_id}")

        try:
            source_ids = json.loads(source["member_ids"])
        except (json.JSONDecodeError, TypeError):
            source_ids = []
        try:
            target_ids = json.loads(target["member_ids"])
        except (json.JSONDecodeError, TypeError):
            target_ids = []

        target_set = set(target_ids)
        new_from_source = [member_id for member_id in source_ids if member_id not in target_set]
        merged = target_ids + new_from_source

        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE series SET member_ids = ?, updated_at = ? WHERE id = ?",
            (json.dumps(merged), now_ts, target_id),
        )
        conn.execute("DELETE FROM series WHERE id = ?", (source_id,))
        conn.execute("DELETE FROM series_scan_cache WHERE series_id = ?", (target_id,))

        return {
            "merged": True,
            "source": {"id": source_id, "name": source["name"], "deleted": True},
            "target": {
                "id": target_id,
                "name": target["name"],
                "member_ids": merged,
                "members_added": len(new_from_source),
                "total_members": len(merged),
            },
        }


def get_series_detail(
    series_id: Identifier,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    """Return series metadata and enriched member events."""
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute("SELECT * FROM series WHERE id = ?", (series_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")
        series = dict(row)
        try:
            member_ids = json.loads(series.get("member_ids", "[]"))
        except (json.JSONDecodeError, TypeError):
            member_ids = []
        try:
            sort_order = json.loads(series.get("sort_order", "[]"))
        except (json.JSONDecodeError, TypeError):
            sort_order = []

        if sort_order:
            ordered = [member_id for member_id in sort_order if member_id in member_ids]
            remaining = [member_id for member_id in member_ids if member_id not in ordered]
            member_ids = ordered + remaining

        members = []
        if member_ids:
            placeholders = ",".join(["?" for _ in member_ids])
            event_rows = conn.execute(
                f"SELECT id, title, overview, url, topic, source_id, status, created_at "
                f"FROM events WHERE id IN ({placeholders})",
                member_ids,
            ).fetchall()
            event_map = {event["id"]: dict(event) for event in event_rows}
            for member_id in member_ids:
                if member_id in event_map:
                    members.append(event_map[member_id])

        series["members"] = members

        scan_cache = conn.execute(
            "SELECT scanned_at FROM series_scan_cache WHERE series_id = ?",
            (series_id,),
        ).fetchone()
        if scan_cache and scan_cache["scanned_at"]:
            since = scan_cache["scanned_at"]
        else:
            since = "1970-01-01"

        if member_ids:
            member_placeholders = ",".join(["?" for _ in member_ids])
            unscanned = conn.execute(
                f"SELECT COUNT(*) FROM events "
                f"WHERE overview IS NOT NULL AND overview != '' AND status != 'error' "
                f"AND id NOT IN ({member_placeholders}) AND created_at > ?",
                member_ids + [since],
            ).fetchone()[0]
        else:
            unscanned = conn.execute(
                "SELECT COUNT(*) FROM events "
                "WHERE overview IS NOT NULL AND overview != '' AND status != 'error' "
                "AND created_at > ?",
                (since,),
            ).fetchone()[0]
        series["unscanned_count"] = unscanned

    return series


def reorder_series(
    series_id: Identifier,
    data: SeriesOrderData,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    """Persist a series member order."""
    init_db_fn()
    member_ids = data.member_ids
    with connect_fn() as conn:
        row = conn.execute("SELECT id FROM series WHERE id = ?", (series_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")
        conn.execute(
            "UPDATE series SET sort_order = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps(member_ids),
                __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
                series_id,
            ),
        )
    return {"id": series_id, "member_ids": member_ids}


def get_series_suggestions(
    series_id: Identifier,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    """Return pending event suggestions for a series."""
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id, member_ids FROM series WHERE id = ?", (series_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")
        try:
            member_ids = set(json.loads(row["member_ids"]))
        except (json.JSONDecodeError, TypeError):
            member_ids = set()

        candidates = conn.execute(
            "SELECT id, suggested_series_json FROM events WHERE suggested_series_json IS NOT NULL AND suggested_series_json != '' AND suggested_series_json != '[]'"
        ).fetchall()

        suggestions = []
        for event in candidates:
            try:
                entries = json.loads(event["suggested_series_json"])
                if entries and isinstance(entries[0], str):
                    if series_id in entries and event["id"] not in member_ids:
                        suggestions.append({"event_id": event["id"], "reason": ""})
                else:
                    for entry in entries:
                        if entry.get("series_id") == series_id and event["id"] not in member_ids:
                            suggestions.append(
                                {"event_id": event["id"], "reason": entry.get("reason", "")}
                            )
                            break
            except (json.JSONDecodeError, TypeError):
                pass

        if not suggestions:
            return {"suggestions": []}

        suggestion_ids = [suggestion["event_id"] for suggestion in suggestions]
        reason_map = {
            suggestion["event_id"]: suggestion["reason"] for suggestion in suggestions
        }
        placeholders = ",".join(["?" for _ in suggestion_ids])
        event_rows = conn.execute(
            f"SELECT id, title, topic, created_at FROM events WHERE id IN ({placeholders})",
            suggestion_ids,
        ).fetchall()

    return {
        "suggestions": [
            {
                "id": event["id"],
                "title": event["title"],
                "topic": event["topic"] or "",
                "reason": reason_map.get(event["id"], ""),
                "created_at": event["created_at"],
            }
            for event in event_rows
        ]
    }


def add_series_members(
    series_id: Identifier,
    data: SeriesMembersData,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
) -> dict[str, Any]:
    """Append new event IDs to a series."""
    init_db_fn()
    new_ids = data.event_ids

    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id, member_ids FROM series WHERE id = ?", (series_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")
        try:
            existing = json.loads(row["member_ids"])
        except (json.JSONDecodeError, TypeError):
            existing = []
        merged = existing + [event_id for event_id in new_ids if event_id not in existing]
        conn.execute(
            "UPDATE series SET member_ids = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps(merged),
                __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
                series_id,
            ),
        )
        conn.execute("DELETE FROM series_scan_cache WHERE series_id = ?", (series_id,))
    return {"id": series_id, "member_ids": merged}
