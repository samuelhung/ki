"""Bidirectional matching between events and brainstorm questions."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

type ConnectFn = Callable[[], Any]
type ChatFn = Callable[..., str | None]
type ContemplateFn = Callable[[str], dict[str, object]]
type CallContemplateFn = Callable[[str], list[dict]]


logger = logging.getLogger("zhiji_backend.routes.brainstorm_routes")


def contemplate(
    request: Any,
    *,
    contemplate_event_to_questions_fn: ContemplateFn,
    contemplate_question_to_events_fn: ContemplateFn,
) -> dict[str, object]:
    if request.direction == "event_to_questions":
        return contemplate_event_to_questions_fn(request.entity_id)
    if request.direction == "question_to_events":
        return contemplate_question_to_events_fn(request.entity_id)
    return {
        "entity_id": request.entity_id,
        "suggestions": [],
        "error": "invalid direction",
    }


def get_linked_questions(event_id: str, *, connect_fn: ConnectFn) -> dict[str, object]:
    with connect_fn() as conn:
        rows = conn.execute(
            """SELECT bq.id, bq.question, bq.topic, bq.created_at
               FROM brainstorm_event_links bel
               JOIN brainstorm_questions bq ON bq.id = bel.question_id
               WHERE bel.event_id = ?
               ORDER BY bq.created_at DESC""",
            (event_id,),
        ).fetchall()
    return {
        "event_id": event_id,
        "linked_questions": [dict(r) for r in rows],
    }


def _contemplate_event_to_questions(
    event_id: str,
    *,
    connect_fn: ConnectFn,
    call_contemplate_deepseek_fn: CallContemplateFn,
) -> dict[str, object]:
    """Find which brainstorm questions an event might answer."""
    with connect_fn() as conn:
        event = conn.execute(
            "SELECT id, title, ai_summary, raw_summary FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
    if not event:
        return {"entity_id": event_id, "suggestions": [], "error": "事件不存在"}
    event_text = (event["ai_summary"] or "") or (event["raw_summary"] or "")
    if not event_text.strip():
        return {
            "entity_id": event_id,
            "suggestions": [],
            "error": "事件没有文本内容",
        }
    with connect_fn() as conn:
        linked_rows = conn.execute(
            "SELECT question_id FROM brainstorm_event_links WHERE event_id = ?",
            (event_id,),
        ).fetchall()
    linked_ids = {r["question_id"] for r in linked_rows}
    with connect_fn() as conn:
        cached_rows = conn.execute(
            "SELECT question_id, relevance, reason FROM brainstorm_contemplate_cache WHERE event_id = ?",
            (event_id,),
        ).fetchall()
    cached: dict[str, dict] = {
        r["question_id"]: {"relevance": r["relevance"], "reason": r["reason"]}
        for r in cached_rows
    }
    cached_ids = set(cached.keys())
    with connect_fn() as conn:
        rows = conn.execute(
            "SELECT id, question FROM brainstorm_questions WHERE status = 'open' ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    all_questions = [dict(r) for r in rows]
    candidates = [
        q
        for q in all_questions
        if q["id"] not in linked_ids and q["id"] not in cached_ids
    ]
    linked_suggestions = []
    for q in all_questions:
        if q["id"] in linked_ids:
            judgment = cached.get(q["id"])
            linked_suggestions.append(
                {
                    "question_id": q["id"],
                    "question_text": q["question"],
                    "relevance": judgment["relevance"] if judgment else "high",
                    "reason": judgment["reason"] if judgment else "已关联",
                    "link_status": "linked",
                }
            )
    cached_suggestions = []
    for q in all_questions:
        if q["id"] not in linked_ids and q["id"] in cached_ids:
            judgment = cached[q["id"]]
            cached_suggestions.append(
                {
                    "question_id": q["id"],
                    "question_text": q["question"],
                    "relevance": judgment["relevance"],
                    "reason": judgment["reason"] or "",
                    "link_status": "unlinked",
                }
            )
    new_suggestions: list[dict] = []
    if candidates:
        event_title = event["title"] or ""
        event_snippet = event_text[:3000] if len(event_text) > 3000 else event_text
        question_lines = []
        for i, q in enumerate(candidates):
            question_lines.append(f"[{i}] {q['question']}")
        prompt = (
            "你是一个内容匹配助手。以下是一篇文章，请判断它能回答下面哪些问题。\n"
            "对每个问题，判断是否可以基于文章内容回答：\n"
            "- 如果文章直接涉及该问题的主题，标为 high\n"
            "- 如果文章部分相关或可提供背景，标为 medium\n"
            "- 如果完全无关，标为 low\n"
            "注意：不要因为问题关键词看起来匹配就误判，必须基于文章内容的实质关联。\n"
            "只输出 JSON 数组，不要其他内容。格式：\n"
            '[{"index": 0, "relevance": "high", "reason": "一句话原因"}, ...]\n'
            "只输出 relevance 为 high 或 medium 的项，low 的跳过不输出。\n\n"
            f"文章标题：{event_title}\n"
            f"文章内容：\n{event_snippet}\n\n"
            f"待评估问题：\n" + "\n".join(question_lines)
        )
        matches = call_contemplate_deepseek_fn(prompt)
        matched_indices: set[int] = set()
        with connect_fn() as conn:
            for match in matches:
                idx = match.get("index")
                if idx is not None and 0 <= idx < len(candidates):
                    matched_indices.add(idx)
                    question = candidates[idx]
                    relevance = match.get("relevance", "medium")
                    reason = match.get("reason", "")
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (question["id"], event_id, relevance, reason),
                    )
                    new_suggestions.append(
                        {
                            "question_id": question["id"],
                            "question_text": question["question"],
                            "relevance": relevance,
                            "reason": reason,
                            "link_status": "unlinked",
                        }
                    )
            for i, question in enumerate(candidates):
                if i not in matched_indices:
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (question["id"], event_id, "low", ""),
                    )
                    new_suggestions.append(
                        {
                            "question_id": question["id"],
                            "question_text": question["question"],
                            "relevance": "low",
                            "reason": "",
                            "link_status": "unlinked",
                        }
                    )

    def _sort_key(suggestion: dict) -> tuple:
        group = (
            0
            if suggestion.get("link_status") != "linked"
            and suggestion not in cached_suggestions
            else (1 if suggestion.get("link_status") != "linked" else 2)
        )
        rel_order = {"high": 0, "medium": 1, "low": 2}
        return (group, rel_order.get(suggestion.get("relevance", "low"), 2))

    new_suggestions.sort(key=_sort_key)
    cached_suggestions.sort(key=_sort_key)
    linked_suggestions.sort(key=_sort_key)

    return {
        "entity_id": event_id,
        "entity_title": event["title"],
        "suggestions": new_suggestions + cached_suggestions + linked_suggestions,
    }


def _contemplate_question_to_events(
    question_id: str,
    *,
    connect_fn: ConnectFn,
    call_contemplate_deepseek_fn: CallContemplateFn,
) -> dict[str, object]:
    with connect_fn() as conn:
        question = conn.execute(
            "SELECT id, question FROM brainstorm_questions WHERE id = ?",
            (question_id,),
        ).fetchone()
    if not question:
        return {"entity_id": question_id, "suggestions": [], "error": "问题不存在"}
    with connect_fn() as conn:
        linked = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    linked_ids = {row["event_id"] for row in linked}
    with connect_fn() as conn:
        cached_rows = conn.execute(
            "SELECT event_id, relevance, reason FROM brainstorm_contemplate_cache WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    cached: dict[str, dict] = {
        row["event_id"]: {
            "relevance": row["relevance"],
            "reason": row["reason"],
        }
        for row in cached_rows
    }
    cached_ids = set(cached.keys())
    with connect_fn() as conn:
        rows = conn.execute(
            """SELECT id, title, ai_summary, raw_summary FROM events
               WHERE source_id IN ('douyin', 'user-upload')
                 AND (ai_summary != '' OR raw_summary != '')
                 AND status = 'completed'
               ORDER BY created_at DESC LIMIT 60"""
        ).fetchall()
    candidates = [
        dict(row)
        for row in rows
        if row["id"] not in linked_ids and row["id"] not in cached_ids
    ]
    cached_suggestions = []
    for event_id, judgment in cached.items():
        if event_id not in linked_ids:
            event_row = next((row for row in rows if row["id"] == event_id), None)
            if event_row is None:
                event_row = conn.execute(
                    "SELECT title, source_id FROM events WHERE id = ?", (event_id,)
                ).fetchone()
                if event_row is None:
                    continue
                if event_row["source_id"] not in (
                    "douyin",
                    "user-upload",
                    "user-concept",
                ):
                    continue
            title = event_row["title"] if event_row else event_id
            cached_suggestions.append(
                {
                    "event_id": event_id,
                    "event_title": title,
                    "relevance": judgment["relevance"],
                    "reason": judgment["reason"] or "",
                }
            )
    if not candidates and not cached_suggestions:
        return {
            "entity_id": question_id,
            "entity_title": question["question"],
            "suggestions": [],
            "note": "所有内容已关联或已判断",
        }

    new_suggestions: list[dict] = []
    if candidates:
        event_lines = []
        for i, event in enumerate(candidates):
            text = (event["ai_summary"] or "") or (event["raw_summary"] or "")
            full_text = text[:3000] if len(text) > 3000 else text
            event_lines.append(f"[{i}] {event['title']}\n内容：{full_text}")

        prompt = (
            "你是一个内容匹配助手。以下是一个问题，请判断下面哪些文章可以用于回答它。\n"
            "对每篇文章，仔细阅读全文后判断是否可基于其内容回答问题：\n"
            "- 如果文章直接涉及该问题的核心，标为 high\n"
            "- 如果文章部分相关或可提供背景信息，标为 medium\n"
            "- 如果完全无关，标为 low\n"
            "注意：不要因为文章标题或关键词看起来相关就误判，必须基于内容的实质关联。\n"
            '只输出 JSON 数组：[{"index": 0, "relevance": "high", "reason": "一句话原因"}, ...]\n'
            "只输出 high 或 medium，low 跳过。\n\n"
            f"问题：{question['question']}\n\n"
            f"待评估文章：\n" + "\n\n".join(event_lines)
        )

        matches = call_contemplate_deepseek_fn(prompt)

        matched_indices: set[int] = set()
        with connect_fn() as conn:
            for match in matches:
                idx = match.get("index")
                if idx is not None and 0 <= idx < len(candidates):
                    matched_indices.add(idx)
                    event = candidates[idx]
                    relevance = match.get("relevance", "medium")
                    reason = match.get("reason", "")
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (question_id, event["id"], relevance, reason),
                    )
                    new_suggestions.append(
                        {
                            "event_id": event["id"],
                            "event_title": event["title"],
                            "relevance": relevance,
                            "reason": reason,
                        }
                    )
            for i, event in enumerate(candidates):
                if i not in matched_indices:
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (question_id, event["id"], "low", ""),
                    )

    all_suggestions = cached_suggestions + new_suggestions
    all_suggestions.sort(
        key=lambda suggestion: 0 if suggestion["relevance"] == "high" else 1
    )

    return {
        "entity_id": question_id,
        "entity_title": question["question"],
        "suggestions": all_suggestions,
    }


def _call_contemplate_deepseek(
    prompt: str, *, chat_fn: ChatFn, logger: logging.Logger
) -> list[dict]:
    messages = [
        {
            "role": "system",
            "content": "You are a JSON-only API. Always output valid JSON array, nothing else.",
        },
        {"role": "user", "content": prompt},
    ]
    raw = chat_fn(
        messages,
        temperature=0.1,
        max_tokens=4096,
        timeout=120,
        module="brainstorm",
        task="concept_extract",
    )
    if raw is None:
        return []

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3]

    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        logger.warning(
            "Contemplate JSON parse error at line %d col %d — trying partial recovery",
            error.lineno,
            error.colno,
        )
        try:
            truncated = raw[: error.pos]
            last_brace = truncated.rfind("}")
            if last_brace > 0:
                partial = truncated[: last_brace + 1] + "]"
                return json.loads(partial)
        except Exception:
            pass
        return []
