from __future__ import annotations

import json
from typing import Any, Protocol

from .chain_node_service import ConnectFn, UUIDFactory


class SyncHintsRequest(Protocol):
    hints: list[dict[str, Any]]


def sync_extracted_hints(
    request: SyncHintsRequest,
    *,
    connect_fn: ConnectFn,
    uuid_factory: UUIDFactory,
) -> dict[str, bool | int]:
    saved = 0
    new_suggestions = 0

    with connect_fn() as conn:
        nodes = conn.execute(
            "SELECT id, name, chain FROM industry_chain_nodes"
        ).fetchall()
        name_map = {node["name"]: (node["id"], node["chain"]) for node in nodes}

        for hint in request.hints:
            node_name = hint.get("node_name", "").strip()
            if node_name in name_map:
                node_id, chain = name_map[node_name]
                hint_id = f"chint-{uuid_factory().hex[:12]}"
                conn.execute(
                    """INSERT INTO chain_data_hints
                       (id, event_id, node_id, chain, field, current_value,
                        suggested_value, source_quote, confidence)
                       VALUES (?, '', ?, ?, ?, '', ?, ?, 0.7)""",
                    (
                        hint_id,
                        node_id,
                        chain,
                        hint.get("field", ""),
                        hint.get("value", ""),
                        hint.get("source_quote", ""),
                    ),
                )
                saved += 1
            elif node_name == "建议新建":
                suggestion_id = f"csug-{uuid_factory().hex[:12]}"
                node_data = [
                    {
                        "name": hint.get("field", "未知节点"),
                        "node_type": "原材料",
                        "description": hint.get("value", ""),
                        "initial_data": hint.get("source_quote", ""),
                    }
                ]
                conn.execute(
                    """INSERT INTO chain_suggestions
                       (id, chain_name, event_id, nodes_json, reason,
                        source_quote, confidence)
                       VALUES (?, ?, '', ?, ?, ?, 0.6)""",
                    (
                        suggestion_id,
                        f"建议: {node_name}",
                        json.dumps(node_data, ensure_ascii=False),
                        f"从分析中提取: {hint.get('value', '')}",
                        hint.get("source_quote", ""),
                    ),
                )
                new_suggestions += 1

    return {
        "ok": True,
        "saved_hints": saved,
        "new_suggestions": new_suggestions,
    }
