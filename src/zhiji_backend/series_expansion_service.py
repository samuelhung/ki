"""AI workflows for expanding and naming series."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, Protocol

from fastapi import HTTPException

from .db import connect, init_db

type ConnectFn = Callable[[], AbstractContextManager[sqlite3.Connection]]
type InitDbFn = Callable[[], None]
type ChatFn = Callable[..., str | None]

logger = logging.getLogger("zhiji_backend.routes.series_routes")


class SeriesNameData(Protocol):
    member_ids: list[str]
    current_name: str


def expand_series(
    series_id: str,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
    chat_fn: ChatFn,
) -> dict[str, Any]:
    """Find new members for an existing series."""
    init_db_fn()
    with connect_fn() as conn:
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
                pass

        placeholders = ",".join(["?" for _ in member_ids])
        member_rows = conn.execute(
            f"SELECT title, overview FROM events WHERE id IN ({placeholders})",
            member_ids,
        ).fetchall()

        non_member_rows = conn.execute(
            "SELECT id, title, overview FROM events "
            "WHERE overview IS NOT NULL AND overview != '' AND status != 'error' "
            f"AND id NOT IN ({placeholders}) "
            "ORDER BY created_at DESC LIMIT 100",
            member_ids,
        ).fetchall()

    if not non_member_rows:
        return {"message": "暂无可扩充的新内容", "recommendations": []}

    context_text = (
        f"专题名称：{row['name']}\n专题简介：{row['description']}\n\n当前成员概述：\n"
    )
    for i, ev in enumerate(member_rows):
        ov = (ev["overview"] or "")[:200]
        context_text += f"\n[{i + 1}] {ev['title']}\n{ov}\n"

    candidates_text = ""
    for ev in non_member_rows:
        ov = ev["overview"] or ""
        candidates_text += (
            f"\n### 候选ID: {ev['id']}\n标题: {ev['title']}\n概述: {ov}\n"
        )

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
        {
            "role": "system",
            "content": "你是知识专题策展人。判断内容是否应加入专题，输出纯 JSON 数组。",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        raw = chat_fn(
            messages,
            temperature=0.2,
            max_tokens=2048,
            timeout=120,
            response_format={"type": "json_object"},
            module="series",
            task="expand",
        )
        if not raw:
            return {"message": "AI 未返回结果", "recommendations": []}

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n```$", "", raw)

        recommendations = json.loads(raw)
        if not isinstance(recommendations, list):
            return {"message": "AI 返回格式异常", "recommendations": []}

        rec_ids = [
            recommendation.get("event_id", "")
            for recommendation in recommendations
            if recommendation.get("event_id")
        ]
        title_map = {}
        if rec_ids:
            with connect_fn() as conn:
                placeholders2 = ",".join(["?" for _ in rec_ids])
                title_rows = conn.execute(
                    f"SELECT id, title FROM events WHERE id IN ({placeholders2})",
                    rec_ids,
                ).fetchall()
                title_map = {
                    title_row["id"]: title_row["title"] for title_row in title_rows
                }

        for recommendation in recommendations:
            recommendation["title"] = title_map.get(
                recommendation.get("event_id", ""), "(已删除)"
            )

        try:
            conn.execute(
                "INSERT OR REPLACE INTO series_scan_cache (series_id, scanned_count, recommendations_json, scanned_at) VALUES (?, ?, ?, datetime('now'))",
                (
                    series_id,
                    len(non_member_rows),
                    json.dumps(recommendations, ensure_ascii=False),
                ),
            )
            conn.commit()
        except Exception:
            pass

        if rec_ids:
            reason_map = {
                recommendation.get("event_id", ""): recommendation.get("reason", "")
                for recommendation in recommendations
            }
            try:
                for event_id in rec_ids:
                    current = conn.execute(
                        "SELECT suggested_series_json FROM events WHERE id = ?",
                        (event_id,),
                    ).fetchone()
                    entries = []
                    if current and current["suggested_series_json"]:
                        try:
                            stored = json.loads(current["suggested_series_json"])
                            if stored and isinstance(stored[0], str):
                                entries = [
                                    {"series_id": stored_id, "reason": ""}
                                    for stored_id in stored
                                ]
                            else:
                                entries = stored
                        except (json.JSONDecodeError, TypeError):
                            entries = []
                    updated = False
                    for entry in entries:
                        if entry.get("series_id") == series_id:
                            entry["reason"] = reason_map.get(event_id, "")
                            updated = True
                            break
                    if not updated:
                        entries.append(
                            {
                                "series_id": series_id,
                                "reason": reason_map.get(event_id, ""),
                            }
                        )
                    conn.execute(
                        "UPDATE events SET suggested_series_json = ? WHERE id = ?",
                        (json.dumps(entries), event_id),
                    )
                conn.commit()
            except Exception:
                pass

        return {"recommendations": recommendations, "scanned": len(non_member_rows)}

    except (json.JSONDecodeError, Exception) as error:
        logger.exception("Expand series failed")
        return {
            "message": f"扩充失败: {str(error)[:200]}",
            "recommendations": [],
        }


def suggest_series_name(
    data: SeriesNameData,
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
    chat_fn: ChatFn,
) -> dict[str, Any]:
    """Suggest a series name and description from selected documents."""
    init_db_fn()
    member_ids = data.member_ids
    current_name = data.current_name.strip()

    with connect_fn() as conn:
        placeholders = ",".join(["?" for _ in member_ids])
        event_rows = conn.execute(
            f"SELECT id, title, overview, ai_summary FROM events WHERE id IN ({placeholders})",
            member_ids,
        ).fetchall()

    if len(event_rows) < 2:
        return {
            "message": "有效文档不足 2 条",
            "suggested_name": "",
            "suggested_description": "",
        }

    docs_text = ""
    for i, ev in enumerate(event_rows):
        ov = ev["overview"] or ev["ai_summary"] or ""
        docs_text += f"\n### [{i + 1}] {ev['title']}\n{ov}\n"

    current_hint = ""
    if current_name:
        current_hint = f"\n用户暂定标题：「{current_name}」（你可以在此基础上优化，也可以提出完全不同的名称）"

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
        {
            "role": "system",
            "content": "你是知识专题策展人。根据文档内容建议专题名称和副标题。输出纯 JSON 对象。",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        raw = chat_fn(
            messages,
            temperature=0.4,
            max_tokens=512,
            timeout=60,
            response_format={"type": "json_object"},
            module="series",
            task="suggest_name",
        )
        if not raw:
            return {
                "message": "AI 未返回结果",
                "suggested_name": "",
                "suggested_description": "",
            }

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n```$", "", raw)

        result = json.loads(raw)
        return {
            "suggested_name": result.get("name", "").strip(),
            "suggested_description": result.get("description", "").strip(),
        }

    except (json.JSONDecodeError, Exception) as error:
        logger.exception("Suggest name failed")
        return {
            "message": f"AI 结果解析失败: {str(error)[:200]}",
            "suggested_name": "",
            "suggested_description": "",
        }
