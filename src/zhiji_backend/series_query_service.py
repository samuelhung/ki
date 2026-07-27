"""Read-only persistence operations for thematic series."""

from __future__ import annotations

import difflib
import json
from typing import Any


class SeriesQueryError(LookupError):
    """Raised when a requested series does not exist."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def name_similarity(a: str, b: str) -> float:
    """Return the difflib similarity ratio for two normalized series names."""
    return difflib.SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def member_overlap_score(ids_a: list[str], ids_b: list[str]) -> float:
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
    connect_fn,
    init_db_fn,
) -> dict[str, Any]:
    """List series with their member event titles."""
    init_db_fn()
    with connect_fn() as conn:
        fields = "id, name, description, member_ids, status, created_at, updated_at"
        if include_candidates:
            rows = conn.execute(
                f"SELECT {fields} FROM series ORDER BY created_at DESC"
            ).fetchall()
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
    *,
    connect_fn,
    init_db_fn,
    name_similarity_fn,
    member_overlap_score_fn,
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
            name_sim = name_similarity_fn(series["name"], other["name"])
            if name_sim >= 0.5:
                try:
                    other_ids = json.loads(other["member_ids"])
                except (json.JSONDecodeError, TypeError):
                    other_ids = []
                member_sim = member_overlap_score_fn(member_ids, other_ids)
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


def get_series_detail(series_id: str, *, connect_fn, init_db_fn) -> dict[str, Any]:
    """Return series metadata and enriched member events."""
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute("SELECT * FROM series WHERE id = ?", (series_id,)).fetchone()
        if not row:
            raise SeriesQueryError("专题不存在")
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
            remaining = [
                member_id for member_id in member_ids if member_id not in ordered
            ]
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


def get_series_suggestions(series_id: str, *, connect_fn, init_db_fn) -> dict[str, Any]:
    """Return pending event suggestions for a series."""
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id, member_ids FROM series WHERE id = ?", (series_id,)
        ).fetchone()
        if not row:
            raise SeriesQueryError("专题不存在")
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
                        if (
                            entry.get("series_id") == series_id
                            and event["id"] not in member_ids
                        ):
                            suggestions.append(
                                {
                                    "event_id": event["id"],
                                    "reason": entry.get("reason", ""),
                                }
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
