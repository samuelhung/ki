"""产业链 API — 节点查询 + AI 影响分析"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import (
    chain_analysis_service,
    chain_chat_service,
    chain_collection_service,
    chain_hint_service,
    chain_merge_service,
    chain_node_service,
    chain_report_service,
    chain_suggestion_service,
    chain_sync_service,
)
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
    return chain_analysis_service.analyze_chain_impact(
        req,
        connect_fn=connect,
        chat_fn=chat,
        detect_new_chains_fn=_detect_new_chains,
        service_logger=logger,
    )


def _detect_new_chains(event_id: str):
    from ..chain_detector import detect_new_chains

    return detect_new_chains(event_id)


@router.post("/report")
def chain_report(req: ChainReportRequest):
    """生成指定产业链的概览分析报告（竞争格局、供应链安全、投资机会）。
    报告持久化到 chain_reports 表，force=true 强制重新生成。"""
    return chain_report_service.generate_chain_report(
        req,
        connect_fn=connect,
        chat_fn=chat,
    )




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
        full_nodes = conn.execute(
            """SELECT * FROM industry_chain_nodes
               WHERE chain = ? AND (global_shares IS NULL OR global_shares = '[]')
               ORDER BY sort_order""",
            (chain_name,)
        ).fetchall()

    if not full_nodes:
        return {"ok": True, "collected": 0, "message": "该链所有节点已有数据"}

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
    return chain_hint_service.list_hints(
        status=status,
        limit=limit,
        connect_fn=connect,
    )


@router.get("/hints/count")
def count_hints():
    """获取待处理提示数量（用于前端徽标）"""
    return chain_hint_service.count_hints(connect_fn=connect)


@router.post("/hints/{hint_id}/resolve")
def resolve_hint(hint_id: SafeIdentifier, req: HintResolve):
    """接受或拒绝一个数据更新提示。
    accept: 将 suggested_value 写入对应节点字段
    reject: 标记为已拒绝
    可选的 edited_value 用于用户微调"""
    return chain_hint_service.resolve_hint(
        hint_id,
        req,
        connect_fn=connect,
    )


# ── 新链建议 API ──


@router.get("/suggestions")
def list_suggestions(
    status: str = "pending",
    limit: int = Query(30, ge=1, le=MAX_PAGE_SIZE),
):
    """列出AI建议的新产业链。"""
    return chain_suggestion_service.list_suggestions(
        status=status,
        limit=limit,
        connect_fn=connect,
    )


@router.get("/suggestions/count")
def count_suggestions():
    """获取待处理新链建议数量。"""
    return chain_suggestion_service.count_suggestions(connect_fn=connect)


@router.post("/suggestions/{sid}/adopt")
def adopt_suggestion(sid: SafeIdentifier):
    """采用一条新链建议：创建链和所有节点 + AI 选图标。"""
    return chain_suggestion_service.adopt_suggestion(
        sid,
        connect_fn=connect,
        uuid_factory=uuid.uuid4,
        icon_suggester=_suggest_icon,
    )


def _suggest_icon(chain_name: str) -> str:
    """用 AI 为产业链名匹配最合适的 Lucide 图标名。"""
    return chain_suggestion_service.suggest_icon(
        chain_name,
        chat_fn=chat,
        service_logger=logger,
    )


@router.post("/suggestions/{sid}/dismiss")
def dismiss_suggestion(sid: SafeIdentifier):
    """忽略一条新链建议。"""
    return chain_suggestion_service.dismiss_suggestion(sid, connect_fn=connect)


# ── 分析反哺：同步 extracted_hints 到 hints 表 ──


class SyncHintsRequest(BaseModel):
    hints: list = Field(max_length=100)


@router.post("/hints/sync")
def sync_extracted_hints(req: SyncHintsRequest):
    """将分析反哺的 hints 同步到 chain_data_hints 或 chain_suggestions。"""
    return chain_sync_service.sync_extracted_hints(
        req,
        connect_fn=connect,
        uuid_factory=uuid.uuid4,
    )


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
    return chain_chat_service.chain_chat(
        req,
        connect_fn=connect,
        chat_fn=chat,
    )


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
