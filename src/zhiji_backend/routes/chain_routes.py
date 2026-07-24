"""产业链 API — 节点查询 + AI 影响分析"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import chain_collection_service, chain_merge_service, chain_node_service
from ..ai_client import chat
from ..db import connect
from ..security.constraints import MAX_PAGE_SIZE, SafeIdentifier

logger = logging.getLogger(__name__)

class AnalyzeRequest(BaseModel):
    event_id: str = ""
    event_title: str = ""
    event_summary: str = ""

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, value: str) -> str:
        if value:
            from ..security.constraints import safe_identifier

            safe_identifier(value)
        return value

class ChainReportRequest(BaseModel):
    chain_name: str
    force: bool = False
    cache_only: bool = False


class GlobalShareGroupsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    production: list[dict]
    supply: list[dict]
    demand: list[dict]


class GroupedGlobalSharesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groups: GlobalShareGroupsPayload


class NodeUpdate(BaseModel):
    name: str | None = None
    node_type: str | None = None
    description: str | None = None
    global_shares: list | GroupedGlobalSharesPayload | None = None
    substitutes: list | None = None
    upstream_names: list[str] | None = Field(default=None, max_length=100)
    data_sources: dict | None = None
    sort_order: int | None = None


class NodeCreate(BaseModel):
    chain: str
    name: str
    node_type: str
    description: str = ""
    global_shares: list = []
    substitutes: list = []
    upstream_names: list[str] = Field(default_factory=list, max_length=100)
    data_sources: dict = {}


class AiUpdateRequest(BaseModel):
    node_id: SafeIdentifier
    source_text: str  # 包含新数据的文本（USGS报告摘要、新闻等）

router = APIRouter(prefix="/api/chains", tags=["chains"])


@router.get("")
def list_chains():
    """列出所有产业链（按 chain 分组的节点数统计 + 图标）"""
    return chain_node_service.list_chains(connect_fn=connect)


@router.get("/meta")
def list_chain_meta():
    """返回所有产业链的元数据（图标等）。"""
    return chain_node_service.list_chain_meta(connect_fn=connect)


@router.post("/flow-summary")
def save_flow_summary(body: FlowSummaryReq):
    """保存产业链的流转逻辑摘要。前端 AI 生成后回传持久化。"""
    return chain_node_service.save_flow_summary(body, connect_fn=connect)


@router.get("/nodes")
def list_nodes():
    """列出所有节点（含全球份额和替代材料）"""
    return chain_node_service.list_nodes(connect_fn=connect)


@router.post("/analyze")
def analyze_chain_impact(req: AnalyzeRequest):
    """分析一条事件对产业链的影响。传入 event_id 则从 DB 读取事件；或直接传入 title+summary。"""
    event_id = req.event_id
    event_title = req.event_title
    event_summary = req.event_summary
    if event_id:
        with connect() as conn:
            conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            ev = conn.execute(
                "SELECT title, ai_summary, raw_summary FROM events WHERE id = ?", (event_id,)
            ).fetchone()
            if not ev:
                return {"error": "事件不存在"}
            event_title = ev.get("title", "") or ""
            event_summary = ev.get("ai_summary", "") or ev.get("raw_summary", "") or ""

    if not event_summary:
        return {"error": "没有事件内容可分析"}

    # 读取所有产业链节点
    with connect() as conn:
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        nodes = conn.execute("""
            SELECT id, chain, name, node_type, description, global_shares, substitutes
            FROM industry_chain_nodes ORDER BY chain, sort_order
        """).fetchall()

    # 构建产业链上下文
    chain_context = _build_chain_context(nodes)

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
        result = chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
            module="chain_analysis",
            task="analyze"
        )
        if not result:
            return {"error": "AI 分析返回空结果"}
        # 二阶段：从分析结果中提取结构化数据点
        extracted_hints = _extract_hints_from_analysis(result, event_title, event_summary[:3000])

        # 持久化分析结果到 events 表
        if event_id:
            with connect() as conn:
                conn.execute(
                    "UPDATE events SET chain_analysis = ? WHERE id = ?",
                    (result, event_id),
                )

        # 异步触发新链检测（不阻塞返回）
        try:
            from ..chain_detector import detect_new_chains
            detect_new_chains(event_id)
        except Exception:
            logger.warning("detect_new_chains failed for %s during analyze", event_id, exc_info=True)

        return {"analysis": result, "matched_nodes": len(nodes), "extracted_hints": extracted_hints}
    except Exception as e:
        return {"error": str(e)}


@router.post("/report")
def chain_report(req: ChainReportRequest):
    """生成指定产业链的概览分析报告（竞争格局、供应链安全、投资机会）。
    报告持久化到 chain_reports 表，force=true 强制重新生成。"""
    chain_name = req.chain_name

    # Check cache
    if not req.force:
        with connect() as conn:
            conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            cached = conn.execute(
                "SELECT report, updated_at FROM chain_reports WHERE chain_name = ?",
                (chain_name,)
            ).fetchone()
            if cached and cached.get("report"):
                return {
                    "report": cached["report"],
                    "chain_name": chain_name,
                    "cached": True,
                    "updated_at": cached.get("updated_at", ""),
                }
        if req.cache_only:
            return {"report": None, "chain_name": chain_name, "cached": False, "missing": True}

    # Read nodes
    with connect() as conn:
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        nodes = conn.execute("""
            SELECT id, chain, name, node_type, description, global_shares, substitutes, data_sources
            FROM industry_chain_nodes WHERE chain = ? ORDER BY sort_order
        """, (chain_name,)).fetchall()

    if not nodes:
        return {"error": f"未找到产业链: {chain_name}"}

    # Build context
    nodes_text_parts = []
    for n in nodes:
        parts = [f"### {n['node_type']}：{n['name']}"]
        if n.get("description"):
            parts.append(f"描述：{n['description']}")
        shares = n.get("global_shares")
        if shares:
            try:
                if isinstance(shares, str):
                    shares = json.loads(shares)
                # 兼容新格式 {"groups":{...}} 和旧格式 [{...}]
                all_s = []
                groups = shares.get("groups") if isinstance(shares, dict) else None
                if groups:
                    for gname in ("production", "supply", "demand"):
                        all_s.extend(groups.get(gname, []))
                elif isinstance(shares, list):
                    all_s = shares
                for s in all_s:
                    c = s.get("c", "未知")
                    metrics = []
                    if s.get("p"):
                        metrics.append(f"全球产量占比 {s['p']}%")
                    if s.get("p_export_global"):
                        metrics.append(f"出口/全球出口 {s['p_export_global']}%")
                    if s.get("p_export_ratio"):
                        metrics.append(f"出口/产量 {s['p_export_ratio']}%")
                    if s.get("d", 0):
                        metrics.append(f"全球消费占比 {s['d']}%")
                    if s.get("d_import_global"):
                        metrics.append(f"进口/全球进口 {s['d_import_global']}%")
                    if s.get("d_import_ratio"):
                        metrics.append(f"进口/消费 {s['d_import_ratio']}%")
                    if metrics:
                        parts.append(f"  {c}: {', '.join(metrics)}")
            except Exception:
                pass
        subs = n.get("substitutes")
        if subs:
            try:
                if isinstance(subs, str):
                    subs = json.loads(subs)
                for sub in subs:
                    parts.append(f"  替代方案：{sub.get('node','')} (成熟度:{sub.get('maturity','')})")
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
        result = chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
            module="chain_analysis",
            task="report"
        )
        if not result:
            return {"error": "AI 分析返回空结果"}

        # Persist to cache
        with connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO chain_reports (chain_name, report, updated_at)
                VALUES (?, ?, datetime('now'))
            """, (chain_name, result))

        return {"report": result, "chain_name": chain_name, "node_count": len(nodes), "cached": False}
    except Exception as e:
        return {"error": str(e)}




