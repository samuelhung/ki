from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from .chain_node_service import ConnectFn

type ChatFn = Callable[..., str | None]


class ChatRequest(Protocol):
    chain_name: str
    message: str
    history: list[dict[str, Any]]


def chain_chat(
    request: ChatRequest, *, connect_fn: ConnectFn, chat_fn: ChatFn
) -> dict[str, str]:
    with connect_fn() as conn:
        conn.row_factory = lambda cursor, row: dict(
            zip([column[0] for column in cursor.description], row)
        )
        nodes = conn.execute(
            """SELECT id, chain, name, node_type, description, global_shares,
                      substitutes, upstream_ids, data_sources
               FROM industry_chain_nodes WHERE chain = ? ORDER BY sort_order""",
            (request.chain_name,),
        ).fetchall()

    if not nodes:
        return {"error": f"未找到产业链: {request.chain_name}"}

    nodes_context = "\n".join(_format_node(node, nodes) for node in nodes)
    system_prompt = f"""你是一位产业链分析专家。以下是「{request.chain_name}」的完整数据，请基于这些数据回答用户问题。

## 产业链数据

{nodes_context}

规则:
1. 优先使用上述数据中的具体数字和信息
2. 数据中没有提到的内容，可以基于你对产业的了解补充，但要明确标注「据一般了解」或「估算」
3. 回答要简洁专业，控制在 300 字以内
4. 如果用户问的问题和数据完全无关，从产业常识角度回答
5. 用中文回答"""

    messages = [{"role": "system", "content": system_prompt}]
    for history_item in request.history[-10:]:
        role = history_item.get("role", "user")
        content = history_item.get("content", "")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": request.message})

    try:
        result = chat_fn(
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
            module="chain_chat",
            task="chat",
        )
        if not result:
            return {"error": "AI 返回空结果"}
        return {"reply": result}
    except Exception as exc:
        return {"error": str(exc)}


def _format_node(node: dict[str, Any], nodes: list[dict[str, Any]]) -> str:
    parts = [f"- [{node['node_type']}] {node['name']}"]
    if node.get("description"):
        parts.append(f"  描述: {node['description']}")

    shares_text = _format_global_shares(node.get("global_shares"))
    if shares_text:
        parts.append(f"  全球份额: {shares_text}")

    substitutes_text = _format_substitutes(node.get("substitutes"))
    if substitutes_text:
        parts.append(f"  替代: {substitutes_text}")

    upstream_text = _format_upstream(node.get("upstream_ids"), nodes)
    if upstream_text:
        parts.append(f"  上游: {upstream_text}")
    return "\n".join(parts)


def _format_global_shares(raw_shares: Any) -> str:
    if not raw_shares or raw_shares == "[]":
        return ""
    try:
        shares = json.loads(raw_shares) if isinstance(raw_shares, str) else raw_shares
        all_items = []
        groups = shares.get("groups") if isinstance(shares, dict) else None
        if groups:
            for group_name in ("production", "supply", "demand"):
                all_items.extend(groups.get(group_name, []))
        elif isinstance(shares, list):
            all_items = shares

        countries = []
        for share in all_items:
            country = share.get("c", "未知")
            values = []
            if share.get("p", 0) > 0:
                values.append(f"产量{share['p']}%")
            if share.get("d", 0) > 0:
                values.append(f"消费{share['d']}%")
            if share.get("p_export_global", 0) > 0:
                values.append(f"出口/全球{share['p_export_global']}%")
            if share.get("d_import_global", 0) > 0:
                values.append(f"进口/全球{share['d_import_global']}%")
            if values:
                countries.append(f"{country}({', '.join(values)})")
        return "; ".join(countries[:5])
    except Exception:
        return ""


def _format_substitutes(raw_substitutes: Any) -> str:
    if not raw_substitutes or raw_substitutes == "[]":
        return ""
    try:
        substitutes = (
            json.loads(raw_substitutes)
            if isinstance(raw_substitutes, str)
            else raw_substitutes
        )
        return ", ".join(item.get("node", "?") for item in substitutes[:3])
    except Exception:
        return ""


def _format_upstream(raw_upstream: Any, nodes: list[dict[str, Any]]) -> str:
    if not raw_upstream or raw_upstream == "[]":
        return ""
    try:
        upstream_ids = (
            json.loads(raw_upstream) if isinstance(raw_upstream, str) else raw_upstream
        )
        names = []
        for upstream_id in upstream_ids:
            for candidate in nodes:
                if candidate["id"] == upstream_id:
                    names.append(candidate["name"])
                    break
        return " → ".join(names)
    except Exception:
        return ""
