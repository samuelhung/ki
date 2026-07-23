"""Series endpoints — CRUD, discovery, AI intro/summary/paper, member management."""

import json
import logging
import re
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import series_service
from ..db import connect, init_db
from ..security.constraints import (
    BoundedIdentifierList,
    SafeIdentifier,
    SafeIdentifierList,
    SafeIdentifierListMinTwo,
)

logger = logging.getLogger(__name__)

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


def _call_ai_chat(messages, temperature=0.3, max_tokens=3072, timeout=120, response_format=None,
                        module=None, task=None):
    """Lazy import to avoid circular dependencies with ai_client."""
    from ..ai_client import chat
    return chat(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout,
                response_format=response_format, module=module, task=task)


# ══════════════════════════════════════════════════
# 去重工具函数
# ══════════════════════════════════════════════════

_name_similarity = series_service.name_similarity
_member_overlap_score = series_service.member_overlap_score


def _find_duplicate(conn, new_name: str, new_member_ids: list,
                    threshold_name: float = 0.7, threshold_member: float = 0.5):
    """检查新候选是否与已有 candidate/published 重复。
    返回 (is_dup: bool, existing_series: dict | None)。"""
    rows = conn.execute(
        "SELECT id, name, description, member_ids, status FROM series "
        "WHERE status IN ('candidate', 'published')"
    ).fetchall()
    for row in rows:
        name_sim = _name_similarity(new_name, row["name"])
        try:
            existing_ids = json.loads(row["member_ids"])
        except (json.JSONDecodeError, TypeError):
            existing_ids = []
        member_sim = _member_overlap_score(new_member_ids, existing_ids)
        # 重名判定：名称高度相似 或 （中等名称相似 + 高成员重叠）
        if name_sim >= threshold_name or (name_sim >= 0.5 and member_sim >= threshold_member):
            return True, dict(row)
    return False, None


def _cleanup_stale_candidates(conn, max_age_days: int = 7) -> int:
    """删除超过 max_age_days 天的候选专题。返回删除数量。"""
    cutoff = (datetime.now() - timedelta(days=max_age_days)).strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.execute(
        "DELETE FROM series WHERE status = 'candidate' AND created_at < ?", (cutoff,)
    )
    return cursor.rowcount


# ══════════════════════════════════════════════════
# 系列发现 & CRUD
# ══════════════════════════════════════════════════

@router.get("/series")
def list_series(include_candidates: bool = False):
    """List all series with member event titles. Excludes candidates by default."""
    return series_service.list_series(
        include_candidates, connect_fn=connect, init_db_fn=init_db
    )


@router.get("/series/candidates")
def list_candidates():
    """List all candidate series (AI-discovered, not yet published).

    Includes dedup information: flags candidates whose names are similar to
    other candidates or published series.
    """
    return series_service.list_candidates(connect_fn=connect, init_db_fn=init_db)