def _extract_hints_from_analysis(analysis: str, title: str, summary: str) -> list:
    """从分析报告中提取可同步到产业链的结构化数据点。"""
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

        from ..ai_client import chat
        result = chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
            module="chain_analysis",
            task="extract_hints"
        )
        if not result:
            return []

        result = result.strip()
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()

        import json
        hints = json.loads(result)
        return hints if isinstance(hints, list) else []

    except Exception:
        return []


# ── CRUD ──



_resolve_upstream_ids = chain_node_service.resolve_upstream_ids


@router.put("/nodes/{node_id}")
def update_node(node_id: SafeIdentifier, req: NodeUpdate):
    """更新产业链节点"""
    return chain_node_service.update_node(node_id, req, connect_fn=connect)


@router.post("/nodes")
def create_node(req: NodeCreate):
    """新建产业链节点"""
    return chain_node_service.create_node(
        req, connect_fn=connect, uuid_factory=uuid.uuid4
    )


@router.delete("/nodes/{node_id}")
def delete_node(node_id: SafeIdentifier):
    """删除产业链节点"""
    return chain_node_service.delete_node(node_id, connect_fn=connect)


@router.post("/nodes/ai-update")
def ai_update_node(req: AiUpdateRequest):
    """AI 辅助更新节点数据 — 从来源文本提取结构化指标"""
    with connect() as conn:
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        node = conn.execute(
            "SELECT * FROM industry_chain_nodes WHERE id = ?", (req.node_id,)
        ).fetchone()
        if not node:
            raise HTTPException(status_code=404, detail="节点不存在")

        node["global_shares"] = json.loads(node["global_shares"])
        node["substitutes"] = json.loads(node["substitutes"])

    prompt = f"""你是一位产业链数据专家。以下是节点"{node['name']}"（{node['chain']}，{node['node_type']}）的当前数据：

{json.dumps(node['global_shares'], ensure_ascii=False, indent=2)}

现有替代方案：
{json.dumps(node['substitutes'], ensure_ascii=False, indent=2)}

---
## 来源文本（可能包含更新的数据）
{req.source_text[:4000]}
---

请从来源文本中提取与这个节点相关的结构化数据，按以下 JSON 格式返回：

```json
{{
  "global_shares": [
    {{"c": "国家名", "p": 产量占比, "p_export_global": 出口占全球出口, "p_export_ratio": 出口占产量比, "p_export_national": 占本国总出口, "d": 消费占比, "d_import_global": 进口占全球进口, "d_import_ratio": 进口占消费比, "d_import_national": 占本国总进口}}
  ],
  "substitutes": [
    {{"node": "替代品名", "maturity": "成熟度", "trigger": "触发条件", "advantage": "优势", "bottleneck": "瓶颈"}}
  ],
  "summary": "一句话总结本次更新了什么"
}}
```

规则：
1. 如果来源文本中没有提及某个国家，保留其原有数据不变，不要编造
2. 如果来源文本包含新的数据，用新数据覆盖对应字段
3. 如果来源文本与本节点无关，返回空的 global_shares 和 substitutes
4. 只输出 JSON，不要其他文字"""

    try:
        result = chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2048,
            module="chain_data_update",
            task="ai_update"
        )
        if not result:
            return {"error": "AI 返回空结果"}

        # Extract JSON
        result = result.strip()
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()

        extracted = json.loads(result)

        # Update in DB
        with connect() as conn:
            new_shares = extracted.get("global_shares", [])
            new_subs = extracted.get("substitutes", [])

            if new_shares:
                conn.execute(
                    "UPDATE industry_chain_nodes SET global_shares = ?, last_updated = datetime('now') WHERE id = ?",
                    (json.dumps(new_shares, ensure_ascii=False), req.node_id)
                )
            if new_subs:
                conn.execute(
                    "UPDATE industry_chain_nodes SET substitutes = ?, last_updated = datetime('now') WHERE id = ?",
                    (json.dumps(new_subs, ensure_ascii=False), req.node_id)
                )
            conn.commit()

        return {
            "ok": True,
            "summary": extracted.get("summary", ""),
            "updated_shares": len(new_shares) > 0,
            "updated_subs": len(new_subs) > 0,
            "global_shares": new_shares,
            "substitutes": new_subs,
        }
    except json.JSONDecodeError:
        return {"error": f"AI 返回格式无法解析: {result[:300]}"}
    except Exception as e:
        return {"error": str(e)}


