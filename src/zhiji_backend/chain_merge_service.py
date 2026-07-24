from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Protocol

from fastapi import HTTPException

from .chain_node_service import ConnectFn

type ChatFn = Callable[..., str | None]
type IconSuggester = Callable[[str], str]


class MergeRequestLike(Protocol):
    chain_a: str
    chain_b: str
    into: str


def check_chain_overlaps(*, connect_fn: ConnectFn) -> dict[str, Any]:
    """Detect shared nodes and upstream/downstream links between chains."""
    with connect_fn() as conn:
        rows = conn.execute(
            "SELECT id, chain, name, node_type, sort_order "
            "FROM industry_chain_nodes ORDER BY chain, sort_order"
        ).fetchall()

    chains: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        chains[item["chain"]].append(item)

    chain_names = sorted(chains.keys())
    overlaps: list[dict[str, Any]] = []

    name_to_chains: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        item = dict(row)
        name_to_chains[item["name"]].add(item["chain"])
    exact_shared = {
        name: chain_set
        for name, chain_set in name_to_chains.items()
        if len(chain_set) > 1
    }

    def strip_chain(name: str) -> str:
        return name.replace("产业链", "")

    for index, chain_a in enumerate(chain_names):
        for chain_b in chain_names[index + 1 :]:
            nodes_a = chains[chain_a]
            nodes_b = chains[chain_b]
            types_a = {node["node_type"] for node in nodes_a}
            types_b = {node["node_type"] for node in nodes_b}
            fuzzy_shared: list[str] = []

            a_stripped = strip_chain(chain_a)
            b_stripped = strip_chain(chain_b)
            for node in nodes_b:
                if a_stripped in node["name"] or node["name"] in a_stripped:
                    fuzzy_shared.append(
                        f"「{chain_a}」链名 ↔ 节点「{node['name']}」({chain_b})"
                    )
            for node in nodes_a:
                if b_stripped in node["name"] or node["name"] in b_stripped:
                    fuzzy_shared.append(
                        f"「{chain_b}」链名 ↔ 节点「{node['name']}」({chain_a})"
                    )

            a_terminals = [node for node in nodes_a if node["node_type"] == "终端"]
            b_materials = [
                node for node in nodes_b if node["node_type"] == "原材料"
            ]
            b_terminals = [node for node in nodes_b if node["node_type"] == "终端"]
            a_materials = [
                node for node in nodes_a if node["node_type"] == "原材料"
            ]

            for terminal in a_terminals:
                for material in b_materials:
                    if (
                        terminal["name"] in material["name"]
                        or material["name"] in terminal["name"]
                    ):
                        fuzzy_shared.append(
                            f"终端「{terminal['name']}」({chain_a}) ↔ "
                            f"原材料「{material['name']}」({chain_b})"
                        )

            for terminal in b_terminals:
                for material in a_materials:
                    if (
                        terminal["name"] in material["name"]
                        or material["name"] in terminal["name"]
                    ):
                        fuzzy_shared.append(
                            f"终端「{terminal['name']}」({chain_b}) ↔ "
                            f"原材料「{material['name']}」({chain_a})"
                        )

            exact = [
                name
                for name, chain_set in exact_shared.items()
                if chain_a in chain_set and chain_b in chain_set
            ]
            if not exact and not fuzzy_shared:
                continue

            reason_parts: list[str] = []
            score = 0.0
            if exact:
                score += len(exact) / max(len(nodes_a) + len(nodes_b), 1) * 0.8
                reason_parts.append(f"同名节点: {', '.join(exact)}")
            if fuzzy_shared:
                score += min(len(fuzzy_shared) * 0.15, 0.4)
                reason_parts.append(f"关键词重叠: {'; '.join(fuzzy_shared)}")
            if "终端" in types_a and "原材料" in types_b:
                score += 0.1
                reason_parts.append(
                    f"「{chain_a}」终端 ←→ 「{chain_b}」原材料, 可合并为上下游"
                )
            if "终端" in types_b and "原材料" in types_a:
                score += 0.1
                reason_parts.append(
                    f"「{chain_b}」终端 ←→ 「{chain_a}」原材料, 可合并为上下游"
                )

            overlaps.append(
                {
                    "chain_a": chain_a,
                    "chain_b": chain_b,
                    "nodes_a_count": len(nodes_a),
                    "nodes_b_count": len(nodes_b),
                    "exact_shared": exact,
                    "fuzzy_shared": fuzzy_shared,
                    "overlap_score": round(min(score, 1.0), 3),
                    "reason": "；".join(reason_parts),
                }
            )

    overlaps.sort(key=lambda item: -item["overlap_score"])
    return {"overlaps": overlaps, "total_chains": len(chain_names)}


