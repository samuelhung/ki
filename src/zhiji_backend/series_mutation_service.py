"""Persistence mutations for thematic series."""

from __future__ import annotations

import json
import uuid
from typing import Any


class SeriesMutationError(Exception):
    """Raised when a series mutation cannot be completed."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def create_series(
    data,
    *,
    connect_fn,
    init_db_fn,
    datetime_cls=None,
    uuid_fn=None,
) -> dict[str, Any]:
    """Create a published series or upgrade a same-name candidate."""
    init_db_fn()
    name = data.name.strip()
    if not name:
        raise SeriesMutationError(400, "专题名称不能为空")
    member_ids = data.member_ids
    description = data.description.strip()
    if datetime_cls is None:
        datetime_cls = __import__("datetime").datetime
    if uuid_fn is None:
        uuid_fn = uuid.uuid4
    now_ts = datetime_cls.now().strftime("%Y-%m-%d %H:%M:%S")

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
            series_id = f"series-{uuid_fn().hex[:12]}"
            conn.execute(
                "INSERT INTO series (id, name, description, member_ids, status, updated_at) VALUES (?, ?, ?, ?, 'published', ?)",
                (series_id, name, description, json.dumps(member_ids), now_ts),
            )

    return {"id": series_id, "name": name}


def delete_series(series_id: str, *, connect_fn, init_db_fn) -> dict[str, Any]:
    """Delete a series."""
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id FROM series WHERE id = ?", (series_id,)
        ).fetchone()
        if not row:
            raise SeriesMutationError(404, "专题不存在")
        conn.execute("DELETE FROM series WHERE id = ?", (series_id,))
    return {"deleted": series_id}


def update_series(
    series_id: str, data: dict[str, Any], *, connect_fn, init_db_fn
) -> dict[str, Any]:
    """Update the supported series metadata fields."""
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id FROM series WHERE id = ?", (series_id,)
        ).fetchone()
        if not row:
            raise SeriesMutationError(404, "专题不存在")
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


def merge_series(data, *, connect_fn, init_db_fn, datetime_cls) -> dict[str, Any]:
    """Merge a source series into a target series."""
    init_db_fn()
    source_id = data.source_id
    target_id = data.target_id
    if source_id == target_id:
        raise SeriesMutationError(400, "不能合并同一个专题")

    with connect_fn() as conn:
        source = conn.execute(
            "SELECT * FROM series WHERE id = ?", (source_id,)
        ).fetchone()
        if not source:
            raise SeriesMutationError(404, f"源专题不存在: {source_id}")
        target = conn.execute(
            "SELECT * FROM series WHERE id = ?", (target_id,)
        ).fetchone()
        if not target:
            raise SeriesMutationError(404, f"目标专题不存在: {target_id}")

        try:
            source_ids = json.loads(source["member_ids"])
        except (json.JSONDecodeError, TypeError):
            source_ids = []
        try:
            target_ids = json.loads(target["member_ids"])
        except (json.JSONDecodeError, TypeError):
            target_ids = []

        target_set = set(target_ids)
        new_from_source = [
            member_id for member_id in source_ids if member_id not in target_set
        ]
        merged = target_ids + new_from_source

        now_ts = datetime_cls.now().strftime("%Y-%m-%d %H:%M:%S")
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


def reorder_series(series_id: str, data, *, connect_fn, init_db_fn) -> dict[str, Any]:
    """Persist a series member order."""
    init_db_fn()
    member_ids = data.member_ids
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id FROM series WHERE id = ?", (series_id,)
        ).fetchone()
        if not row:
            raise SeriesMutationError(404, "专题不存在")
        conn.execute(
            "UPDATE series SET sort_order = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps(member_ids),
                __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
                series_id,
            ),
        )
    return {"id": series_id, "member_ids": member_ids}


def add_series_members(
    series_id: str, data, *, connect_fn, init_db_fn
) -> dict[str, Any]:
    """Append new event IDs to a series."""
    init_db_fn()
    new_ids = data.event_ids

    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id, member_ids FROM series WHERE id = ?", (series_id,)
        ).fetchone()
        if not row:
            raise SeriesMutationError(404, "专题不存在")
        try:
            existing = json.loads(row["member_ids"])
        except (json.JSONDecodeError, TypeError):
            existing = []
        merged = existing + [
            event_id for event_id in new_ids if event_id not in existing
        ]
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