@router.post("/series/discover")
def discover_series():
    """AI discovers thematic series by clustering events with overviews.

    Enhanced with:
    - Incremental scanning (new events not in any series, fallback to all)
    - Candidate persistence to DB (upsert by name)
    - Dedup checks against existing candidates and published series
    - Stale candidate cleanup (>7 days)
    """
    init_db()
    with connect() as conn:
        # 收集所有有概述的事件
        all_rows = conn.execute(
            "SELECT id, title, overview FROM events "
            "WHERE overview IS NOT NULL AND overview != '' AND status != 'error' "
            "ORDER BY created_at DESC LIMIT 60"
        ).fetchall()

        if len(all_rows) < 3:
            return {"message": "有概述的事件不足 3 条，无法发现专题", "series": []}

        # 增量扫描：找出尚未归属任何 series 的新事件
        used_ids = set()
        existing_series_rows = conn.execute(
            "SELECT member_ids FROM series WHERE status = 'published'"
        ).fetchall()
        for sr in existing_series_rows:
            try:
                ids = json.loads(sr["member_ids"])
                used_ids.update(ids)
            except (json.JSONDecodeError, TypeError):
                pass

        new_rows = [r for r in all_rows if r["id"] not in used_ids]
        # 如果新事件不足 3 条，退化为全量扫描
        if len(new_rows) < 3:
            new_rows = all_rows

        # 获取已有候选作为上下文
        candidates_rows = conn.execute(
            "SELECT id, name, description, member_ids FROM series WHERE status = 'candidate'"
        ).fetchall()

    events_text = ""
    for ev in new_rows:
        ov = ev["overview"] or ""
        events_text += f"\n### 事件ID: {ev['id']}\n标题: {ev['title']}\n概述: {ov}\n"

    # 构建 prompt：已有候选 + 新事件
    candidates_context = ""
    if candidates_rows:
        candidates_context = "\n## 已有候选专题（可确认/修改/舍弃）\n"
        for c in candidates_rows:
            try:
                mids = json.loads(c["member_ids"])
            except (json.JSONDecodeError, TypeError):
                mids = []
            candidates_context += (
                f"- **{c['name']}**（id: {c['id']}）: {c['description'] or ''}，"
                f"成员 {len(mids)} 条\n"
            )

    prompt = f"""你是知识专题策展人。请分析以下事件概述，将它们聚类成 1-3 个有意义的专题系列。

{candidates_context}

事件列表：
{events_text}

要求：
- 每个专题需包含至少 2 条事件
- 为每个专题生成简洁的名称（≤20字）和一句话描述（≤80字）
- member_ids 必须使用上面给出的真实"事件ID"值（不能使用序号）
- 一条内容可以属于多个专题
- 如果新内容和已有候选相似，可以在 name 前加「确认:」前缀表示建议合并到该候选
- 输出 JSON 数组，格式：[{{"name": "...", "description": "...", "member_ids": ["真实的event_id", ...], "rationale": "为什么这些内容构成一个专题"}}]
- 直接输出 JSON，不要 Markdown 包裹"""

    messages = [
        {"role": "system", "content": "你是知识专题策展人。输出纯 JSON 数组，每个元素包含 name/description/member_ids/rationale。"},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = _call_ai_chat(messages, temperature=0.4, max_tokens=4096, timeout=120,
                                  response_format={"type": "json_object"},
                                  module="series", task="discover")
        if not raw:
            return {"message": "AI 未返回结果", "series": []}

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n```$", "", raw)

        candidates = json.loads(raw)
        if not isinstance(candidates, list):
            return {"message": "AI 返回格式异常", "series": []}

        # 解析 member_ids + 去重检查 + 持久化候选
        member_id_set = set()
        persisted = []
        skipped_dupes = []
        stale_cleaned = 0
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 先收集所有 member_id 用于解析标题
        for c in candidates:
            for mid in c.get("member_ids", []):
                member_id_set.add(mid)

        with connect() as conn:
            # 清理过期候选
            stale_cleaned = _cleanup_stale_candidates(conn)

            # 解析成员标题
            title_map = {}
            if member_id_set:
                placeholders = ",".join(["?" for _ in member_id_set])
                title_rows = conn.execute(
                    f"SELECT id, title FROM events WHERE id IN ({placeholders})",
                    list(member_id_set),
                ).fetchall()
                title_map = {r["id"]: r["title"] for r in title_rows}

            for c in candidates:
                mids = c.get("member_ids", [])
                c["member_titles"] = [title_map.get(mid, "(已删除)") for mid in mids]

                # 去重检查
                is_dup, existing = _find_duplicate(conn, c.get("name", ""), mids)
                if is_dup:
                    c["_duplicate_of"] = {
                        "id": existing["id"],
                        "name": existing["name"],
                        "status": existing["status"],
                    }
                    skipped_dupes.append(c)
                    continue

                # 持久化候选（按 name upsert）
                series_id = f"series-{uuid.uuid4().hex[:12]}"
                existing_candidate = conn.execute(
                    "SELECT id FROM series WHERE name = ? AND status = 'candidate'",
                    (c["name"],)
                ).fetchone()

                if existing_candidate:
                    # 更新已有候选
                    conn.execute(
                        "UPDATE series SET description = ?, member_ids = ?, updated_at = ? WHERE id = ?",
                        (c.get("description", ""), json.dumps(mids), now_ts, existing_candidate["id"]),
                    )
                    c["_persisted_id"] = existing_candidate["id"]
                else:
                    conn.execute(
                        "INSERT INTO series (id, name, description, member_ids, status, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, 'candidate', ?, ?)",
                        (series_id, c.get("name", ""), c.get("description", ""), json.dumps(mids), now_ts, now_ts),
                    )
                    c["_persisted_id"] = series_id
                persisted.append(c)

        return {
            "series": persisted,
            "duplicates_skipped": len(skipped_dupes),
            "duplicates": skipped_dupes if skipped_dupes else [],
            "stale_cleaned": stale_cleaned,
            "events_scanned": len(new_rows),
            "events_total": len(all_rows),
        }

    except (json.JSONDecodeError, Exception) as e:
        logger.exception("Series discovery failed")
        return {"message": f"AI 结果解析失败: {str(e)[:200]}", "series": []}


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
    init_db()
    with connect() as conn:
        # 全量有概述事件，不限 60 条
        event_rows = conn.execute(
            "SELECT id, title FROM events "
            "WHERE overview IS NOT NULL AND overview != '' AND status != 'error' "
            "ORDER BY created_at DESC"
        ).fetchall()

    if len(event_rows) < 3:
        return {"message": "有概述的事件不足 3 条，无法发现专题", "groups": []}

    # 构建紧凑的标题列表
    titles_text = ""
    for ev in event_rows:
        titles_text += f"- [{ev['id']}] {ev['title']}\n"

    # 获取已有专题名，指导 AI 不要重复
    with connect() as conn:
        existing = conn.execute(
            "SELECT name FROM series WHERE status IN ('candidate', 'published')"
        ).fetchall()
    existing_names = "\n".join([f"- {r['name']}" for r in existing]) if existing else "（无）"

    prompt = f"""你是知识专题策展人。请根据以下事件标题，将它们按主题领域粗分组。

事件标题列表（共 {len(event_rows)} 条）：
{titles_text}

已有的专题（不要再生成同名或相似专题）：
{existing_names}

要求：
- 按主题领域分组，每组 3-20 条，内容可跨组（一条可归入多组）
- 为每组生成简洁的领域名称（≤15字）和一句话描述（≤40字）
- event_ids 必须使用上面给出的真实 ID（如 [evt-xxx]）
- 输出 1-8 个组
- 输出 JSON 数组，格式：[{{"name": "...", "description": "...", "event_ids": ["真实的event_id", ...]}}]
- 直接输出 JSON，不要 Markdown 包裹"""

    messages = [
        {"role": "system", "content": "你是知识专题策展人。按主题领域对事件标题分组，输出纯 JSON 数组。"},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = _call_ai_chat(messages, temperature=0.3, max_tokens=4096, timeout=120,
                                  response_format={"type": "json_object"},
                                  module="series", task="discover_stage1")
        if not raw:
            return {"message": "AI 未返回结果", "groups": []}

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n```$", "", raw)

        groups = json.loads(raw)
        if not isinstance(groups, list):
            return {"message": "AI 返回格式异常", "groups": []}

        # 解析标题
        all_ids = set()
        for g in groups:
            for eid in g.get("event_ids", []):
                # Strip brackets that AI may copy from the prompt format "[evt-xxx]"
                eid = eid.strip().lstrip("[").rstrip("]")
                all_ids.add(eid)
            # Rewrite cleaned IDs back into the group
            cleaned = []
            for eid in g.get("event_ids", []):
                cleaned.append(eid.strip().lstrip("[").rstrip("]"))
            g["event_ids"] = cleaned

        title_map = {}
        if all_ids:
            with connect() as conn:
                placeholders = ",".join(["?" for _ in all_ids])
                rows = conn.execute(
                    f"SELECT id, title FROM events WHERE id IN ({placeholders})",
                    list(all_ids),
                ).fetchall()
                title_map = {r["id"]: r["title"] for r in rows}

        for g in groups:
            ids = g.get("event_ids", [])
            g["event_titles"] = [title_map.get(eid, "(已删除)") for eid in ids]
            g["count"] = len(ids)

        return {"groups": groups, "total_events": len(event_rows)}

    except (json.JSONDecodeError, Exception) as e:
        logger.exception("Stage1 discovery failed")
        return {"message": f"阶段1失败: {str(e)[:200]}", "groups": []}


@router.post("/series/discover/stage2")
def discover_stage2(data: SeriesDiscoveryRequest):
    """阶段2：精细发现 — 基于用户选中的事件，AI 聚类生成候选专题。
    
    Expects: {event_ids: [...], name_hint: "可选领域名"}
    Returns: {series: [...candidates], duplicates_skipped: N}
    """
    init_db()
    event_ids = data.event_ids
    name_hint = data.name_hint.strip()

    with connect() as conn:
        placeholders = ",".join(["?" for _ in event_ids])
        event_rows = conn.execute(
            f"SELECT id, title, overview FROM events WHERE id IN ({placeholders}) AND overview IS NOT NULL AND overview != ''",
            event_ids,
        ).fetchall()

    if len(event_rows) < 2:
        return {"message": "有效概述事件不足 2 条", "series": []}

    events_text = ""
    for ev in event_rows:
        ov = ev["overview"] or ""
        events_text += f"\n### 事件ID: {ev['id']}\n标题: {ev['title']}\n概述: {ov}\n"

    hint_line = f"\n领域提示：这些内容属于「{name_hint}」相关领域。\n" if name_hint else ""

    prompt = f"""你是知识专题策展人。请分析以下事件概述，将它们聚类成 1-3 个有意义的专题系列。

{hint_line}
事件列表：
{events_text}

要求：
- 每个专题需包含至少 2 条事件
- 为每个专题生成简洁的名称（≤20字）和一句话描述（≤80字）
- member_ids 必须使用上面给出的真实"事件ID"值
- 一条内容可以属于多个专题
- 输出 JSON 数组，格式：[{{"name": "...", "description": "...", "member_ids": ["真实的event_id", ...], "rationale": "为什么这些内容构成一个专题"}}]
- 直接输出 JSON，不要 Markdown 包裹"""

    messages = [
        {"role": "system", "content": "你是知识专题策展人。输出纯 JSON 数组，每个元素包含 name/description/member_ids/rationale。"},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = _call_ai_chat(messages, temperature=0.4, max_tokens=4096, timeout=120,
                                  response_format={"type": "json_object"},
                                  module="series", task="discover_stage2")
        if not raw:
            return {"message": "AI 未返回结果", "series": []}

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n```$", "", raw)

        candidates = json.loads(raw)
        if not isinstance(candidates, list):
            return {"message": "AI 返回格式异常", "series": []}

        # 解析成员标题
        member_id_set = set()
        for c in candidates:
            for mid in c.get("member_ids", []):
                # Strip brackets that AI may inadvertently copy
                mid = mid.strip().lstrip("[").rstrip("]")
                member_id_set.add(mid)
            # Rewrite cleaned IDs back
            c["member_ids"] = [mid.strip().lstrip("[").rstrip("]") for mid in c.get("member_ids", [])]

        persisted = []
        skipped_dupes = []
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with connect() as conn:
            title_map = {}
            if member_id_set:
                placeholders2 = ",".join(["?" for _ in member_id_set])
                title_rows = conn.execute(
                    f"SELECT id, title FROM events WHERE id IN ({placeholders2})",
                    list(member_id_set),
                ).fetchall()
                title_map = {r["id"]: r["title"] for r in title_rows}

            for c in candidates:
                mids = c.get("member_ids", [])
                c["member_titles"] = [title_map.get(mid, "(已删除)") for mid in mids]

                # 去重检查
                is_dup, existing = _find_duplicate(conn, c.get("name", ""), mids)
                if is_dup:
                    c["_duplicate_of"] = {
                        "id": existing["id"],
                        "name": existing["name"],
                        "status": existing["status"],
                    }
                    skipped_dupes.append(c)
                    continue

                # 持久化候选
                series_id = f"series-{uuid.uuid4().hex[:12]}"
                existing_candidate = conn.execute(
                    "SELECT id FROM series WHERE name = ? AND status = 'candidate'",
                    (c["name"],)
                ).fetchone()

                if existing_candidate:
                    conn.execute(
                        "UPDATE series SET description = ?, member_ids = ?, updated_at = ? WHERE id = ?",
                        (c.get("description", ""), json.dumps(mids), now_ts, existing_candidate["id"]),
                    )
                    c["_persisted_id"] = existing_candidate["id"]
                else:
                    conn.execute(
                        "INSERT INTO series (id, name, description, member_ids, status, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, 'candidate', ?, ?)",
                        (series_id, c.get("name", ""), c.get("description", ""), json.dumps(mids), now_ts, now_ts),
                    )
                    c["_persisted_id"] = series_id
                persisted.append(c)

        return {
            "series": persisted,
            "duplicates_skipped": len(skipped_dupes),
            "duplicates": skipped_dupes if skipped_dupes else [],
        }

    except (json.JSONDecodeError, Exception) as e:
        logger.exception("Stage2 discovery failed")
        return {"message": f"阶段2失败: {str(e)[:200]}", "series": []}


# ══════════════════════════════════════════════════
# 按主题发现
# ══════════════════════════════════════════════════

@router.post("/series/discover/by-topic")
def discover_by_topic(data: dict):
    """按用户输入的主题发现相关专题。
    
    Expects: {topic: "伊朗核问题"}
    流程：SQL 关键字匹配 → 缩小候选池 → AI 聚类 → 去重 → 返回
    """
    init_db()
    topic = data.get("topic", "").strip()
    if not topic:
        return {"message": "请输入主题关键词", "series": []}

    # 拆分关键词用于 SQL LIKE 匹配
    # 中文无空格：按字符级拆分为 OR 匹配（如"美国历史" → 匹配含"美国"或"历史"的内容）
    keywords = [kw.strip() for kw in topic.split() if len(kw.strip()) >= 1]
    if len(keywords) == 1 and not keywords[0].isascii():
        # Chinese text without spaces — generate bigrams for flexible matching
        chars = keywords[0]
        keywords = []
        for i in range(len(chars) - 1):
            bigram = chars[i:i+2]
            if bigram not in keywords:
                keywords.append(bigram)
        if not keywords:
            keywords = [chars]  # fallback: single character
    if not keywords:
        return {"message": "关键词无效", "series": []}

    with connect() as conn:
        # 构建动态 LIKE 条件（OR 连接：匹配任一关键词即可）
        conditions = []
        params = []
        for kw in keywords:
            like = f"%{kw}%"
            conditions.append("(title LIKE ? OR overview LIKE ?)")
            params.extend([like, like])
        where = " OR ".join(conditions)

        event_rows = conn.execute(
            f"SELECT id, title, overview FROM events "
            f"WHERE overview IS NOT NULL AND overview != '' AND status != 'error' AND ({where}) "
            f"ORDER BY created_at DESC LIMIT 30",
            params,
        ).fetchall()

    if len(event_rows) < 2:
        return {"message": f"与「{topic}」相关的内容不足 2 条", "series": []}

    # 直接精细发现（候选池已缩到 ≤30 条）
    events_text = ""
    for ev in event_rows:
        ov = ev["overview"] or ""
        events_text += f"\n### 事件ID: {ev['id']}\n标题: {ev['title']}\n概述: {ov}\n"

    prompt = f"""你是知识专题策展人。用户对「{topic}」主题感兴趣，请在以下相关内容中聚类成 1-3 个有意义的专题系列。

事件列表：
{events_text}

要求：
- 每个专题需包含至少 2 条事件
- 为每个专题生成简洁的名称（≤20字）和一句话描述（≤80字）
- member_ids 必须使用上面给出的真实"事件ID"值
- 一条内容可以属于多个专题
- 输出 JSON 数组，格式：[{{"name": "...", "description": "...", "member_ids": ["真实的event_id", ...], "rationale": "为什么这些内容构成一个专题"}}]
- 直接输出 JSON，不要 Markdown 包裹"""

    messages = [
        {"role": "system", "content": "你是知识专题策展人。输出纯 JSON 数组，每个元素包含 name/description/member_ids/rationale。"},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = _call_ai_chat(messages, temperature=0.4, max_tokens=4096, timeout=120,
                                  response_format={"type": "json_object"},
                                  module="series", task="discover_by_topic")
        if not raw:
            return {"message": "AI 未返回结果", "series": []}

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n```$", "", raw)

        candidates = json.loads(raw)
        if not isinstance(candidates, list):
            return {"message": "AI 返回格式异常", "series": []}

        member_id_set = set()
        for c in candidates:
            for mid in c.get("member_ids", []):
                # Strip brackets that AI may inadvertently copy
                mid = mid.strip().lstrip("[").rstrip("]")
                member_id_set.add(mid)
            # Rewrite cleaned IDs back
            c["member_ids"] = [mid.strip().lstrip("[").rstrip("]") for mid in c.get("member_ids", [])]

        persisted = []
        skipped_dupes = []
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with connect() as conn:
            title_map = {}
            if member_id_set:
                placeholders = ",".join(["?" for _ in member_id_set])
                title_rows = conn.execute(
                    f"SELECT id, title FROM events WHERE id IN ({placeholders})",
                    list(member_id_set),
                ).fetchall()
                title_map = {r["id"]: r["title"] for r in title_rows}

            for c in candidates:
                mids = c.get("member_ids", [])
                c["member_titles"] = [title_map.get(mid, "(已删除)") for mid in mids]

                is_dup, existing = _find_duplicate(conn, c.get("name", ""), mids)
                if is_dup:
                    c["_duplicate_of"] = {
                        "id": existing["id"],
                        "name": existing["name"],
                        "status": existing["status"],
                    }
                    skipped_dupes.append(c)
                    continue

                series_id = f"series-{uuid.uuid4().hex[:12]}"
                existing_candidate = conn.execute(
                    "SELECT id FROM series WHERE name = ? AND status = 'candidate'",
                    (c["name"],)
                ).fetchone()

                if existing_candidate:
                    conn.execute(
                        "UPDATE series SET description = ?, member_ids = ?, updated_at = ? WHERE id = ?",
                        (c.get("description", ""), json.dumps(mids), now_ts, existing_candidate["id"]),
                    )
                    c["_persisted_id"] = existing_candidate["id"]
                else:
                    conn.execute(
                        "INSERT INTO series (id, name, description, member_ids, status, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, 'candidate', ?, ?)",
                        (series_id, c.get("name", ""), c.get("description", ""), json.dumps(mids), now_ts, now_ts),
                    )
                    c["_persisted_id"] = series_id
                persisted.append(c)

        return {
            "series": persisted,
            "duplicates_skipped": len(skipped_dupes),
            "duplicates": skipped_dupes if skipped_dupes else [],
            "matched_events": len(event_rows),
        }

    except (json.JSONDecodeError, Exception) as e:
        logger.exception("By-topic discovery failed")
        return {"message": f"按主题发现失败: {str(e)[:200]}", "series": []}


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
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name, description, member_ids FROM series WHERE id = ?",
            (series_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")

        try:
            member_ids = json.loads(row["member_ids"])
        except (json.JSONDecodeError, TypeError):
            member_ids = []

        if not member_ids:
            raise HTTPException(status_code=400, detail="专题无成员，无法扩充")

        # ── 检查缓存：member_ids 未变则直接返回 ──
        cached = conn.execute(
            "SELECT scanned_count, recommendations_json FROM series_scan_cache WHERE series_id = ?",
            (series_id,),
        ).fetchone()
        if cached:
            try:
                cached_recs = json.loads(cached["recommendations_json"])
                return {
                    "recommendations": cached_recs,
                    "scanned": cached["scanned_count"],
                    "cached": True,
                }
            except json.JSONDecodeError:
                pass  # corrupt cache → re-scan

        # 取成员标题+概述摘要（控制上下文长度）
        placeholders = ",".join(["?" for _ in member_ids])
        member_rows = conn.execute(
            f"SELECT title, overview FROM events WHERE id IN ({placeholders})",
            member_ids,
        ).fetchall()

        # 取不在本专题的有概述事件（最近100条）
        non_member_rows = conn.execute(
            "SELECT id, title, overview FROM events "
            "WHERE overview IS NOT NULL AND overview != '' AND status != 'error' "
            f"AND id NOT IN ({placeholders}) "
            "ORDER BY created_at DESC LIMIT 100",
            member_ids,
        ).fetchall()

    if not non_member_rows:
        return {"message": "暂无可扩充的新内容", "recommendations": []}

    # 构建专题上下文
    context_text = f"专题名称：{row['name']}\n专题简介：{row['description']}\n\n当前成员概述：\n"
    for i, ev in enumerate(member_rows):
        ov = (ev["overview"] or "")[:200]  # 摘要限制200字
        context_text += f"\n[{i + 1}] {ev['title']}\n{ov}\n"

    candidates_text = ""
    for ev in non_member_rows:
        ov = ev["overview"] or ""
        candidates_text += f"\n### 候选ID: {ev['id']}\n标题: {ev['title']}\n概述: {ov}\n"

    prompt = f"""你是知识专题策展人。请判断以下新内容是否应加入现有专题。

{context_text}

候选内容：
{candidates_text}

要求：
- 逐条判断每条候选是否应加入该专题
- 加入标准：与专题主题相关、能补充新视角或信息、不重复已有内容
- 输出 JSON 数组，仅包含应加入的条目：[{{"event_id": "真实的候选ID", "reason": "一句话理由"}}]
- 如果不应该加入任何，输出空数组 []
- 最多推荐 8 条
- 直接输出 JSON，不要 Markdown 包裹"""

    messages = [
        {"role": "system", "content": "你是知识专题策展人。判断内容是否应加入专题，输出纯 JSON 数组。"},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = _call_ai_chat(messages, temperature=0.2, max_tokens=2048, timeout=120,
                                  response_format={"type": "json_object"},
                                  module="series", task="expand")
        if not raw:
            return {"message": "AI 未返回结果", "recommendations": []}

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n```$", "", raw)

        recommendations = json.loads(raw)
        if not isinstance(recommendations, list):
            return {"message": "AI 返回格式异常", "recommendations": []}

        # 解析标题
        rec_ids = [r.get("event_id", "") for r in recommendations if r.get("event_id")]
        title_map = {}
        if rec_ids:
            with connect() as conn:
                placeholders2 = ",".join(["?" for _ in rec_ids])
                title_rows = conn.execute(
                    f"SELECT id, title FROM events WHERE id IN ({placeholders2})",
                    rec_ids,
                ).fetchall()
                title_map = {r2["id"]: r2["title"] for r2 in title_rows}

        for r in recommendations:
            r["title"] = title_map.get(r.get("event_id", ""), "(已删除)")

        # 保存到缓存
        try:
            conn.execute(
                "INSERT OR REPLACE INTO series_scan_cache (series_id, scanned_count, recommendations_json, scanned_at) VALUES (?, ?, ?, datetime('now'))",
                (series_id, len(non_member_rows), json.dumps(recommendations, ensure_ascii=False)),
            )
            conn.commit()
        except Exception:
            pass  # cache write failure is non-fatal

        # 将推荐结果持久化到 suggested_series_json（与“待确认”打通）
        # 新格式: [{"series_id": "...", "reason": "..."}]  — 带理由
        if rec_ids:
            # 构建 event_id → reason 映射
            reason_map = {r.get("event_id", ""): r.get("reason", "") for r in recommendations}
            try:
                for eid in rec_ids:
                    current = conn.execute(
                        "SELECT suggested_series_json FROM events WHERE id = ?", (eid,)
                    ).fetchone()
                    entries = []
                    if current and current["suggested_series_json"]:
                        try:
                            raw = json.loads(current["suggested_series_json"])
                            # 兼容旧格式（纯ID数组）
                            if raw and isinstance(raw[0], str):
                                entries = [{"series_id": s, "reason": ""} for s in raw]
                            else:
                                entries = raw
                        except (json.JSONDecodeError, TypeError):
                            entries = []
                    # 更新或追加（已有同系列条目则更新理由）
                    updated = False
                    for e in entries:
                        if e.get("series_id") == series_id:
                            e["reason"] = reason_map.get(eid, "")
                            updated = True
                            break
                    if not updated:
                        entries.append({"series_id": series_id, "reason": reason_map.get(eid, "")})
                    conn.execute(
                        "UPDATE events SET suggested_series_json = ? WHERE id = ?",
                        (json.dumps(entries), eid),
                    )
                conn.commit()
            except Exception:
                pass  # suggestion write failure is non-fatal

        return {"recommendations": recommendations, "scanned": len(non_member_rows)}

    except (json.JSONDecodeError, Exception) as e:
        logger.exception("Expand series failed")
        return {"message": f"扩充失败: {str(e)[:200]}", "recommendations": []}


# ══════════════════════════════════════════════════
# 自由组题 — AI 建议名称
# ══════════════════════════════════════════════════

@router.post("/series/suggest-name")
def suggest_series_name(data: SeriesNameRequest):
    """自由组题：根据用户选定的文档，AI 建议专题名称和副标题。

    Expects: {member_ids: [...], current_name: "用户起的临时名（可选）"}
    Returns: {suggested_name: "AI建议标题", suggested_description: "AI建议副标题"}
    """
    init_db()
    member_ids = data.member_ids
    current_name = data.current_name.strip()

    with connect() as conn:
        placeholders = ",".join(["?" for _ in member_ids])
        event_rows = conn.execute(
            f"SELECT id, title, overview, ai_summary FROM events WHERE id IN ({placeholders})",
            member_ids,
        ).fetchall()

    if len(event_rows) < 2:
        return {"message": "有效文档不足 2 条", "suggested_name": "", "suggested_description": ""}

    docs_text = ""
    for i, ev in enumerate(event_rows):
        ov = ev["overview"] or ev["ai_summary"] or ""
        docs_text += f"\n### [{i + 1}] {ev['title']}\n{ov}\n"

    current_hint = ""
    if current_name:
        current_hint = f'\n用户暂定标题：「{current_name}」（你可以在此基础上优化，也可以提出完全不同的名称）'

    prompt = f"""你是知识专题策展人。请根据以下用户选定的文档内容，为这个专题建议一个精准的名称和副标题。

文档内容：
{docs_text}
{current_hint}

要求：
- 标题（name）：≤20字，精确概括这些文档的共同主题和内在联系
- 副标题（description）：≤80字，说明这个专题覆盖什么核心问题和分析范围
- 输出 JSON：{{"name": "...", "description": "..."}}
- 直接输出 JSON，不要 Markdown 包裹"""

    messages = [
        {"role": "system", "content": "你是知识专题策展人。根据文档内容建议专题名称和副标题。输出纯 JSON 对象。"},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = _call_ai_chat(messages, temperature=0.4, max_tokens=512, timeout=60,
                                  response_format={"type": "json_object"},
                                  module="series", task="suggest_name")
        if not raw:
            return {"message": "AI 未返回结果", "suggested_name": "", "suggested_description": ""}

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n```$", "", raw)

        result = json.loads(raw)
        return {
            "suggested_name": result.get("name", "").strip(),
            "suggested_description": result.get("description", "").strip(),
        }

    except (json.JSONDecodeError, Exception) as e:
        logger.exception("Suggest name failed")
        return {"message": f"AI 结果解析失败: {str(e)[:200]}", "suggested_name": "", "suggested_description": ""}


@router.post("/series")
def create_series(data: SeriesCreateRequest):
    """Create a new series from discovered candidates.

    If a candidate with the same name exists, upgrades it to 'published' (upsert).
    """
    return series_service.create_series(data, connect_fn=connect, init_db_fn=init_db)


@router.delete("/series/{series_id}")
def delete_series(series_id: SafeIdentifier):
    """Delete a series."""
    return series_service.delete_series(
        series_id, connect_fn=connect, init_db_fn=init_db
    )


@router.put("/series/{series_id}")
def update_series(series_id: SafeIdentifier, data: dict):
    """Update series metadata (name, description, status)."""
    return series_service.update_series(
        series_id, data, connect_fn=connect, init_db_fn=init_db
    )


@router.post("/series/merge")
def merge_series(data: SeriesMergeRequest):
    """Merge a source candidate into a target series.

    Expects: {source_id: str, target_id: str}
    - Moves source's member_ids into target (dedup)
    - Deletes the source candidate
    - Returns updated target
    """
    return series_service.merge_series(data, connect_fn=connect, init_db_fn=init_db)


# ══════════════════════════════════════════════════
# 专题详情 & 成员
# ══════════════════════════════════════════════════

@router.get("/series/{series_id}")
def get_series_detail(series_id: SafeIdentifier):
    """Return full series detail: metadata + enriched member events."""
    return series_service.get_series_detail(
        series_id, connect_fn=connect, init_db_fn=init_db
    )


# ══════════════════════════════════════════════════
# AI 导言、速览、深度分析
# ══════════════════════════════════════════════════

@router.put("/series/{series_id}/intro")
def generate_series_intro(series_id: SafeIdentifier):
    """AI generates a narrative intro connecting all member overviews."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name, description, member_ids FROM series WHERE id = ?",
            (series_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")

        try:
            member_ids = json.loads(row["member_ids"])
        except (json.JSONDecodeError, TypeError):
            member_ids = []

        if len(member_ids) < 2:
            raise HTTPException(status_code=400, detail="专题成员不足，无法生成导言")

        placeholders = ",".join(["?" for _ in member_ids])
        event_rows = conn.execute(
            f"SELECT title, overview FROM events WHERE id IN ({placeholders})",
            member_ids,
        ).fetchall()

    members_text = ""
    for i, ev in enumerate(event_rows):
        members_text += f"\n### [{i + 1}] {ev['title']}\n{ev['overview']}\n"

    prompt = f"""你是知识专题策展人。请为以下专题撰写一段 300-500 字的导言。

专题名称：{row['name']}
专题简介：{row['description']}

成员内容概述：
{members_text}

要求：
- 用叙事语言而非列表，像博物馆展览的引导词
- 告诉读者这个专题在回答什么核心问题
- 简要介绍各篇内容在专题中的角色和逻辑关系
- 给读者一个合理的阅读顺序建议
- 文末附 1-2 句邀请读者深入探索的话
- 引用用 [N] 标注
- 直接输出 Markdown，不要前置说明"""

    messages = [
        {"role": "system", "content": "你是知识专题策展人。导言用叙事语言，像博物馆引导词，告诉读者这个专题回答什么核心问题及各篇逻辑关系。"},
        {"role": "user", "content": prompt},
    ]

    intro = _call_ai_chat(messages, temperature=0.5, max_tokens=1024, timeout=120,
                               module="series", task="intro")
    if not intro:
        raise HTTPException(status_code=500, detail="AI 导言生成失败")

    now_ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
    with connect() as conn:
        conn.execute(
            "UPDATE series SET intro = ?, updated_at = ? WHERE id = ?",
            (intro.strip(), now_ts, series_id),
        )

    return {"intro": intro.strip()}


@router.put("/series/{series_id}/summary")
def generate_series_summary(series_id: SafeIdentifier):
    """AI generates a structured summary of the series — thesis, insights, logic chain, entities, open questions."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name, description, member_ids FROM series WHERE id = ?",
            (series_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")

        try:
            member_ids = json.loads(row["member_ids"])
        except (json.JSONDecodeError, TypeError):
            member_ids = []

        if len(member_ids) < 2:
            raise HTTPException(status_code=400, detail="专题成员不足，无法生成总结")

        placeholders = ",".join(["?" for _ in member_ids])
        event_rows = conn.execute(
            f"SELECT title, overview FROM events WHERE id IN ({placeholders})",
            member_ids,
        ).fetchall()

    members_text = ""
    for i, ev in enumerate(event_rows):
        members_text += f"\n### [{i + 1}] {ev['title']}\n{ev['overview']}\n"

    prompt = f"""你是知识专题分析师。请为以下专题生成一份详尽的结构化速览总结。

专题名称：{row['name']}
专题简介：{row['description']}

**重要**：专题简介中列举的分析维度（如历史、宗教、政治、经济等），必须在「关键洞察」中逐一覆盖。每条洞察明确标注对应哪个维度。

成员内容概述：
{members_text}

请严格按以下 Markdown 格式输出，每个部分都要充实：

## 核心论点
（一句话，不超过 60 字，概括这个专题在回答什么核心问题）

## 关键洞察
（从成员 overview 中提炼 4-6 条核心洞察。按专题简介承诺的维度组织，每条格式：「维度 · 视角标签：核心观点」+ 1-2 句支撑论据。标注依据来源 [N]）
- **历史 · 殖民创伤**：伊朗对西方的仇恨根植于近代被英俄瓜分的屈辱史。[3]
  论据：1907年英俄条约直接瓜分伊朗主权，伊朗连参与谈判的资格都没有。
- **宗教 · 什叶派身份**：伊朗为对抗逊尼派主动改宗，强化了独特的民族认同。[4]
  论据：...

## 关键数据/时间节点
（从内容中提取的具体数字、年份、关键事件，按时间或重要性排列）
- 1907 — 英俄条约瓜分伊朗主权
- 16% vs 84% — 巴列维时期石油利润分配比例

## 逻辑脉络
（揭示成员之间的逻辑关系。用分组说明哪些是因果、哪些是对比、哪些是递进）
1. [1] 标题简述 — 作用：奠定历史背景
2. [2] 标题简述 — 作用：揭示转折点
   ↳ 对比 [3]：从另一视角提供对照

## 视角分歧
（如果成员之间对同一问题有不同的立场、解释或侧重，标注出来）
- 分歧点：成员 [A] 认为...，而成员 [B] 强调...

## 关键人物/实体
（专题反复提及的核心人物、组织、国家，每项附简要角色说明）
- 实体名 — 角色与重要性

## 待探索问题
（基于现有内容自然延伸但尚未覆盖的问题，3-5 条）
- 问题一

直接输出 Markdown，不要前置说明。"""

    messages = [
        {"role": "system", "content": "你是知识专题分析师。输出结构化的 Markdown 总结。关键洞察必须按专题简介承诺的分析维度逐一覆盖，每条标注维度标签（如 历史·、宗教·、政治·、经济·）。"},
        {"role": "user", "content": prompt},
    ]

    summary = _call_ai_chat(messages, temperature=0.3, max_tokens=3072, timeout=120,
                                 module="series", task="summary")
    if not summary:
        raise HTTPException(status_code=500, detail="AI 总结生成失败")

    now_ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
    with connect() as conn:
        conn.execute(
            "UPDATE series SET summary = ?, updated_at = ? WHERE id = ?",
            (summary.strip(), now_ts, series_id),
        )

    return {"summary": summary.strip()}


@router.put("/series/{series_id}/paper")
def generate_series_paper(series_id: SafeIdentifier):
    """AI generates a paper/lecture-style deep analysis of the series.
    Narrative arc: background → analysis → climax (core findings) → conclusion/outlook.
    Paragraph-style writing with thesis-evidence structure and lecture rhythm."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name, description, member_ids FROM series WHERE id = ?",
            (series_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")

        try:
            member_ids = json.loads(row["member_ids"])
        except (json.JSONDecodeError, TypeError):
            member_ids = []

        if len(member_ids) < 2:
            raise HTTPException(status_code=400, detail="专题成员不足，无法生成论文")

        placeholders = ",".join(["?" for _ in member_ids])
        event_rows = conn.execute(
            f"SELECT title, overview FROM events WHERE id IN ({placeholders})",
            member_ids,
        ).fetchall()

    members_text = ""
    for i, ev in enumerate(event_rows):
        members_text += f"\n### [{i + 1}] {ev['title']}\n{ev['overview']}\n"

    prompt = f"""你是资深国际关系研究学者。请为以下专题撰写一篇**论文式深度分析**。

专题名称：{row['name']}
专题简介：{row['description']}

成员内容概述：
{members_text}

---

**写作要求：**

1. **叙事弧线**：这是一篇有起承转合的论文/演讲稿，不是要点列表
   - 开头（背景/问题）：为什么这个问题值得关注？核心矛盾是什么？
   - 发展（分析论证）：逐层深入，每段有论点+论据+过渡
   - 高潮（核心发现）：跨维度提炼最关键的判断，这是全文的思想顶点
   - 结尾（结论与展望）：未来走向是什么？留下的思考是什么？

2. **论点-论据结构**：每个观点必须有具体事件/数据支撑，引用用 [N] 标注
   - 不要空泛概括——要引具体史实、人物、时间点
   - 论据不是重复概述，而是用来推进论证

3. **段落式写作**：连贯段落，有逻辑连接词和过渡句
   - 每段说清楚一件事，段落间有"然而""更进一步""这背后是""换句话说"等过渡
   - 可以设问，可以强调

4. **讲稿节奏**：
   - 可以有"关键在于""更关键的是""这揭示了一个更深层的问题"等引导语
   - 结尾有力度，像演讲的收束，给读者留下思考余味

**格式要求：**
- 输出纯 Markdown，不要前置说明
- 全文 1500-2500 字
- 每段之间空一行
- 引用用 [N] 标注
- 可以用小标题分段（不超过 5 个）"""

    messages = [
        {"role": "system", "content": "你是资深国际关系研究学者。请撰写论文式深度分析：叙事弧线完整（开头→发展→高潮→结尾），论点-论据结构，连贯段落式写作，讲稿节奏。每个观点引用具体事件/数据并标注 [N]。输出纯 Markdown，全文 1500-2500 字。"},
        {"role": "user", "content": prompt},
    ]

    paper = _call_ai_chat(messages, temperature=0.5, max_tokens=4096, timeout=180,
                               module="series", task="paper")
    if not paper:
        raise HTTPException(status_code=500, detail="AI 论文生成失败")

    now_ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
    with connect() as conn:
        conn.execute(
            "UPDATE series SET paper = ?, updated_at = ? WHERE id = ?",
            (paper.strip(), now_ts, series_id),
        )

    return {"paper": paper.strip()}


# ══════════════════════════════════════════════════
# 排序、建议审核、成员管理
# ══════════════════════════════════════════════════

@router.put("/series/{series_id}/sort")
def reorder_series(series_id: SafeIdentifier, data: SeriesOrderRequest):
    """Update member order via drag-and-drop."""
    return series_service.reorder_series(
        series_id, data, connect_fn=connect, init_db_fn=init_db
    )


@router.get("/series/{series_id}/suggestions")
def get_series_suggestions(series_id: SafeIdentifier):
    """Get pending member suggestions for a series."""
    return series_service.get_series_suggestions(
        series_id, connect_fn=connect, init_db_fn=init_db
    )


@router.post("/series/{series_id}/members")
def add_series_members(series_id: SafeIdentifier, data: SeriesMembersRequest):
    """Add one or more event_ids to a series (non-destructive append)."""
    return series_service.add_series_members(
        series_id, data, connect_fn=connect, init_db_fn=init_db
    )


# ══════════════════════════════════════════════════
# 即时 AI 匹配
# ══════════════════════════════════════════════════

def auto_suggest_series(event_id: str) -> None:
    """After ingest completes, AI checks if this event belongs to any existing published series.

    Stores suggestions in events.suggested_series_json as a JSON array of series IDs.
    Non-blocking — failures are logged but not raised.
    """
    from ..ai_client import chat

    try:
        with connect() as conn:
            ev = conn.execute(
                "SELECT id, title, overview, topic FROM events WHERE id = ?", (event_id,)
            ).fetchone()
            if not ev or not ev["overview"]:
                return

            # Get all published series
            series_rows = conn.execute(
                "SELECT id, name, description FROM series WHERE status = 'published'"
            ).fetchall()

        if not series_rows:
            return

        series_text = ""
        id_map = {}
        for s in series_rows:
            series_text += f"\n- **{s['name']}** (id: {s['id']}): {s['description']}"
            id_map[s["id"]] = s["name"]

        prompt = f"""判断以下新内容是否属于现有的知识专题。

新内容：
标题：{ev['title']}
概述：{ev['overview']}
主题：{ev['topic'] or '未分类'}

现有专题列表：
{series_text}

请判断这条内容是否应该归入以上某个专题。一条内容可以同时属于多个专题。
返回 JSON 数组，每项包含 series_id 和 reason（≤15字，为何匹配）。
格式：[{{"series_id": "xxx", "reason": "理由"}}] 或 []
直接输出 JSON，不要说明。"""

        messages = [
            {"role": "system", "content": "你是知识分类助手。判断内容是否属于现有专题，输出纯 JSON 数组，可为空。"},
            {"role": "user", "content": prompt},
        ]

        raw = chat(messages, temperature=0.1, max_tokens=512, timeout=30,
                   module="series", task="auto_suggest")
        if not raw:
            return

        raw = raw.strip().strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:]
        suggested = json.loads(raw)

        if isinstance(suggested, list) and suggested:
            with connect() as conn:
                conn.execute(
                    "UPDATE events SET suggested_series_json = ? WHERE id = ?",
                    (json.dumps(suggested), event_id),
                )

    except Exception:
        logger.warning("auto_suggest_series failed for %s", event_id, exc_info=True)
