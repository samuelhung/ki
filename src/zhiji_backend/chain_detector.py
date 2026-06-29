"""产业链数据检测器 — 采集内容处理完成后，AI 扫描是否含产业链节点数据更新。"""

from __future__ import annotations

import json
import logging
import uuid

from .db import connect
from .ai_client import chat

logger = logging.getLogger(__name__)

# 每次检测最多发送给 AI 的节点数（token 控制）
_MAX_NODES_PER_BATCH = 10

# 每次检测发送给 AI 的摘要 + 转写内容长度上限
_MAX_CONTENT_LENGTH = 4000


def detect_chain_data_hints(event_id: str) -> int:
    """检测采集事件是否包含产业链节点数据更新，写入 chain_data_hints 表。返回创建的 hint 数量。"""
    try:
        # 1) 获取事件内容 + 全部节点
        with connect() as conn:
            event_row = conn.execute(
                "SELECT title, ai_summary, raw_summary FROM events WHERE id = ?",
                (event_id,),
            ).fetchone()
            if not event_row:
                return 0

            title = event_row["title"] or ""
            ai_summary = event_row["ai_summary"] or ""
            raw_summary = event_row["raw_summary"] or ""

            nodes = conn.execute(
                "SELECT id, chain, name, node_type, description, global_shares, substitutes, data_sources "
                "FROM industry_chain_nodes ORDER BY chain, sort_order"
            ).fetchall()

        if not nodes:
            return 0

        content = f"标题: {title}\n\n摘要:\n{ai_summary[:_MAX_CONTENT_LENGTH]}"
        if raw_summary:
            content += f"\n\n转写原文:\n{raw_summary[:_MAX_CONTENT_LENGTH]}"

        if len(content.strip()) < 50:
            return 0

        # 2) 分批检测 (每批最多10个节点,减少token)
        nodes_list = [dict(n) for n in nodes]
        total_hints = 0

        for i in range(0, len(nodes_list), _MAX_NODES_PER_BATCH):
            batch = nodes_list[i : i + _MAX_NODES_PER_BATCH]
            hints = _detect_batch(event_id, content, batch)
            if hints:
                total_hints += _save_hints(event_id, hints, batch)

        return total_hints

    except Exception:
        logger.exception("chain_detector failed for event %s", event_id)
        return 0


def _build_nodes_context(nodes: list[dict]) -> str:
    """构建紧凑的节点数据上下文，供 AI 对比。"""
    lines = []
    for n in nodes:
        parts = [f"节点ID: {n['id']}"]
        parts.append(f"产业链: {n['chain']}")
        parts.append(f"名称: {n['name']} ({n['node_type']})")
        if n.get("description"):
            parts.append(f"描述: {n['description'][:100]}")

        try:
            shares = json.loads(n.get("global_shares", "[]")) if isinstance(n.get("global_shares"), str) else n.get("global_shares", [])
            if shares:
                share_lines = []
                for s in shares:
                    vals = []
                    if s.get("p", 0) > 0:
                        vals.append(f"产量{s['p']}%")
                    if s.get("p_export_global", 0) > 0:
                        vals.append(f"出口全球{s['p_export_global']}%")
                    if s.get("p_export_ratio", 0) > 0:
                        vals.append(f"出口/产量{s['p_export_ratio']}%")
                    if s.get("p_export_national", 0) > 0:
                        vals.append(f"出口/本国{s['p_export_national']}%")
                    if s.get("d", 0) > 0:
                        vals.append(f"消费{s['d']}%")
                    if s.get("d_import_global", 0) > 0:
                        vals.append(f"进口全球{s['d_import_global']}%")
                    if s.get("d_import_ratio", 0) > 0:
                        vals.append(f"进口/消费{s['d_import_ratio']}%")
                    if s.get("d_import_national", 0) > 0:
                        vals.append(f"进口/本国{s['d_import_national']}%")
                    share_lines.append(f"  {s['c']}: {', '.join(vals)}")
                parts.append("当前数据:\n" + "\n".join(share_lines))
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            subs = json.loads(n.get("substitutes", "[]")) if isinstance(n.get("substitutes"), str) else n.get("substitutes", [])
            if subs:
                sub_lines = [f"  {s.get('node','?')} (成熟度:{s.get('maturity','?')})" for s in subs[:3]]
                parts.append("替代方案:\n" + "\n".join(sub_lines))
        except (json.JSONDecodeError, TypeError):
            pass

        lines.append("\n".join(parts))
        lines.append("---")

    return "\n".join(lines)


