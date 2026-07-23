from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, Protocol
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel

type ConnectionContext = AbstractContextManager[sqlite3.Connection]
type ConnectFn = Callable[[], ConnectionContext]
type UUIDFactory = Callable[[], UUID]
type JSONList = list[Any]
type JSONDict = dict[Any, Any]
type JSONCollection = JSONList | JSONDict | BaseModel


class FlowSummaryRequest(Protocol):
    chain_name: str
    flow_summary: str


class NodeUpdateRequest(Protocol):
    name: str | None
    node_type: str | None
    description: str | None
    global_shares: JSONCollection | None
    substitutes: JSONList | None
    upstream_names: list[str] | None
    data_sources: JSONDict | None
    sort_order: int | None


class NodeCreateRequest(Protocol):
    chain: str
    name: str
    node_type: str
    description: str
    global_shares: JSONList
    substitutes: JSONList
    upstream_names: list[str]
    data_sources: JSONDict


def list_chains(*, connect_fn: ConnectFn) -> dict[str, Any]:
    with connect_fn() as conn:
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        rows = conn.execute("""
            SELECT chain, COUNT(*) as node_count
            FROM industry_chain_nodes
            GROUP BY chain
            ORDER BY chain
        """).fetchall()
        meta_rows = conn.execute(
            "SELECT chain_name, icon, flow_summary FROM chain_meta"
        ).fetchall()
        icon_map = {r["chain_name"]: r["icon"] for r in meta_rows}
        summary_map = {r["chain_name"]: r["flow_summary"] for r in meta_rows}
        for row in rows:
            row["icon"] = icon_map.get(row["chain"], "")
            row["flow_summary"] = summary_map.get(row["chain"], "")
        return {"chains": rows}


def list_chain_meta(*, connect_fn: ConnectFn) -> dict[str, Any]:
    with connect_fn() as conn:
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        rows = conn.execute("SELECT * FROM chain_meta ORDER BY chain_name").fetchall()
        return {"meta": rows}


def save_flow_summary(
    body: FlowSummaryRequest, *, connect_fn: ConnectFn
) -> dict[str, bool]:
    with connect_fn() as conn:
        conn.execute(
            "INSERT INTO chain_meta (chain_name, flow_summary, icon, created_at) "
            "VALUES (?, ?, '', datetime('now')) "
            "ON CONFLICT(chain_name) DO UPDATE SET flow_summary = excluded.flow_summary",
            (body.chain_name, body.flow_summary),
        )
    return {"ok": True}


def list_nodes(*, connect_fn: ConnectFn) -> dict[str, Any]:
    with connect_fn() as conn:
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        rows = conn.execute("""
            SELECT * FROM industry_chain_nodes
            ORDER BY chain, sort_order
        """).fetchall()
        for row in rows:
            row["global_shares"] = json.loads(row["global_shares"])
            row["substitutes"] = json.loads(row["substitutes"])
            row["upstream_ids"] = json.loads(row["upstream_ids"])
            row["data_sources"] = (
                json.loads(row["data_sources"]) if row.get("data_sources") else {}
            )
        return {"nodes": rows}


def resolve_upstream_ids(
    conn: sqlite3.Connection, upstream_names: list[str]
) -> list[str]:
    if not upstream_names:
        return []
    placeholders = ",".join("?" for _ in upstream_names)
    rows = conn.execute(
        f"SELECT id, name FROM industry_chain_nodes WHERE name IN ({placeholders})",
        upstream_names,
    ).fetchall()
    name_map = {row[1]: row[0] for row in rows}
    return [name_map[name] for name in upstream_names if name in name_map]


def update_node(
    node_id: str, req: NodeUpdateRequest, *, connect_fn: ConnectFn
) -> dict[str, Any]:
    with connect_fn() as conn:
        existing = conn.execute(
            "SELECT id FROM industry_chain_nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="节点不存在")

        updates = {}
        if req.name is not None:
            updates["name"] = req.name
        if req.node_type is not None:
            updates["node_type"] = req.node_type
        if req.description is not None:
            updates["description"] = req.description
        if req.global_shares is not None:
            global_shares = (
                req.global_shares.model_dump()
                if isinstance(req.global_shares, BaseModel)
                else req.global_shares
            )
            updates["global_shares"] = json.dumps(global_shares, ensure_ascii=False)
        if req.substitutes is not None:
            updates["substitutes"] = json.dumps(req.substitutes, ensure_ascii=False)
        if req.data_sources is not None:
            updates["data_sources"] = json.dumps(req.data_sources, ensure_ascii=False)
        if req.sort_order is not None:
            updates["sort_order"] = req.sort_order
        if req.upstream_names is not None:
            updates["upstream_ids"] = json.dumps(
                resolve_upstream_ids(conn, req.upstream_names), ensure_ascii=False
            )

        if not updates:
            return {"ok": True, "message": "无变更"}

        set_clause = ", ".join(f"{key} = ?" for key in updates)
        set_clause = f"{set_clause}, last_updated = datetime('now')"
        values = list(updates.values())
        values.append(node_id)
        conn.execute(
            f"UPDATE industry_chain_nodes SET {set_clause} WHERE id = ?", values
        )
        conn.commit()
        return {"ok": True}


def create_node(
    req: NodeCreateRequest, *, connect_fn: ConnectFn, uuid_factory: UUIDFactory
) -> dict[str, Any]:
    node_id = str(uuid_factory())
    with connect_fn() as conn:
        upstream_ids = resolve_upstream_ids(conn, req.upstream_names)
        if not upstream_ids:
            last = conn.execute(
                "SELECT id FROM industry_chain_nodes WHERE chain = ? "
                "ORDER BY sort_order DESC LIMIT 1",
                (req.chain,),
            ).fetchone()
            if last:
                upstream_ids = [last[0]]
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM industry_chain_nodes WHERE chain = ?",
            (req.chain,),
        ).fetchone()[0]

        conn.execute(
            """
            INSERT INTO industry_chain_nodes (id, chain, name, node_type, description,
                global_shares, substitutes, upstream_ids, data_sources, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                req.chain,
                req.name,
                req.node_type,
                req.description,
                json.dumps(req.global_shares, ensure_ascii=False),
                json.dumps(req.substitutes, ensure_ascii=False),
                json.dumps(upstream_ids, ensure_ascii=False),
                json.dumps(req.data_sources, ensure_ascii=False),
                max_order + 1,
            ),
        )
        conn.commit()
        return {"ok": True, "id": node_id}


def delete_node(node_id: str, *, connect_fn: ConnectFn) -> dict[str, bool]:
    with connect_fn() as conn:
        conn.execute("DELETE FROM industry_chain_nodes WHERE id = ?", (node_id,))
        conn.commit()
        return {"ok": True}
