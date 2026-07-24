from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from .chain_node_service import ConnectFn

type ChatFn = Callable[..., str | None]


class ChainReportRequest(Protocol):
    chain_name: str
    force: bool
    cache_only: bool


def generate_chain_report(
    request: ChainReportRequest,
    *,
    connect_fn: ConnectFn,
    chat_fn: ChatFn,
) -> dict[str, Any]:
    chain_name = request.chain_name

    if not request.force:
        with connect_fn() as conn:
            conn.row_factory = _dict_factory
            cached = conn.execute(
                "SELECT report, updated_at FROM chain_reports WHERE chain_name = ?",
                (chain_name,),
            ).fetchone()
            if cached and cached.get("report"):
                return {
                    "report": cached["report"],
                    "chain_name": chain_name,
                    "cached": True,
                    "updated_at": cached.get("updated_at", ""),
                }
        if request.cache_only:
            return {
                "report": None,
                "chain_name": chain_name,
                "cached": False,
                "missing": True,
            }

    with connect_fn() as conn:
        conn.row_factory = _dict_factory
        nodes = conn.execute(
            """SELECT id, chain, name, node_type, description, global_shares,
                      substitutes, data_sources
               FROM industry_chain_nodes WHERE chain = ? ORDER BY sort_order""",
            (chain_name,),
        ).fetchall()

    if not nodes:
        return {"error": f"未找到产业链: {chain_name}"}

    nodes_text_parts = []
    for node in nodes:
        parts = [f"### {node['node_type']}：{node['name']}"]
        if node.get("description"):
            parts.append(f"描述：{node['description']}")
        shares = node.get("global_shares")
        if shares:
            try:
                if isinstance(shares, str):
                    shares = json.loads(shares)
                all_shares = []
                groups = shares.get("groups") if isinstance(shares, dict) else None
                if groups:
                    for group_name in ("production", "supply", "demand"):
                        all_shares.extend(groups.get(group_name, []))
                elif isinstance(shares, list):
                    all_shares = shares
                for share in all_shares:
                    country = share.get("c", "未知")
                    metrics = []
                    if share.get("p"):
                        metrics.append(f"全球产量占比 {share['p']}%")
                    if share.get("p_export_global"):
                        metrics.append(f"出口/全球出口 {share['p_export_global']}%")
                    if share.get("p_export_ratio"):
                        metrics.append(f"出口/产量 {share['p_export_ratio']}%")
                    if share.get("d", 0):
                        metrics.append(f"全球消费占比 {share['d']}%")
                    if share.get("d_import_global"):
                        metrics.append(f"进口/全球进口 {share['d_import_global']}%")
                    if share.get("d_import_ratio"):
                        metrics.append(f"进口/消费 {share['d_import_ratio']}%")
                    if metrics:
                        parts.append(f"  {country}: {', '.join(metrics)}")
            except Exception:
                pass
        substitutes = node.get("substitutes")
        if substitutes:
            try:
                if isinstance(substitutes, str):
                    substitutes = json.loads(substitutes)
                for substitute in substitutes:
                    parts.append(
                        f"  替代方案：{substitute.get('node', '')} "
                        f"(成熟度:{substitute.get('maturity', '')})"
                    )
            except Exception:
                pass
        nodes_text_parts.append("\n".join(parts))

    nodes_text = "\n\n".join(nodes_text_parts)
    prompt = f"""你是一位产业战略分析师。请基于以下产业链数据，生成一份专业的产业链概览分析报告。

## 产业链：{chain_name}

{nodes_text}

请按以下结构生成报告（使用 Markdown 格式，数据引用用【来源:节点名】标注）：

## 一、产业链结构概览
- **流转概述**：用简洁箭头描述从原材料到终端的价值流转路径（如 硅料 → 硅片 → 电池片 → 组件 → 电站），标注每个环节的节点类型，让读者一眼看懂"先生产什么、再生产什么、最终产出什么"
- 节点数量与类型分布（原材料×N、中间品×N、零部件×N、终端×N）
- 关键节点识别（哪些节点具有战略重要性）
- 产业链完整度评估

## 二、全球竞争格局
- 基于各国全球份额数据，分析主要竞争方
- 各节点的产能集中度与地缘风险
- 中国在各节点的位置（优势环节 / 薄弱环节）

## 三、供应链安全评估
- 对外依赖度高的节点及进口来源
- 潜在的"卡脖子"风险点
- 替代方案的可行性与成熟度

## 四、关键风险与机遇
- 短期（1年内）和中长期（3-5年）风险
- 技术突破或地缘变化可能带来的结构性机会

## 五、投资与战略建议
- 值得关注的环节与方向
- 建议的布局策略

请用简洁专业的语言，避免空泛表述，尽量量化。总字数控制在 1500-2000 字。"""

    try:
        result = chat_fn(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
            module="chain_analysis",
            task="report",
        )
        if not result:
            return {"error": "AI 分析返回空结果"}

        with connect_fn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO chain_reports
                   (chain_name, report, updated_at)
                   VALUES (?, ?, datetime('now'))""",
                (chain_name, result),
            )

        return {
            "report": result,
            "chain_name": chain_name,
            "node_count": len(nodes),
            "cached": False,
        }
    except Exception as exc:
        return {"error": str(exc)}


def _dict_factory(cursor: Any, row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip([column[0] for column in cursor.description], row))