def _detect_batch(event_id: str, content: str, nodes: list[dict]) -> list[dict] | None:
    """调用 DeepSeek 检测一批节点中有无数据更新。"""
    nodes_ctx = _build_nodes_context(nodes)

    prompt = f"""你是产业链数据分析助手。请判断以下内容是否包含对上述产业链节点**具体数据的更新**。

内容来源:
{content}

当前已记录的产业链节点数据:
{nodes_ctx}

请严格按以下标准判断:
1. 只有当内容中包含了**可直接引用的具体数字**（如"中国生产占比85%""全球出货量增长到120GW"）时，才认为有更新
2. 泛泛的"增长""下降""趋势向好"不算有效更新
3. 每个 hint 必须包含可验证的原文引用（source_quote）
4. field 用中文描述，如 "产量份额" "出口数据" "消费数据" "替代方案" 等

输出 JSON 数组，每个元素:
{{
  "node_id": "节点ID",
  "field": "字段名(如 中国产量份额 / 全球出口占比 / 替代方案)",
  "suggested_value": "建议的新值(简洁描述, 如: 中国产量占比82%)",
  "source_quote": "原文中支持这个更新的引用(短句)",
  "confidence": 0.0-1.0
}}

如果没有发现任何有效更新，返回空数组: []
只输出 JSON，不要任何解释。"""

    try:
        result = chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2048,
            module="chain_detector",
            task="detect_hints",
        )
        if not result:
            return None

        result = result.strip()
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()

        hints = json.loads(result)
        if not isinstance(hints, list):
            return None
        return hints

    except (json.JSONDecodeError, Exception) as e:
        logger.warning("chain_detector AI parse error for %s: %s", event_id, e)
        return None


def _save_hints(event_id: str, hints: list[dict], nodes: list[dict]) -> int:
    """保存 hints 到数据库，去重（过滤与当前值相同的建议）。"""
    nodes_by_id = {n["id"]: n for n in nodes}
    saved = 0

    with connect() as conn:
        for h in hints:
            node_id = h.get("node_id", "")
            if node_id not in nodes_by_id:
                continue

            node = nodes_by_id[node_id]
            field = h.get("field", "")

            current_value = _get_current_value(node, field)
            suggested_value = h.get("suggested_value", "")

            # 跳过与当前值相同的建议
            if current_value and suggested_value and current_value.strip() == suggested_value.strip():
                continue

            hint_id = f"chint-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """INSERT INTO chain_data_hints (id, event_id, node_id, chain, field, current_value, suggested_value, source_quote, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    hint_id, event_id, node_id,
                    node.get("chain", ""), field,
                    (current_value or "")[:500],
                    suggested_value[:500],
                    (h.get("source_quote", ""))[:500],
                    min(max(h.get("confidence", 0.5), 0), 1),
                ),
            )
            saved += 1

    if saved:
        logger.info("chain_detector: saved %d hints for event %s", saved, event_id)
    return saved


def _get_current_value(node: dict, field: str) -> str:
    """从节点数据中提取当前值（供对比）。"""
    field_lower = field.lower()

    try:
        shares = json.loads(node.get("global_shares", "[]")) if isinstance(node.get("global_shares"), str) else node.get("global_shares", [])
        for s in shares:
            country = s.get("c", "")
            if country and country in field:
                metrics = {
                    "产量": ("p", f"产量占全球{s['p']}%"),
                    "出口占全球": ("p_export_global", f"出口占全球出口{s.get('p_export_global',0)}%"),
                    "出口/产量": ("p_export_ratio", f"出口占产量{s.get('p_export_ratio',0)}%"),
                    "出口占本国": ("p_export_national", f"出口占本国总出口{s.get('p_export_national',0)}%"),
                    "消费": ("d", f"消费占全球{s['d']}%"),
                    "进口占全球": ("d_import_global", f"进口占全球进口{s.get('d_import_global',0)}%"),
                    "进口/消费": ("d_import_ratio", f"进口占消费{s.get('d_import_ratio',0)}%"),
                    "进口占本国": ("d_import_national", f"进口占本国总进口{s.get('d_import_national',0)}%"),
                }
                for key, (col, val) in metrics.items():
                    if key in field and s.get(col, 0) > 0:
                        return f"{country} {val}"
                return f"{country} 产量{s.get('p',0)}% 消费{s.get('d',0)}%"

    except (json.JSONDecodeError, TypeError):
        pass

    if "替代" in field_lower:
        try:
            subs = json.loads(node.get("substitutes", "[]")) if isinstance(node.get("substitutes"), str) else node.get("substitutes", [])
            if subs:
                return ", ".join(s.get("node", "") for s in subs[:3])
        except (json.JSONDecodeError, TypeError):
            pass

    return ""


