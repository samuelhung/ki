"""Series endpoints — CRUD, discovery, AI intro/summary/paper, member management."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import (
    series_discovery_service,
    series_expansion_service,
    series_generation_service,
    series_mutation_service,
    series_query_service,
    series_service,
    series_topic_discovery_service,
)
from ..db import connect, init_db
from ..security.constraints import (
    BoundedIdentifierList,
    SafeIdentifier,
    SafeIdentifierList,
    SafeIdentifierListMinTwo,
)

router = APIRouter(prefix="/api/ingest", tags=["series"])


class SeriesDiscoveryRequest(BaseModel):
    event_ids: SafeIdentifierListMinTwo
    name_hint: str = ""


class SeriesNameRequest(BaseModel):
    member_ids: SafeIdentifierListMinTwo
    current_name: str = ""


class SeriesCreateRequest(BaseModel):
    name: str
    member_ids: SafeIdentifierListMinTwo
    description: str = ""


class SeriesOrderRequest(BaseModel):
    member_ids: BoundedIdentifierList


class SeriesMembersRequest(BaseModel):
    event_ids: SafeIdentifierList


class SeriesMergeRequest(BaseModel):
    source_id: SafeIdentifier
    target_id: SafeIdentifier


def _call_ai_chat(
    messages,
    temperature=0.3,
    max_tokens=3072,
    timeout=120,
    response_format=None,
    module=None,
    task=None,
):
    """Lazy import to avoid circular dependencies with ai_client."""
    from ..ai_client import chat

    return chat(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        response_format=response_format,
        module=module,
        task=task,
    )


# ══════════════════════════════════════════════════
# 系列发现 & CRUD
# ══════════════════════════════════════════════════


@router.get("/series")
def list_series(include_candidates: bool = False):
    """List all series with member event titles. Excludes candidates by default."""
    return series_query_service.list_series(
        include_candidates, connect_fn=connect, init_db_fn=init_db
    )


@router.get("/series/candidates")
def list_candidates():
    """List all candidate series (AI-discovered, not yet published).

    Includes dedup information: flags candidates whose names are similar to
    other candidates or published series.
    """
    return series_query_service.list_candidates(
        connect_fn=connect,
        init_db_fn=init_db,
        name_similarity_fn=series_service.name_similarity,
        member_overlap_score_fn=series_service.member_overlap_score,
    )


@router.post("/series/discover")
def discover_series():
    """AI discovers thematic series by clustering events with overviews.

    Enhanced with:
    - Incremental scanning (new events not in any series, fallback to all)
    - Candidate persistence to DB (upsert by name)
    - Dedup checks against existing candidates and published series
    - Stale candidate cleanup (>7 days)
    """
    return series_discovery_service.discover_series(
        connect_fn=connect, init_db_fn=init_db, chat_fn=_call_ai_chat
    )


# ══════════════════════════════════════════════════
# 两阶段发现（方案 A）：阶段1 全量标题粗分组
# ══════════════════════════════════════════════════


@router.post("/series/discover/stage1")
def discover_stage1():
    """阶段1：全量标题聚类 → 返回主题领域分组。

    解决 LIMIT 60 的片面问题：标题很短（~30字/条），200条才6000字，
    全量喂给 AI 毫无压力。结果不持久化，前端临时状态。

    Returns:
        {groups: [{name, description, event_ids: [...], event_titles: [...], count}]}
    """
    return series_discovery_service.discover_stage1(
        connect_fn=connect, init_db_fn=init_db, chat_fn=_call_ai_chat
    )


@router.post("/series/discover/stage2")
def discover_stage2(data: SeriesDiscoveryRequest):
    """阶段2：精细发现 — 基于用户选中的事件，AI 聚类生成候选专题。

    Expects: {event_ids: [...], name_hint: "可选领域名"}
    Returns: {series: [...candidates], duplicates_skipped: N}
    """
    return series_discovery_service.discover_stage2(
        data, connect_fn=connect, init_db_fn=init_db, chat_fn=_call_ai_chat
    )


# ══════════════════════════════════════════════════
# 按主题发现
# ══════════════════════════════════════════════════


@router.post("/series/discover/by-topic")
def discover_by_topic(data: dict):
    """按用户输入的主题发现相关专题。

    Expects: {topic: "伊朗核问题"}
    流程：SQL 关键字匹配 → 缩小候选池 → AI 聚类 → 去重 → 返回
    """
    return series_topic_discovery_service.discover_by_topic(
        data, connect_fn=connect, init_db_fn=init_db, chat_fn=_call_ai_chat
    )


# ══════════════════════════════════════════════════
# 已有专题扩充
# ══════════════════════════════════════════════════


@router.post("/series/{series_id}/expand")
def expand_series(series_id: SafeIdentifier):
    """为已有专题寻找新成员 — AI 扫描未归属的新内容，推荐加入。

    流程：
    1. 取专题上下文（name + description + 成员概述摘要）
    2. 取最近30条不在本专题的有概述事件
    3. AI 判断哪些应加入，返回推荐列表 + 理由
    """
    return series_expansion_service.expand_series(
        series_id, connect_fn=connect, init_db_fn=init_db, chat_fn=_call_ai_chat
    )


# ══════════════════════════════════════════════════
# 自由组题 — AI 建议名称
# ══════════════════════════════════════════════════


@router.post("/series/suggest-name")
def suggest_series_name(data: SeriesNameRequest):
    """自由组题：根据用户选定的文档，AI 建议专题名称和副标题。

    Expects: {member_ids: [...], current_name: "用户起的临时名（可选）"}
    Returns: {suggested_name: "AI建议标题", suggested_description: "AI建议副标题"}
    """
    return series_expansion_service.suggest_series_name(
        data, connect_fn=connect, init_db_fn=init_db, chat_fn=_call_ai_chat
    )


@router.post("/series")
def create_series(data: SeriesCreateRequest):
    """Create a new series from discovered candidates.

    If a candidate with the same name exists, upgrades it to 'published' (upsert).
    """
    try:
        return series_mutation_service.create_series(
            data, connect_fn=connect, init_db_fn=init_db
        )
    except series_mutation_service.SeriesMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


@router.delete("/series/{series_id}")
def delete_series(series_id: SafeIdentifier):
    """Delete a series."""
    try:
        return series_mutation_service.delete_series(
            series_id, connect_fn=connect, init_db_fn=init_db
        )
    except series_mutation_service.SeriesMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


@router.put("/series/{series_id}")
def update_series(series_id: SafeIdentifier, data: dict):
    """Update series metadata (name, description, status)."""
    try:
        return series_mutation_service.update_series(
            series_id, data, connect_fn=connect, init_db_fn=init_db
        )
    except series_mutation_service.SeriesMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


@router.post("/series/merge")
def merge_series(data: SeriesMergeRequest):
    """Merge a source candidate into a target series.

    Expects: {source_id: str, target_id: str}
    - Moves source's member_ids into target (dedup)
    - Deletes the source candidate
    - Returns updated target
    """
    try:
        return series_mutation_service.merge_series(
            data,
            connect_fn=connect,
            init_db_fn=init_db,
            datetime_cls=series_service.datetime,
        )
    except series_mutation_service.SeriesMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


# ══════════════════════════════════════════════════
# 专题详情 & 成员
# ══════════════════════════════════════════════════


@router.get("/series/{series_id}")
def get_series_detail(series_id: SafeIdentifier):
    """Return full series detail: metadata + enriched member events."""
    try:
        return series_query_service.get_series_detail(
            series_id, connect_fn=connect, init_db_fn=init_db
        )
    except series_query_service.SeriesQueryError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from None


# ══════════════════════════════════════════════════
# AI 导言、速览、深度分析
# ══════════════════════════════════════════════════


@router.put("/series/{series_id}/intro")
def generate_series_intro(series_id: SafeIdentifier):
    """AI generates a narrative intro connecting all member overviews."""
    return series_generation_service.generate_series_intro(
        series_id, connect_fn=connect, init_db_fn=init_db, chat_fn=_call_ai_chat
    )


@router.put("/series/{series_id}/summary")
def generate_series_summary(series_id: SafeIdentifier):
    """AI generates a structured summary of the series — thesis, insights, logic chain, entities, open questions."""
    return series_generation_service.generate_series_summary(
        series_id, connect_fn=connect, init_db_fn=init_db, chat_fn=_call_ai_chat
    )


@router.put("/series/{series_id}/paper")
def generate_series_paper(series_id: SafeIdentifier):
    """AI generates a paper/lecture-style deep analysis of the series.
    Narrative arc: background → analysis → climax (core findings) → conclusion/outlook.
    Paragraph-style writing with thesis-evidence structure and lecture rhythm."""
    return series_generation_service.generate_series_paper(
        series_id, connect_fn=connect, init_db_fn=init_db, chat_fn=_call_ai_chat
    )


# ══════════════════════════════════════════════════
# 排序、建议审核、成员管理
# ══════════════════════════════════════════════════


@router.put("/series/{series_id}/sort")
def reorder_series(series_id: SafeIdentifier, data: SeriesOrderRequest):
    """Update member order via drag-and-drop."""
    try:
        return series_mutation_service.reorder_series(
            series_id, data, connect_fn=connect, init_db_fn=init_db
        )
    except series_mutation_service.SeriesMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


@router.get("/series/{series_id}/suggestions")
def get_series_suggestions(series_id: SafeIdentifier):
    """Get pending member suggestions for a series."""
    try:
        return series_query_service.get_series_suggestions(
            series_id, connect_fn=connect, init_db_fn=init_db
        )
    except series_query_service.SeriesQueryError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from None


@router.post("/series/{series_id}/members")
def add_series_members(series_id: SafeIdentifier, data: SeriesMembersRequest):
    """Add one or more event_ids to a series (non-destructive append)."""
    try:
        return series_mutation_service.add_series_members(
            series_id, data, connect_fn=connect, init_db_fn=init_db
        )
    except series_mutation_service.SeriesMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