class AiCollectRequest(BaseModel):
    node_id: SafeIdentifier
    use_web: bool = False


def _do_collect(node: dict, use_web: bool = False) -> dict:
    return chain_collection_service.collect_node_data(
        node,
        use_web=use_web,
        connect_fn=connect,
        chat_fn=chat,
        service_logger=logger,
    )


@router.post("/nodes/ai-collect")
def ai_collect_node_data(req: AiCollectRequest):
    """AI 采集节点贸易数据。
    use_web=false → 从已入库内容中搜索相关数据提取
    use_web=true  → 联网搜索后提取 + 标注来源 URL
    """
    with connect() as conn:
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        node = conn.execute(
            "SELECT * FROM industry_chain_nodes WHERE id = ?", (req.node_id,)
        ).fetchone()
        if not node:
            raise HTTPException(status_code=404, detail="节点不存在")

    try:
        return _do_collect(node, req.use_web)
    except json.JSONDecodeError:
        return {"error": "AI 返回格式无法解析"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/ai-collect-all")
def ai_collect_chain_all(req: AiCollectRequest):
    """批量采集整条产业链所有空数据节点"""
    with connect() as conn:
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        node = conn.execute(
            "SELECT chain FROM industry_chain_nodes WHERE id = ?", (req.node_id,)
        ).fetchone()
        if not node:
            raise HTTPException(status_code=404, detail="节点不存在")

        chain_name = node["chain"]
        # 找出该链所有 global_shares 为空或为 '[]' 的节点
        nodes = conn.execute(
            """SELECT id, name FROM industry_chain_nodes
               WHERE chain = ? AND (global_shares IS NULL OR global_shares = '[]')
               ORDER BY sort_order""",
            (chain_name,)
        ).fetchall()

    if not nodes:
        return {"ok": True, "collected": 0, "message": "该链所有节点已有数据"}

    # 读完整节点数据
    full_nodes = []
    for n in nodes:
        row = conn.execute(
            "SELECT * FROM industry_chain_nodes WHERE id = ?", (n["id"],)
        ).fetchone()
        if row:
            full_nodes.append(row)

    collected = []
    for node in full_nodes:
        try:
            r = _do_collect(node, req.use_web)
            if r.get("ok"):
                collected.append({"id": node["id"], "name": node["name"], "countries": r.get("countries", 0)})
        except Exception as e:
            logger.warning("ai_collect_all: failed for node %s: %s", node["id"], e)

    return {"ok": True, "chain": chain_name, "collected": len(collected), "nodes": collected}


# ── Helpers ──


def _build_chain_context(nodes: list[dict]) -> str:
    """将节点数据构建为 AI 可读的上下文"""
    chains: dict[str, list] = {}
    for n in nodes:
        chain_name = n["chain"]
        if chain_name not in chains:
            chains[chain_name] = []
        chains[chain_name].append(n)

    parts = []
    for chain_name, chain_nodes in chains.items():
        parts.append(f"### {chain_name}")
        for n in chain_nodes:
            shares_str = ""
            if n["global_shares"]:
                try:
                    raw = json.loads(n["global_shares"]) if isinstance(n["global_shares"], str) else n["global_shares"]
                    # 兼容新格式 {"groups":{...}} 和旧格式 [{...}]
                    all_shares = []
                    groups = raw.get("groups") if isinstance(raw, dict) else None
                    if groups:
                        for gname in ("production", "supply", "demand"):
                            all_shares.extend(groups.get(gname, []))
                    elif isinstance(raw, list):
                        all_shares = raw
                    items = []
                    for s in all_shares:
                        parts_s = [s['c']]
                        if s.get("p", 0) > 0:
                            parts_s.append(f"产量占全球{s['p']}%")
                            if s.get("p_export_global", 0) > 0:
                                parts_s.append(f"出口占全球{s['p_export_global']}%")
                            if s.get("p_export_ratio", 0) > 0:
                                parts_s.append(f"出口/产量比{s['p_export_ratio']}%")
                            if s.get("p_export_national", 0) > 0:
                                parts_s.append(f"占本国总出口{s['p_export_national']}%")
                        if s.get("d", 0) > 0:
                            parts_s.append(f"消费占全球{s['d']}%")
                            if s.get("d_import_global", 0) > 0:
                                parts_s.append(f"进口占全球{s['d_import_global']}%")
                            if s.get("d_import_ratio", 0) > 0:
                                parts_s.append(f"进口/消费比{s['d_import_ratio']}%")
                            if s.get("d_import_national", 0) > 0:
                                parts_s.append(f"占本国总进口{s['d_import_national']}%")
                        items.append(" | ".join(parts_s))
                    shares_str = "  ".join(items)
                except (json.JSONDecodeError, TypeError):
                    pass

            subs_str = ""
            if n["substitutes"]:
                try:
                    subs = json.loads(n["substitutes"]) if isinstance(n["substitutes"], str) else n["substitutes"]
                    items = []
                    for s in subs:
                        items.append(f"{s['node']}({s['maturity']}, 触发:{s['trigger']})")
                    subs_str = "替代品: " + "; ".join(items)
                except (json.JSONDecodeError, TypeError):
                    pass

            desc = n.get("description", "") or ""
            type_tag = n["node_type"]
            parts.append(f"- [{type_tag}] {n['name']}: {desc}")
            if shares_str:
                parts.append(f"  全球份额: {shares_str}")
            if subs_str:
                parts.append(f"  {subs_str}")
        parts.append("")

    return "\n".join(parts)


# ── 数据更新提示 API ──


class HintResolve(BaseModel):
    action: str  # "accept" | "reject"
    edited_value: str = ""  # accept 时可提供用户微调后的值


@router.get("/hints")
def list_hints(
    status: str = "pending",
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
):
    """列出产业链数据更新提示。status: pending / reviewed / accepted / rejected"""
    with connect() as conn:
        rows = conn.execute(
            """SELECT h.*, n.name as node_name
               FROM chain_data_hints h
               LEFT JOIN industry_chain_nodes n ON n.id = h.node_id
               WHERE h.status = ?
               ORDER BY h.created_at DESC
               LIMIT ?""",
            (status, limit),
        ).fetchall()
    return {"hints": [dict(r) for r in rows]}


@router.get("/hints/count")
def count_hints():
    """获取待处理提示数量（用于前端徽标）"""
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM chain_data_hints WHERE status = 'pending'"
        ).fetchone()
    return {"pending": row["cnt"] if row else 0}


