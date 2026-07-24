from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any, Protocol

from .chain_node_service import ConnectFn

type ChatFn = Callable[..., str | None]
type DetectNewChainsFn = Callable[[str], Any]


class AnalyzeRequest(Protocol):
    event_id: str
    event_title: str
    event_summary: str


def analyze_chain_impact(
    request: AnalyzeRequest,
    *,
    connect_fn: ConnectFn,
    chat_fn: ChatFn,
    detect_new_chains_fn: DetectNewChainsFn,
    service_logger: logging.Logger,
) -> dict[str, Any]:
    event_id = request.event_id
    event_title = request.event_title
    event_summary = request.event_summary
    if event_id:
        with connect_fn() as conn:
            conn.row_factory = _dict_factory
            event = conn.execute(
                "SELECT title, ai_summary, raw_summary FROM events WHERE id = ?",
                (event_id,),
            ).fetchone()
            if not event:
                return {"error": "事件不存在"}
            event_title = event.get("title", "") or ""
            event_summary = (
                event.get("ai_summary", "") or event.get("raw_summary", "") or ""
            )

    if not event_summary:
        return {"error": "没有事件内容可分析"}

    with connect_fn() as conn:
        conn.row_factory = _dict_factory
        nodes = conn.execute(
            """SELECT id, chain, name, node_type, description, global_shares,
                      substitutes
               FROM industry_chain_nodes ORDER BY chain, sort_order"""
        ).fetchall()

    chain_context = build_chain_context(nodes)
    prompt = f"""你是一位产业分析专家。以下是已知的产业链知识库和一条新闻事件。

{chain_context}

---
## 事件
标题：{event_title}
内容：{event_summary[:4000]}
---

请分析该事件对产业链的影响，按以下结构生成报告：

## 一、直接冲击
- 受直接影响的产业链节点及程度（严重/中等/轻微）
- 基于全球份额数据量化影响

## 二、上下游传导
- 按产业链逐级推演传导路径
- 标注每个环节受影响的方向（↑成本上升/↓需求下降）和时滞（即时/短期/中期）

## 三、价格趋势预判
- 涉及的关键原材料、中间品、终端产品价格走势
- 涨幅/跌幅区间估计

## 四、替代效应
- 哪些替代材料/替代技术可能受益
- 替代可行性和时点判断

## 五、资本市场映射
- 受影响的A股/港股板块和代表性公司
- 受益方和受损方分别列出

请用简洁专业的中文，数据引用标注来源。（如全球份额数据、替代材料可行性等）"""

    try:
        result = chat_fn(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
            module="chain_analysis",
            task="analyze",
        )
        if not result:
            return {"error": "AI 分析返回空结果"}

        extracted_hints = extract_hints_from_analysis(
            result,
            event_title,
            event_summary[:3000],
            chat_fn=chat_fn,
        )

        if event_id:
            with connect_fn() as conn:
                conn.execute(
                    "UPDATE events SET chain_analysis = ? WHERE id = ?",
                    (result, event_id),
                )

        try:
            detect_new_chains_fn(event_id)
        except Exception:
            service_logger.warning(
                "detect_new_chains failed for %s during analyze",
                event_id,
                exc_info=True,
            )

        return {
            "analysis": result,
            "matched_nodes": len(nodes),
            "extracted_hints": extracted_hints,
        }
    except Exception as exc:
        return {"error": str(exc)}