def detect_new_chains(event_id: str) -> int:
    """检测内容是否涉及尚未收录的产业链，写入 chain_suggestions 表。返回建议数量。"""
    try:
        with connect() as conn:
            event_row = conn.execute(
                "SELECT title, ai_summary, raw_summary FROM events WHERE id = ?",
                (event_id,),
            ).fetchone()
            if not event_row:
                return 0

            title = event_row["title"] or ""
            ai_summary = event_row["ai_summary"] or ""
            raw_summary = event_row["raw_summary"] or ""

            # 获取已有产业链名
            existing = conn.execute(
                "SELECT DISTINCT chain FROM industry_chain_nodes"
            ).fetchall()
            existing_names = [r["chain"] for r in existing]

        content = f"标题: {title}\n\n摘要:\n{ai_summary[:3000]}"
        if raw_summary:
            content += f"\n\n转写原文:\n{raw_summary[:3000]}"

        if len(content.strip()) < 50:
            return 0

        existing_list = "、".join(existing_names) if existing_names else "暂无"

        prompt = f"""你是产业链分析助手。当前系统已收录的产业链: {existing_list}

请阅读以下内容，判断是否涉及**尚未收录的新产业链**。

内容:
{content}

判断标准:
1. 只有内容明确涉及某条产业（如粮食、能源、航运、化工、钢铁...）且当前列表中没有时，才建议新建
2. 每条新链需要 2-5 个核心节点（原材料→中间品→零部件→终端），从内容中提取可验证的初始数据
3. 如果内容只涉及已有链，返回空数组

输出 JSON 数组，每个元素:
{{
  "chain_name": "产业链名(如 粮食产业链)",
  "reason": "为什么建议新建（1-2句话）",
  "source_quote": "原文关键引用",
  "confidence": 0.0-1.0,
  "nodes": [
    {{
      "name": "节点名",
      "node_type": "原材料/中间品/零部件/终端",
      "description": "为什么是核心节点",
      "initial_data": "从原文提取的初始数据描述（如: 俄乌占全球小麦出口30%）"
    }}
  ]
}}

如果没有新链值得建议，返回空数组: []
只输出 JSON。"""

        result = chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2048,
            module="chain_detector",
            task="detect_new_chains",
        )
        if not result:
            return 0

        result = result.strip()
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()

        suggestions = json.loads(result)
        if not isinstance(suggestions, list) or len(suggestions) == 0:
            return 0

        saved = 0
        with connect() as conn:
            for s in suggestions:
                chain_name = s.get("chain_name", "").strip()
                if not chain_name or chain_name in existing_names:
                    continue

                sid = f"csug-{uuid.uuid4().hex[:12]}"
                nodes = s.get("nodes", [])
                conn.execute(
                    """INSERT INTO chain_suggestions (id, chain_name, event_id, nodes_json, reason, source_quote, confidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sid, chain_name, event_id,
                        json.dumps(nodes, ensure_ascii=False),
                        (s.get("reason", ""))[:500],
                        (s.get("source_quote", ""))[:500],
                        min(max(s.get("confidence", 0.6), 0), 1),
                    ),
                )
                saved += 1

        if saved:
            logger.info("chain_detector: %d new chain suggestion(s) for event %s: %s",
                        saved, event_id, ", ".join(s.get("chain_name", "") for s in suggestions))
        return saved

    except (json.JSONDecodeError, Exception) as e:
        logger.warning("detect_new_chains failed for %s: %s", event_id, e)
        return 0