@router.post("/hints/{hint_id}/resolve")
def resolve_hint(hint_id: SafeIdentifier, req: HintResolve):
    """接受或拒绝一个数据更新提示。
    accept: 将 suggested_value 写入对应节点字段
    reject: 标记为已拒绝
    可选的 edited_value 用于用户微调"""
    with connect() as conn:
        hint = conn.execute(
            "SELECT * FROM chain_data_hints WHERE id = ?", (hint_id,)
        ).fetchone()
        if not hint:
            raise HTTPException(404, "提示不存在")

        hint = dict(hint)

        if req.action == "accept":
            # 使用用户微调值或建议值
            final_value = req.edited_value.strip() if req.edited_value.strip() else hint["suggested_value"]

            # 更新节点数据
            node = conn.execute(
                "SELECT global_shares, substitutes FROM industry_chain_nodes WHERE id = ?",
                (hint["node_id"],),
            ).fetchone()
            if node:
                _apply_hint_update(conn, hint, final_value, dict(node))

            # 标记已接受
            conn.execute(
                """UPDATE chain_data_hints SET status = 'accepted', reviewed_at = datetime('now'),
                   resolved_value = ? WHERE id = ?""",
                (final_value, hint_id),
            )
        elif req.action == "reject":
            conn.execute(
                """UPDATE chain_data_hints SET status = 'rejected', reviewed_at = datetime('now')
                   WHERE id = ?""",
                (hint_id,),
            )
        else:
            raise HTTPException(400, f"未知 action: {req.action}")

    return {"ok": True, "action": req.action}