def extract_hints_from_analysis(
    analysis: str, title: str, summary: str, *, chat_fn: ChatFn
) -> list[Any]:
    try:
        prompt = f"""从以下产业分析报告中提取**可量化的数据点**，格式为 JSON 数组。

分析报告:
{analysis[:3000]}

事件标题: {title}

提取规则:
1. 只提取包含具体数字的数据点（百分比、价格区间、排名等）
2. 每个数据点要注明对应的产业链节点名（尽量匹配已有的节点名）
3. 如果无法确定节点名，用 "建议新建" 作为 node_name

输出 JSON 数组，每个元素:
{{
  "node_name": "节点名（如 锂矿、原油、小麦）",
  "field": "字段描述（如 全球产量占比、价格涨幅）",
  "value": "数据值（如 中国占比65%）",
  "source_quote": "报告中支撑该数据的原文引用"
}}

如果没有可提取的量化数据，返回空数组: []
只输出 JSON。"""
        result = chat_fn(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
            module="chain_analysis",
            task="extract_hints",
        )
        if not result:
            return []

        json_text = result.strip()
        if "```json" in json_text:
            json_text = json_text.split("```json")[1].split("```")[0].strip()
        elif "```" in json_text:
            json_text = json_text.split("```")[1].split("```")[0].strip()

        hints = json.loads(json_text)
        return hints if isinstance(hints, list) else []
    except Exception:
        return []


def build_chain_context(nodes: list[dict[str, Any]]) -> str:
    chains: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        chain_name = node["chain"]
        if chain_name not in chains:
            chains[chain_name] = []
        chains[chain_name].append(node)

    parts = []
    for chain_name, chain_nodes in chains.items():
        parts.append(f"### {chain_name}")
        for node in chain_nodes:
            shares_text = _format_shares(node["global_shares"])
            substitutes_text = _format_substitutes(node["substitutes"])
            description = node.get("description", "") or ""
            parts.append(f"- [{node['node_type']}] {node['name']}: {description}")
            if shares_text:
                parts.append(f"  全球份额: {shares_text}")
            if substitutes_text:
                parts.append(f"  {substitutes_text}")
        parts.append("")
    return "\n".join(parts)


def _format_shares(raw_shares: Any) -> str:
    shares_text = ""
    if raw_shares:
        try:
            shares = (
                json.loads(raw_shares) if isinstance(raw_shares, str) else raw_shares
            )
            all_shares = []
            groups = shares.get("groups") if isinstance(shares, dict) else None
            if groups:
                for group_name in ("production", "supply", "demand"):
                    all_shares.extend(groups.get(group_name, []))
            elif isinstance(shares, list):
                all_shares = shares

            items = []
            for share in all_shares:
                values = [share["c"]]
                if share.get("p", 0) > 0:
                    values.append(f"产量占全球{share['p']}%")
                    if share.get("p_export_global", 0) > 0:
                        values.append(f"出口占全球{share['p_export_global']}%")
                    if share.get("p_export_ratio", 0) > 0:
                        values.append(f"出口/产量比{share['p_export_ratio']}%")
                    if share.get("p_export_national", 0) > 0:
                        values.append(f"占本国总出口{share['p_export_national']}%")
                if share.get("d", 0) > 0:
                    values.append(f"消费占全球{share['d']}%")
                    if share.get("d_import_global", 0) > 0:
                        values.append(f"进口占全球{share['d_import_global']}%")
                    if share.get("d_import_ratio", 0) > 0:
                        values.append(f"进口/消费比{share['d_import_ratio']}%")
                    if share.get("d_import_national", 0) > 0:
                        values.append(f"占本国总进口{share['d_import_national']}%")
                items.append(" | ".join(values))
            shares_text = "  ".join(items)
        except (json.JSONDecodeError, TypeError):
            pass
    return shares_text


def _format_substitutes(raw_substitutes: Any) -> str:
    substitutes_text = ""
    if raw_substitutes:
        try:
            substitutes = (
                json.loads(raw_substitutes)
                if isinstance(raw_substitutes, str)
                else raw_substitutes
            )
            items = []
            for substitute in substitutes:
                items.append(
                    f"{substitute['node']}({substitute['maturity']}, "
                    f"触发:{substitute['trigger']})"
                )
            substitutes_text = "替代品: " + "; ".join(items)
        except (json.JSONDecodeError, TypeError):
            pass
    return substitutes_text


def _dict_factory(cursor: Any, row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip([column[0] for column in cursor.description], row))