def merge_chains(
    request: MergeRequestLike,
    *,
    connect_fn: ConnectFn,
    chat_fn: ChatFn,
    icon_suggester: IconSuggester,
    service_logger: logging.Logger,
) -> dict[str, Any]:
    """Merge two chains while preserving the existing API and database behavior."""
    into_a = request.into == "a"
    into_b = request.into == "b"
    into_new = request.into.startswith("new:")
    target_chain = ""
    removed_chain = ""

    if into_a:
        target_chain = request.chain_a
        removed_chain = request.chain_b
    elif into_b:
        target_chain = request.chain_b
        removed_chain = request.chain_a
    elif into_new:
        target_chain = request.into[4:]
    else:
        raise HTTPException(400, "into must be 'a', 'b', or 'new:name'")

    if into_new and target_chain in (request.chain_a, request.chain_b):
        raise HTTPException(400, "新链名不能与现有链名相同")

    with connect_fn() as conn:
        nodes_a = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM industry_chain_nodes "
                "WHERE chain = ? ORDER BY sort_order",
                (request.chain_a,),
            ).fetchall()
        ]
        nodes_b = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM industry_chain_nodes "
                "WHERE chain = ? ORDER BY sort_order",
                (request.chain_b,),
            ).fetchall()
        ]

        if into_a:
            merged_nodes = nodes_a
            existing_names = {node["name"] for node in nodes_a}
            candidates = nodes_b
        elif into_b:
            merged_nodes = nodes_b
            existing_names = {node["name"] for node in nodes_b}
            candidates = nodes_a
        else:
            merged_nodes = list(nodes_a)
            existing_names = {node["name"] for node in nodes_a}
            candidates = nodes_b

        for node in candidates:
            if node["name"] not in existing_names:
                merged_nodes.append(node)
                existing_names.add(node["name"])

        try:
            node_list = "\n".join(
                f"- [{node['node_type']}] {node['name']}"
                + (
                    f" — {node.get('description', '')[:60]}"
                    if node.get("description")
                    else ""
                )
                for node in merged_nodes
            )
            prompt = f"""你是一位产业链分析师。以下节点来自两条合并的产业链：
原链A「{request.chain_a}」和原链B「{request.chain_b}」已合并为「{target_chain}」。

请根据产业链的真实生产流转逻辑，将这些节点重新排序。规则：
1. 原材料在上游，中间品/零部件在中间，终端/应用在下游
2. 同一物质如果同时出现在两条链中（如A的产物是B的原料），按上下游串联
3. 并列的原材料放在一起，并列的终端放在一起
4. 返回纯 JSON 数组，只包含节点名，不要任何其他内容

节点列表：
{node_list}

格式示例：["硫磺","合成氨","尿素","化肥","柴油","粮食种植","粮食作物","食品价格"]"""

            ai_raw = chat_fn(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1024,
                timeout=30,
                response_format={"type": "json_object"},
            )
            if ai_raw:
                array_match = re.search(r"\[.*?\]", ai_raw.strip(), re.DOTALL)
                if array_match:
                    ai_order = json.loads(array_match.group())
                    if isinstance(ai_order, dict):
                        for value in ai_order.values():
                            if isinstance(value, list) and value:
                                ai_order = value
                                break
                    if isinstance(ai_order, list):
                        name_map = {node["name"]: node for node in merged_nodes}
                        ai_sorted = [
                            name_map[name] for name in ai_order if name in name_map
                        ]
                        covered = {node["name"] for node in ai_sorted}
                        for node in merged_nodes:
                            if node["name"] not in covered:
                                ai_sorted.append(node)
                                covered.add(node["name"])
                        merged_nodes = ai_sorted
                        service_logger.info(
                            "AI sorted %d nodes for merged chain '%s'",
                            len(ai_sorted),
                            target_chain,
                        )
        except Exception as exc:
            service_logger.warning(
                "AI merge sort failed, falling back to type-based sort: %s", exc
            )
            type_order = {"原材料": 0, "中间品": 1, "零部件": 2, "终端": 3}
            primary_chain = (
                request.chain_a
                if into_a
                else request.chain_b
                if into_b
                else request.chain_a
            )
            merged_nodes.sort(
                key=lambda node: (
                    type_order.get(node["node_type"], 99),
                    0 if node["chain"] == primary_chain else 1,
                    node["sort_order"],
                )
            )

        for index, node in enumerate(merged_nodes):
            conn.execute(
                "UPDATE industry_chain_nodes SET chain = ?, sort_order = ? "
                "WHERE id = ?",
                (target_chain, index, node["id"]),
            )

        if into_a:
            conn.execute(
                "DELETE FROM chain_meta WHERE chain_name = ?", (request.chain_b,)
            )
        elif into_b:
            conn.execute(
                "DELETE FROM chain_meta WHERE chain_name = ?", (request.chain_a,)
            )
        else:
            conn.execute(
                "DELETE FROM chain_meta WHERE chain_name = ?", (request.chain_a,)
            )
            conn.execute(
                "DELETE FROM chain_meta WHERE chain_name = ?", (request.chain_b,)
            )

        existing_meta = conn.execute(
            "SELECT icon FROM chain_meta WHERE chain_name = ?", (target_chain,)
        ).fetchone()
        if not existing_meta:
            conn.execute(
                "INSERT OR IGNORE INTO chain_meta (chain_name, icon) VALUES (?, ?)",
                (target_chain, icon_suggester(target_chain)),
            )

        if removed_chain:
            conn.execute(
                "UPDATE chain_data_hints SET chain = ? WHERE chain = ?",
                (target_chain, removed_chain),
            )
        else:
            conn.execute(
                "UPDATE chain_data_hints SET chain = ? WHERE chain = ?",
                (target_chain, request.chain_a),
            )
            conn.execute(
                "UPDATE chain_data_hints SET chain = ? WHERE chain = ?",
                (target_chain, request.chain_b),
            )

        conn.commit()

    return {
        "ok": True,
        "target_chain": target_chain,
        "removed": removed_chain or [request.chain_a, request.chain_b],
        "node_count": len(merged_nodes),
        "flow": [
            {"name": node["name"], "type": node["node_type"], "sort_order": index}
            for index, node in enumerate(merged_nodes)
        ],
    }