def _apply_hint_update(conn, hint: dict, new_value: str, node: dict):
    """将 hint 的建议值写入节点数据。"""
    import json as _json

    field = hint.get("field", "")
    field_lower = field.lower()

    shares = _json.loads(node.get("global_shares", "[]")) if isinstance(node.get("global_shares"), str) else (node.get("global_shares") or [])
    updated = False

    # 尝试匹配国家+指标组合
    for s in shares:
        country = s.get("c", "")
        if country and country in field:
            _try_parse_and_set(s, new_value, field)
            updated = True
            break

    if not updated and "替代" in field_lower:
        # 待后续实现更智能的替代方案更新
        pass

    if updated:
        conn.execute(
            "UPDATE industry_chain_nodes SET global_shares = ?, last_updated = datetime('now') WHERE id = ?",
            (_json.dumps(shares, ensure_ascii=False), hint["node_id"]),
        )


def _try_parse_and_set(share: dict, new_value: str, field: str):
    """尝试从 new_value 字符串中解析数字并设置到 share dict 的对应字段。"""
    import re as _re

    numbers = _re.findall(r"(\d+(?:\.\d+)?)\s*%?", new_value)
    if not numbers:
        return

    val = float(numbers[0])

    field_lower = field.lower()
    if "出口占全球" in field_lower:
        share["p_export_global"] = val
    elif "出口/产量" in field_lower or "出口占产量" in field_lower:
        share["p_export_ratio"] = val
    elif "出口占本国" in field_lower or "出口占总出口" in field_lower:
        share["p_export_national"] = val
    elif "进口占全球" in field_lower:
        share["d_import_global"] = val
    elif "进口/消费" in field_lower or "进口占消费" in field_lower:
        share["d_import_ratio"] = val
    elif "进口占本国" in field_lower or "进口占总进口" in field_lower:
        share["d_import_national"] = val
    elif "消费" in field_lower:
        share["d"] = val
    else:
        share["p"] = val  # 默认产量




