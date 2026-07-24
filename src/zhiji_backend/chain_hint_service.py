from __future__ import annotations

import json
import re
from typing import Any, Protocol

from fastapi import HTTPException

from .chain_node_service import ConnectFn


class HintResolveRequest(Protocol):
    action: str
    edited_value: str


def list_hints(
    *, status: str, limit: int, connect_fn: ConnectFn
) -> dict[str, list[dict[str, Any]]]:
    with connect_fn() as conn:
        rows = conn.execute(
            """SELECT h.*, n.name as node_name
               FROM chain_data_hints h
               LEFT JOIN industry_chain_nodes n ON n.id = h.node_id
               WHERE h.status = ?
               ORDER BY h.created_at DESC
               LIMIT ?""",
            (status, limit),
        ).fetchall()
    return {"hints": [dict(row) for row in rows]}


def count_hints(*, connect_fn: ConnectFn) -> dict[str, int]:
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM chain_data_hints WHERE status = 'pending'"
        ).fetchone()
    return {"pending": row["cnt"] if row else 0}


def resolve_hint(
    hint_id: str,
    request: HintResolveRequest,
    *,
    connect_fn: ConnectFn,
) -> dict[str, Any]:
    with connect_fn() as conn:
        hint_row = conn.execute(
            "SELECT * FROM chain_data_hints WHERE id = ?", (hint_id,)
        ).fetchone()
        if not hint_row:
            raise HTTPException(404, "提示不存在")

        hint = dict(hint_row)
        if request.action == "accept":
            final_value = (
                request.edited_value.strip()
                if request.edited_value.strip()
                else hint["suggested_value"]
            )
            node = conn.execute(
                "SELECT global_shares, substitutes "
                "FROM industry_chain_nodes WHERE id = ?",
                (hint["node_id"],),
            ).fetchone()
            if node:
                _apply_hint_update(conn, hint, final_value, dict(node))

            conn.execute(
                """UPDATE chain_data_hints
                   SET status = 'accepted', reviewed_at = datetime('now'),
                       resolved_value = ?
                   WHERE id = ?""",
                (final_value, hint_id),
            )
        elif request.action == "reject":
            conn.execute(
                """UPDATE chain_data_hints
                   SET status = 'rejected', reviewed_at = datetime('now')
                   WHERE id = ?""",
                (hint_id,),
            )
        else:
            raise HTTPException(400, f"未知 action: {request.action}")

    return {"ok": True, "action": request.action}


def _apply_hint_update(
    conn: Any, hint: dict[str, Any], new_value: str, node: dict[str, Any]
) -> None:
    field = hint.get("field", "")
    field_lower = field.lower()
    raw_shares = node.get("global_shares", "[]")
    shares = (
        json.loads(raw_shares)
        if isinstance(raw_shares, str)
        else (raw_shares or [])
    )
    updated = False

    for share in shares:
        country = share.get("c", "")
        if country and country in field:
            _try_parse_and_set(share, new_value, field)
            updated = True
            break

    if not updated and "替代" in field_lower:
        pass

    if updated:
        conn.execute(
            "UPDATE industry_chain_nodes SET global_shares = ?, "
            "last_updated = datetime('now') WHERE id = ?",
            (json.dumps(shares, ensure_ascii=False), hint["node_id"]),
        )


def _try_parse_and_set(
    share: dict[str, Any], new_value: str, field: str
) -> None:
    numbers = re.findall(r"(\d+(?:\.\d+)?)\s*%?", new_value)
    if not numbers:
        return

    value = float(numbers[0])
    field_lower = field.lower()
    if "出口占全球" in field_lower:
        share["p_export_global"] = value
    elif "出口/产量" in field_lower or "出口占产量" in field_lower:
        share["p_export_ratio"] = value
    elif "出口占本国" in field_lower or "出口占总出口" in field_lower:
        share["p_export_national"] = value
    elif "进口占全球" in field_lower:
        share["d_import_global"] = value
    elif "进口/消费" in field_lower or "进口占消费" in field_lower:
        share["d_import_ratio"] = value
    elif "进口占本国" in field_lower or "进口占总进口" in field_lower:
        share["d_import_national"] = value
    elif "消费" in field_lower:
        share["d"] = value
    else:
        share["p"] = value
