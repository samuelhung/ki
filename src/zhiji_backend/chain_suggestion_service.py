from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

from .chain_node_service import ConnectFn, UUIDFactory

type ChatFn = Callable[..., str | None]
type IconSuggester = Callable[[str], str]

ICON_NAMES = [
    "Zap",
    "Sun",
    "Cpu",
    "Factory",
    "Wheat",
    "Flame",
    "Hammer",
    "Shirt",
    "Truck",
    "Heart",
    "Building",
    "Cloud",
    "DollarSign",
    "Leaf",
    "Anchor",
    "Microscope",
    "Droplets",
    "ShoppingCart",
    "Ship",
    "Plane",
    "Shield",
    "Radio",
    "Globe",
    "Database",
]


def list_suggestions(
    *, status: str, limit: int, connect_fn: ConnectFn
) -> dict[str, list[dict[str, Any]]]:
    with connect_fn() as conn:
        rows = conn.execute(
            """SELECT * FROM chain_suggestions
               WHERE status = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (status, limit),
        ).fetchall()

    suggestions = []
    for row in rows:
        item = dict(row)
        if isinstance(item["nodes_json"], str):
            item["nodes_json"] = json.loads(item["nodes_json"])
        suggestions.append(item)
    return {"suggestions": suggestions}


def count_suggestions(*, connect_fn: ConnectFn) -> dict[str, int]:
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM chain_suggestions "
            "WHERE status = 'pending'"
        ).fetchone()
    return {"pending": row["cnt"] if row else 0}


def adopt_suggestion(
    suggestion_id: str,
    *,
    connect_fn: ConnectFn,
    uuid_factory: UUIDFactory,
    icon_suggester: IconSuggester,
) -> dict[str, Any]:
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT * FROM chain_suggestions WHERE id = ?", (suggestion_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "建议不存在")

        suggestion = dict(row)
        nodes = suggestion["nodes_json"]
        if isinstance(nodes, str):
            nodes = json.loads(nodes)

        created = []
        for index, node in enumerate(nodes):
            node_id = str(uuid_factory())
            upstream = json.dumps([created[-1]["id"]]) if created else None
            conn.execute(
                """INSERT INTO industry_chain_nodes
                   (id, chain, name, node_type, description, sort_order, upstream_ids)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    node_id,
                    suggestion["chain_name"],
                    node.get("name", "?"),
                    node.get("node_type", "原材料"),
                    node.get("description", ""),
                    index,
                    upstream,
                ),
            )
            created.append({"id": node_id, "name": node.get("name", "?")})

        conn.execute(
            "UPDATE chain_suggestions SET status = 'adopted', "
            "reviewed_at = datetime('now') WHERE id = ?",
            (suggestion_id,),
        )

    icon = icon_suggester(suggestion["chain_name"])
    with connect_fn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO chain_meta "
            "(chain_name, icon, created_at) VALUES (?, ?, datetime('now'))",
            (suggestion["chain_name"], icon),
        )

    return {
        "ok": True,
        "chain_name": suggestion["chain_name"],
        "icon": icon,
        "nodes_created": len(created),
        "nodes": created,
    }


def dismiss_suggestion(
    suggestion_id: str, *, connect_fn: ConnectFn
) -> dict[str, bool]:
    with connect_fn() as conn:
        conn.execute(
            "UPDATE chain_suggestions SET status = 'dismissed', "
            "reviewed_at = datetime('now') WHERE id = ?",
            (suggestion_id,),
        )
    return {"ok": True}


def suggest_icon(
    chain_name: str, *, chat_fn: ChatFn, service_logger: logging.Logger
) -> str:
    prompt = f"""从以下 Lucide 图标名中选择最适合「{chain_name}」的一个图标。

可选图标: {', '.join(ICON_NAMES)}

规则:
1. 只返回图标名，不要加引号或其他文字
2. 根据产业链的核心实物/活动来选择（如粮食→Wheat, 石油→Droplets, 钢铁→Hammer, 服装→Shirt, 医药→Heart, 物流→Truck, 航空→Plane, 金融→DollarSign, 农业→Leaf, 建筑→Building, 军工→Shield, 云计算→Cloud, 通信→Radio）
3. 如果都不合适，返回 Factory"""
    try:
        result = chat_fn(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=32,
            module="chain_meta",
            task="suggest_icon",
        )
        if result:
            icon = result.strip().strip('"').strip("'")
            if icon in ICON_NAMES:
                return icon
    except Exception:
        service_logger.warning(
            "_suggest_icon failed for %s", chain_name, exc_info=True
        )
    return "Factory"
