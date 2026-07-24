"""AI workflows for general and two-stage series discovery."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, Protocol

from .db import connect, init_db
from .series_candidate_service import persist_discovered_candidates

type ConnectFn = Callable[[], AbstractContextManager[sqlite3.Connection]]
type InitDbFn = Callable[[], None]
type ChatFn = Callable[..., str | None]

logger = logging.getLogger(__name__)


class SeriesDiscoveryData(Protocol):
    event_ids: list[str]
    name_hint: str


def discover_series(
    *, connect_fn: ConnectFn = connect, init_db_fn: InitDbFn = init_db, chat_fn: ChatFn
) -> dict[str, Any]:
    """Discover and persist candidate series from recent event overviews."""
    init_db_fn()
    with connect_fn() as conn:
        all_rows = conn.execute(
            "SELECT id, title, overview FROM events "
            "WHERE overview IS NOT NULL AND overview != '' AND status != 'error' "
            "ORDER BY created_at DESC LIMIT 60"
        ).fetchall()

        if len(all_rows) < 3:
            return {"message": "有概述的事件不足 3 条，无法发现专题", "series": []}

        used_ids = set()
        existing_series_rows = conn.execute(
            "SELECT member_ids FROM series WHERE status = 'published'"
        ).fetchall()
        for series_row in existing_series_rows:
            try:
                ids = json.loads(series_row["member_ids"])
                used_ids.update(ids)
            except (json.JSONDecodeError, TypeError):
                pass

        new_rows = [row for row in all_rows if row["id"] not in used_ids]
        if len(new_rows) < 3:
            new_rows = all_rows

        candidates_rows = conn.execute(
            "SELECT id, name, description, member_ids FROM series WHERE status = 'candidate'"
        ).fetchall()

    events_text = ""
    for ev in new_rows:
        ov = ev["overview"] or ""
        events_text += f"\n### 事件ID: {ev['id']}\n标题: {ev['title']}\n概述: {ov}\n"

    candidates_context = ""
    if candidates_rows:
        candidates_context = "\n## 已有候选专题（可确认/修改/舍弃）\n"
        for candidate in candidates_rows:
            try:
                mids = json.loads(candidate["member_ids"])
            except (json.JSONDecodeError, TypeError):
                mids = []
            candidates_context += (
                f"- **{candidate['name']}**（id: {candidate['id']}）: {candidate['description'] or ''}，"
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
        {
            "role": "system",
            "content": "你是知识专题策展人。输出纯 JSON 数组，每个元素包含 name/description/member_ids/rationale。",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        raw = chat_fn(
            messages,
            temperature=0.4,
            max_tokens=4096,
            timeout=120,
            response_format={"type": "json_object"},
            module="series",
            task="discover",
        )
        if not raw:
            return {"message": "AI 未返回结果", "series": []}

        candidates = _parse_json_array(raw)
        if candidates is None:
            return {"message": "AI 返回格式异常", "series": []}

        persisted, skipped_dupes, stale_cleaned = persist_discovered_candidates(
            candidates, connect_fn=connect_fn, clean_stale=True
        )
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


def discover_stage1(
    *, connect_fn: ConnectFn = connect, init_db_fn: InitDbFn = init_db, chat_fn: ChatFn
) -> dict[str, Any]:
    """Group all event titles into broad topic domains without persistence."""
    init_db_fn()
    with connect_fn() as conn:
        event_rows = conn.execute(
            "SELECT id, title FROM events "
            "WHERE overview IS NOT NULL AND overview != '' AND status != 'error' "
            "ORDER BY created_at DESC"
        ).fetchall()

    if len(event_rows) < 3:
        return {"message": "有概述的事件不足 3 条，无法发现专题", "groups": []}

    titles_text = ""
    for ev in event_rows:
        titles_text += f"- [{ev['id']}] {ev['title']}\n"

    with connect_fn() as conn:
        existing = conn.execute(
            "SELECT name FROM series WHERE status IN ('candidate', 'published')"
        ).fetchall()
    existing_names = (
        "\n".join([f"- {r['name']}" for r in existing]) if existing else "（无）"
    )

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
        {
            "role": "system",
            "content": "你是知识专题策展人。按主题领域对事件标题分组，输出纯 JSON 数组。",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        raw = chat_fn(
            messages,
            temperature=0.3,
            max_tokens=4096,
            timeout=120,
            response_format={"type": "json_object"},
            module="series",
            task="discover_stage1",
        )
        if not raw:
            return {"message": "AI 未返回结果", "groups": []}

        groups = _parse_json_array(raw)
        if groups is None:
            return {"message": "AI 返回格式异常", "groups": []}

        all_ids = set()
        for group in groups:
            for event_id in group.get("event_ids", []):
                event_id = event_id.strip().lstrip("[").rstrip("]")
                all_ids.add(event_id)
            group["event_ids"] = [
                event_id.strip().lstrip("[").rstrip("]")
                for event_id in group.get("event_ids", [])
            ]

        title_map = {}
        if all_ids:
            with connect_fn() as conn:
                placeholders = ",".join(["?" for _ in all_ids])
                rows = conn.execute(
                    f"SELECT id, title FROM events WHERE id IN ({placeholders})",
                    list(all_ids),
                ).fetchall()
                title_map = {row["id"]: row["title"] for row in rows}

        for group in groups:
            ids = group.get("event_ids", [])
            group["event_titles"] = [
                title_map.get(event_id, "(已删除)") for event_id in ids
            ]
            group["count"] = len(ids)

        return {"groups": groups, "total_events": len(event_rows)}

    except (json.JSONDecodeError, Exception) as e:
        logger.exception("Stage1 discovery failed")
        return {"message": f"阶段1失败: {str(e)[:200]}", "groups": []}


def discover_stage2(
    data: SeriesDiscoveryData,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
    chat_fn: ChatFn,
) -> dict[str, Any]:
    """Discover candidate series from a user-selected set of events."""
    init_db_fn()
    event_ids = data.event_ids
    name_hint = data.name_hint.strip()

    with connect_fn() as conn:
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

    hint_line = (
        f"\n领域提示：这些内容属于「{name_hint}」相关领域。\n" if name_hint else ""
    )

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
        {
            "role": "system",
            "content": "你是知识专题策展人。输出纯 JSON 数组，每个元素包含 name/description/member_ids/rationale。",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        raw = chat_fn(
            messages,
            temperature=0.4,
            max_tokens=4096,
            timeout=120,
            response_format={"type": "json_object"},
            module="series",
            task="discover_stage2",
        )
        if not raw:
            return {"message": "AI 未返回结果", "series": []}

        candidates = _parse_json_array(raw)
        if candidates is None:
            return {"message": "AI 返回格式异常", "series": []}

        for candidate in candidates:
            candidate["member_ids"] = [
                member_id.strip().lstrip("[").rstrip("]")
                for member_id in candidate.get("member_ids", [])
            ]

        persisted, skipped_dupes, _ = persist_discovered_candidates(
            candidates, connect_fn=connect_fn
        )
        return {
            "series": persisted,
            "duplicates_skipped": len(skipped_dupes),
            "duplicates": skipped_dupes if skipped_dupes else [],
        }

    except (json.JSONDecodeError, Exception) as e:
        logger.exception("Stage2 discovery failed")
        return {"message": f"阶段2失败: {str(e)[:200]}", "series": []}


def _parse_json_array(raw: str) -> list[dict[str, Any]] | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n```$", "", raw)
    value = json.loads(raw)
    return value if isinstance(value, list) else None