# ── 新链建议 API ──


@router.get("/suggestions")
def list_suggestions(
    status: str = "pending",
    limit: int = Query(30, ge=1, le=MAX_PAGE_SIZE),
):
    """列出AI建议的新产业链。"""
    with connect() as conn:
        rows = conn.execute(
            """SELECT * FROM chain_suggestions
               WHERE status = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (status, limit),
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["nodes_json"] = json.loads(d["nodes_json"]) if isinstance(d["nodes_json"], str) else d["nodes_json"]
        items.append(d)
    return {"suggestions": items}


@router.get("/suggestions/count")
def count_suggestions():
    """获取待处理新链建议数量。"""
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM chain_suggestions WHERE status = 'pending'"
        ).fetchone()
    return {"pending": row["cnt"] if row else 0}


@router.post("/suggestions/{sid}/adopt")
def adopt_suggestion(sid: SafeIdentifier):
    """采用一条新链建议：创建链和所有节点 + AI 选图标。"""
    with connect() as conn:
        sug = conn.execute("SELECT * FROM chain_suggestions WHERE id = ?", (sid,)).fetchone()
        if not sug:
            raise HTTPException(404, "建议不存在")

        sug = dict(sug)
        nodes = json.loads(sug["nodes_json"]) if isinstance(sug["nodes_json"], str) else sug["nodes_json"]

        created = []
        for i, n in enumerate(nodes):
            node_id = str(uuid.uuid4())
            # 自动串联：每个节点(序号>0)的上游 = 前一个节点
            upstream = json.dumps([created[-1]["id"]]) if created else None
            conn.execute(
                """INSERT INTO industry_chain_nodes (id, chain, name, node_type, description, sort_order, upstream_ids)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (node_id, sug["chain_name"], n.get("name", "?"), n.get("node_type", "原材料"),
                 n.get("description", ""), i, upstream),
            )
            created.append({"id": node_id, "name": n.get("name", "?")})

        conn.execute(
            "UPDATE chain_suggestions SET status = 'adopted', reviewed_at = datetime('now') WHERE id = ?",
            (sid,),
        )

    # AI 推荐图标
    icon = _suggest_icon(sug["chain_name"])

    # 存入 chain_meta
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO chain_meta (chain_name, icon, created_at) VALUES (?, ?, datetime('now'))",
            (sug["chain_name"], icon),
        )

    return {"ok": True, "chain_name": sug["chain_name"], "icon": icon,
            "nodes_created": len(created), "nodes": created}


def _suggest_icon(chain_name: str) -> str:
    """用 AI 为产业链名匹配最合适的 Lucide 图标名。"""
    icon_list = [
        "Zap", "Sun", "Cpu", "Factory", "Wheat", "Flame", "Hammer",
        "Shirt", "Truck", "Heart", "Building", "Cloud", "DollarSign",
        "Leaf", "Anchor", "Microscope", "Droplets", "ShoppingCart",
        "Ship", "Plane", "Shield", "Radio", "Globe", "Database",
    ]
    prompt = f"""从以下 Lucide 图标名中选择最适合「{chain_name}」的一个图标。

可选图标: {', '.join(icon_list)}

规则:
1. 只返回图标名，不要加引号或其他文字
2. 根据产业链的核心实物/活动来选择（如粮食→Wheat, 石油→Droplets, 钢铁→Hammer, 服装→Shirt, 医药→Heart, 物流→Truck, 航空→Plane, 金融→DollarSign, 农业→Leaf, 建筑→Building, 军工→Shield, 云计算→Cloud, 通信→Radio）
3. 如果都不合适，返回 Factory"""
    try:
        result = chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=32,
            module="chain_meta",
            task="suggest_icon"
        )
        if result:
            icon = result.strip().strip('"').strip("'")
            if icon in icon_list:
                return icon
    except Exception:
        logger.warning("_suggest_icon failed for %s", chain_name, exc_info=True)
    return "Factory"


@router.post("/suggestions/{sid}/dismiss")
def dismiss_suggestion(sid: SafeIdentifier):
    """忽略一条新链建议。"""
    with connect() as conn:
        conn.execute(
            "UPDATE chain_suggestions SET status = 'dismissed', reviewed_at = datetime('now') WHERE id = ?",
            (sid,),
        )
    return {"ok": True}


# ── 分析反哺：同步 extracted_hints 到 hints 表 ──


class SyncHintsRequest(BaseModel):
    hints: list = Field(max_length=100)


@router.post("/hints/sync")
def sync_extracted_hints(req: SyncHintsRequest):
    """将分析反哺的 hints 同步到 chain_data_hints 或 chain_suggestions。"""
    saved = 0
    new_suggestions = 0

    with connect() as conn:
        # 获取已有节点名映射
        nodes = conn.execute("SELECT id, name, chain FROM industry_chain_nodes").fetchall()
        name_map = {n["name"]: (n["id"], n["chain"]) for n in nodes}

        for h in req.hints:
            node_name = h.get("node_name", "").strip()

            if node_name in name_map:
                # 已有节点 → 写入 chain_data_hints
                node_id, chain = name_map[node_name]
                hint_id = f"chint-{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """INSERT INTO chain_data_hints (id, event_id, node_id, chain, field, current_value, suggested_value, source_quote, confidence)
                       VALUES (?, '', ?, ?, ?, '', ?, ?, 0.7)""",
                    (hint_id, node_id, chain, h.get("field", ""), h.get("value", ""), h.get("source_quote", "")),
                )
                saved += 1

            elif node_name == "建议新建":
                # 无法匹配 → 写入 chain_suggestions
                sid = f"csug-{uuid.uuid4().hex[:12]}"
                node_data = [{
                    "name": h.get("field", "未知节点"),
                    "node_type": "原材料",
                    "description": h.get("value", ""),
                    "initial_data": h.get("source_quote", ""),
                }]
                conn.execute(
                    """INSERT INTO chain_suggestions (id, chain_name, event_id, nodes_json, reason, source_quote, confidence)
                       VALUES (?, ?, '', ?, ?, ?, 0.6)""",
                    (sid, f"建议: {node_name}", json.dumps(node_data, ensure_ascii=False),
                     f"从分析中提取: {h.get('value','')}", h.get("source_quote", "")),
                )
                new_suggestions += 1

    return {"ok": True, "saved_hints": saved, "new_suggestions": new_suggestions}


# ── 产业链智能答疑 ──

class ChatRequest(BaseModel):
    chain_name: str
    message: str
    history: list[dict] = Field(default_factory=list, max_length=100)


class FlowSummaryReq(BaseModel):
    chain_name: str
    flow_summary: str

@router.post("/chat")
def chain_chat(req: ChatRequest):
    """产业链智能答疑：基于节点数据回答用户问题。"""
    # 读取该链全部节点
    with connect() as conn:
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        nodes = conn.execute("""
            SELECT id, chain, name, node_type, description, global_shares, substitutes,
                   upstream_ids, data_sources
            FROM industry_chain_nodes WHERE chain = ? ORDER BY sort_order
        """, (req.chain_name,)).fetchall()

    if not nodes:
        return {"error": f"未找到产业链: {req.chain_name}"}

    # 构建节点上下文（简洁版，控制 token）
    node_lines = []
    for n in nodes:
        parts = [f"- [{n['node_type']}] {n['name']}"]
        if n.get("description"):
            parts.append(f"  描述: {n['description']}")
        shares = n.get("global_shares")
        if shares and shares != "[]":
            try:
                if isinstance(shares, str):
                    shares = json.loads(shares)
                # 兼容新格式 {"groups":{...}} 和旧格式 [{...}]
                all_share_items = []
                groups = shares.get("groups") if isinstance(shares, dict) else None
                if groups:
                    for gname in ("production", "supply", "demand"):
                        all_share_items.extend(groups.get(gname, []))
                elif isinstance(shares, list):
                    all_share_items = shares
                country_parts = []
                for s in all_share_items:
                    c = s.get("c", "未知")
                    nums = []
                    if s.get("p", 0) > 0:
                        nums.append(f"产量{s['p']}%")
                    if s.get("d", 0) > 0:
                        nums.append(f"消费{s['d']}%")
                    if s.get("p_export_global", 0) > 0:
                        nums.append(f"出口/全球{s['p_export_global']}%")
                    if s.get("d_import_global", 0) > 0:
                        nums.append(f"进口/全球{s['d_import_global']}%")
                    if nums:
                        country_parts.append(f"{c}({', '.join(nums)})")
                if country_parts:
                    parts.append(f"  全球份额: {'; '.join(country_parts[:5])}")
            except Exception:
                pass
        subs = n.get("substitutes")
        if subs and subs != "[]":
            try:
                if isinstance(subs, str):
                    subs = json.loads(subs)
                sub_names = [s.get("node", "?") for s in subs[:3]]
                if sub_names:
                    parts.append(f"  替代: {', '.join(sub_names)}")
            except Exception:
                pass
        # 上游关系
        upstream = n.get("upstream_ids")
        if upstream and upstream != "[]":
            try:
                if isinstance(upstream, str):
                    upstream = json.loads(upstream)
                upstream_names = []
                for uid in upstream:
                    for n2 in nodes:
                        if n2["id"] == uid:
                            upstream_names.append(n2["name"])
                            break
                if upstream_names:
                    parts.append(f"  上游: {' → '.join(upstream_names)}")
            except Exception:
                pass
        node_lines.append("\n".join(parts))

    nodes_context = "\n".join(node_lines)

    system_prompt = f"""你是一位产业链分析专家。以下是「{req.chain_name}」的完整数据，请基于这些数据回答用户问题。

## 产业链数据

{nodes_context}

规则:
1. 优先使用上述数据中的具体数字和信息
2. 数据中没有提到的内容，可以基于你对产业的了解补充，但要明确标注「据一般了解」或「估算」
3. 回答要简洁专业，控制在 300 字以内
4. 如果用户问的问题和数据完全无关，从产业常识角度回答
5. 用中文回答"""

    messages = [{"role": "system", "content": system_prompt}]
    for h in req.history[-10:]:  # 最多保留 10 轮
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": req.message})

    try:
        result = chat(
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
            module="chain_chat",
            task="chat"
        )
        if not result:
            return {"error": "AI 返回空结果"}
        return {"reply": result}
    except Exception as e:
        return {"error": str(e)}
        if not result:
            return {"error": "AI 返回空结果"}
        return {"reply": result}
    except Exception as e:
        return {"error": str(e)}


# ── 产业链重叠检测 ──

@router.get("/overlap-check")
def check_chain_overlaps():
    """检测产业链之间的重叠节点和上下游承接关系，建议合并。"""
    return chain_merge_service.check_chain_overlaps(connect_fn=connect)


class MergeRequest(BaseModel):
    chain_a: str
    chain_b: str
    into: str  # "a" | "b" | "new:新链名"


@router.post("/merge")
def merge_chains(req: MergeRequest):
    """合并两条产业链。into = "a" 保留链A并把B并入；"b" 保留B并入A；"new:名称" 创建新链。"""
    return chain_merge_service.merge_chains(
        req,
        connect_fn=connect,
        chat_fn=chat,
        icon_suggester=_suggest_icon,
        service_logger=logger,
    )
