"""Brainstorm question CRUD, answering, conversation, and contemplation endpoints."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from .. import (
    brainstorm_answer_service,
    brainstorm_conversation_service,
    brainstorm_question_service,
)
from ..ai_client import chat
from ..classifier import classify_content
from ..db import connect
from ..paths import BRAINSTORM_DIR
from ..security.constraints import (
    MAX_OFFSET,
    MAX_PAGE_SIZE,
    BoundedIdentifierList,
    SafeIdentifier,
    SafeIdentifierList,
    safe_identifier,
)
from ..security.paths import resolve_under, safe_unlink_under

logger = logging.getLogger(__name__)

router = APIRouter()


def _brainstorm_md_path(question_id: str) -> Path:
    safe_identifier(question_id)
    return resolve_under(BRAINSTORM_DIR, f"{question_id}.md", must_exist=False)


def _safe_brainstorm_unlink(question_id: str) -> None:
    try:
        safe_unlink_under(BRAINSTORM_DIR, f"{question_id}.md")
    except Exception:
        logger.warning("Refusing to delete unsafe brainstorm artifact", exc_info=True)


@router.get("/api/brainstorm")
def list_brainstorm_questions(
    status: str | None = None,
    topic: str | None = None,
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    limit: int = Query(200, ge=1, le=MAX_PAGE_SIZE),
) -> dict[str, object]:
    """List brainstorm questions, newest first. Optional topic filter."""
    return brainstorm_question_service.list_brainstorm_questions(
        status,
        topic,
        offset,
        limit,
        connect_fn=connect,
        logger=logger,
    )


@router.get("/api/brainstorm/topic-counts")
def brainstorm_topic_counts() -> dict[str, int]:
    """Return question counts per topic for brainstorm tabs."""
    return brainstorm_question_service.brainstorm_topic_counts(
        connect_fn=connect, logger=logger
    )


@router.get("/api/brainstorm/{question_id}")
def get_brainstorm_question(question_id: SafeIdentifier) -> dict[str, object]:
    """Get a single brainstorm question with its answered_event_ids and latest answer."""
    return brainstorm_question_service.get_brainstorm_question(
        question_id,
        connect_fn=connect,
        markdown_path_fn=_brainstorm_md_path,
        logger=logger,
    )


def _extract_latest_answer(md_path: Path) -> str:
    return brainstorm_answer_service._extract_latest_answer(md_path)


class CreateQuestionRequest(BaseModel):
    question: str


@router.post("/api/brainstorm")
def create_brainstorm_question(request: CreateQuestionRequest) -> dict[str, object]:
    """Manually create a brainstorm question and its .md file."""
    return brainstorm_question_service.create_brainstorm_question(
        request,
        connect_fn=connect,
        classify_fn=classify_content,
        markdown_path_fn=_brainstorm_md_path,
        uuid_fn=uuid.uuid4,
        now_fn=datetime.now,
        logger=logger,
    )


@router.delete("/api/brainstorm/{question_id}")
def delete_brainstorm_question(question_id: SafeIdentifier) -> dict[str, object]:
    """Delete a brainstorm question and its .md file."""
    return brainstorm_question_service.delete_brainstorm_question(
        question_id,
        connect_fn=connect,
        unlink_fn=_safe_brainstorm_unlink,
        logger=logger,
    )


class QuestionBatchRequest(BaseModel):
    question_ids: SafeIdentifierList


@router.post("/api/brainstorm/batch-delete")
def batch_delete_brainstorm_questions(
    payload: QuestionBatchRequest,
) -> dict[str, object]:
    """Delete multiple brainstorm questions and their .md files."""
    return brainstorm_question_service.batch_delete_brainstorm_questions(
        payload,
        connect_fn=connect,
        unlink_fn=_safe_brainstorm_unlink,
        logger=logger,
    )


@router.post("/api/brainstorm/{question_id}/done")
def mark_brainstorm_done(question_id: SafeIdentifier) -> dict[str, object]:
    """Mark a brainstorm question as done."""
    return brainstorm_question_service.mark_brainstorm_done(
        question_id, connect_fn=connect, logger=logger
    )


class AnswerRequest(BaseModel):
    question_id: SafeIdentifier
    question: str
    event_ids: BoundedIdentifierList


@router.post("/api/brainstorm/answer")
def get_answer_for_question(request: AnswerRequest) -> dict[str, object]:
    """Given a brainstorm question and selected events, find the answer from the articles.
    Saves the answer to the question's .md file and tracks answered_event_ids.
    """
    return brainstorm_answer_service.get_answer_for_question(
        request,
        connect_fn=connect,
        chat_fn=chat,
        markdown_path_fn=_brainstorm_md_path,
        logger=logger,
        now_fn=datetime.now,
    )


# ---------------------------------------------------------------------------
# Conversation: multi-turn dialog + summary
# ---------------------------------------------------------------------------


class ConversationStartRequest(BaseModel):
    event_ids: SafeIdentifierList
    question: str


class ConversationMessageRequest(BaseModel):
    content: str


def _call_ai_chat(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2000,
    module: str = "",
    task: str = "",
) -> str:
    return brainstorm_conversation_service._call_ai_chat(
        messages,
        temperature,
        max_tokens,
        module,
        task,
        chat_fn=chat,
    )


def _build_reference_docs(event_ids: list[str]) -> tuple[list[dict], dict[str, str]]:
    return brainstorm_conversation_service._build_reference_docs(
        event_ids, connect_fn=connect
    )


def _build_conversation_messages(
    question_id: str, role_filter: bool = True
) -> list[dict]:
    return brainstorm_conversation_service._build_conversation_messages(
        question_id, role_filter, connect_fn=connect
    )


def _parse_refs_from_answer(answer: str, id_to_idx: dict[str, str]) -> list[str]:
    return brainstorm_conversation_service._parse_refs_from_answer(answer, id_to_idx)


@router.post("/api/brainstorm/{question_id}/conversation/start")
def start_conversation(
    question_id: SafeIdentifier, request: ConversationStartRequest
) -> dict[str, object]:
    """Start a new conversation thread: lock reference docs, generate first answer."""
    return brainstorm_conversation_service.start_conversation(
        question_id,
        request,
        connect_fn=connect,
        chat_fn=chat,
        build_reference_docs_fn=_build_reference_docs,
        markdown_path_fn=_brainstorm_md_path,
        logger=logger,
    )


@router.post("/api/brainstorm/{question_id}/conversation/message")
def send_conversation_message(
    question_id: SafeIdentifier, request: ConversationMessageRequest
) -> dict[str, object]:
    """Send a follow-up question in an existing conversation thread."""
    return brainstorm_conversation_service.send_conversation_message(
        question_id,
        request,
        connect_fn=connect,
        chat_fn=chat,
        build_reference_docs_fn=_build_reference_docs,
        markdown_path_fn=_brainstorm_md_path,
        logger=logger,
    )


@router.get("/api/brainstorm/{question_id}/conversation")
def get_conversation(question_id: SafeIdentifier) -> dict[str, object]:
    """Get the full conversation history + locked event IDs for a question."""
    return brainstorm_conversation_service.get_conversation(
        question_id, connect_fn=connect
    )


@router.post("/api/brainstorm/{question_id}/conversation/summary")
def generate_conversation_summary(question_id: SafeIdentifier) -> dict[str, object]:
    """Generate a structured summary of the full conversation thread."""
    return brainstorm_conversation_service.generate_conversation_summary(
        question_id,
        connect_fn=connect,
        chat_fn=chat,
        build_reference_docs_fn=_build_reference_docs,
        markdown_path_fn=_brainstorm_md_path,
        logger=logger,
    )


# ---------------------------------------------------------------------------
# Contemplate: bidirectional matching between events and brainstorm questions
# ---------------------------------------------------------------------------


class ContemplateRequest(BaseModel):
    direction: str  # "event_to_questions" or "question_to_events"
    entity_id: str

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, value: str) -> str:
        return safe_identifier(value)


@router.post("/api/brainstorm/contemplate")
def contemplate(request: ContemplateRequest) -> dict[str, object]:
    """Bidirectional smart matching:
    - event_to_questions: given an event, find brainstorm questions it might answer
    - question_to_events: given a question, find events that might answer it
    Skips already-linked pairs.
    """
    if request.direction == "event_to_questions":
        return _contemplate_event_to_questions(request.entity_id)
    elif request.direction == "question_to_events":
        return _contemplate_question_to_events(request.entity_id)
    else:
        return {
            "entity_id": request.entity_id,
            "suggestions": [],
            "error": "invalid direction",
        }


@router.get("/api/brainstorm/event/{event_id}/linked-questions")
def get_linked_questions(event_id: SafeIdentifier) -> dict[str, object]:
    """Return brainstorm questions already linked to this event via brainstorm_event_links."""
    with connect() as conn:
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


def _contemplate_event_to_questions(event_id: str) -> dict[str, object]:
    """Given an event, find which brainstorm questions it might answer.
    Uses cache table so repeated contemplation skips already-judged pairs.
    """
    # 1. Get the event
    with connect() as conn:
        event = conn.execute(
            "SELECT id, title, ai_summary, raw_summary FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
    if not event:
        return {"entity_id": event_id, "suggestions": [], "error": "事件不存在"}

    event_text = (event["ai_summary"] or "") or (event["raw_summary"] or "")
    if not event_text.strip():
        return {"entity_id": event_id, "suggestions": [], "error": "事件没有文本内容"}

    # 2. Get already-linked question IDs
    with connect() as conn:
        linked_rows = conn.execute(
            "SELECT question_id FROM brainstorm_event_links WHERE event_id = ?",
            (event_id,),
        ).fetchall()
    linked_ids = {r["question_id"] for r in linked_rows}

    # 3. Get cached judgments for this event
    with connect() as conn:
        cached_rows = conn.execute(
            "SELECT question_id, relevance, reason FROM brainstorm_contemplate_cache WHERE event_id = ?",
            (event_id,),
        ).fetchall()
    cached: dict[str, dict] = {
        r["question_id"]: {"relevance": r["relevance"], "reason": r["reason"]}
        for r in cached_rows
    }
    cached_ids = set(cached.keys())

    # 4. Get all open questions
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, question FROM brainstorm_questions WHERE status = 'open' ORDER BY created_at DESC LIMIT 50"
        ).fetchall()

    # Split: linked, cached (unlinked), new candidates
    all_questions = [dict(r) for r in rows]
    candidates = [
        q
        for q in all_questions
        if q["id"] not in linked_ids and q["id"] not in cached_ids
    ]

    # Build linked suggestions (always at the end)
    linked_suggestions = []
    for q in all_questions:
        if q["id"] in linked_ids:
            # Look up relevance from cache if available, else mark as linked
            j = cached.get(q["id"])
            linked_suggestions.append(
                {
                    "question_id": q["id"],
                    "question_text": q["question"],
                    "relevance": j["relevance"] if j else "high",
                    "reason": j["reason"] if j else "已关联",
                    "link_status": "linked",
                }
            )

    # Build cached suggestions (unlinked, already judged)
    cached_suggestions = []
    for q in all_questions:
        if q["id"] not in linked_ids and q["id"] in cached_ids:
            j = cached[q["id"]]
            cached_suggestions.append(
                {
                    "question_id": q["id"],
                    "question_text": q["question"],
                    "relevance": j["relevance"],
                    "reason": j["reason"] or "",
                    "link_status": "unlinked",
                }
            )

    # 5. Ask AI for new candidates
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

        matches = _call_contemplate_deepseek(prompt)

        # 6. Persist results to cache (including low for unmatched candidates)
        matched_indices: set[int] = set()
        with connect() as conn:
            for m in matches:
                idx = m.get("index")
                if idx is not None and 0 <= idx < len(candidates):
                    matched_indices.add(idx)
                    q = candidates[idx]
                    relevance = m.get("relevance", "medium")
                    reason = m.get("reason", "")
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (q["id"], event_id, relevance, reason),
                    )
                    new_suggestions.append(
                        {
                            "question_id": q["id"],
                            "question_text": q["question"],
                            "relevance": relevance,
                            "reason": reason,
                            "link_status": "unlinked",
                        }
                    )
            # Cache unmatched candidates as "low"
            for i, q in enumerate(candidates):
                if i not in matched_indices:
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (q["id"], event_id, "low", ""),
                    )
                    new_suggestions.append(
                        {
                            "question_id": q["id"],
                            "question_text": q["question"],
                            "relevance": "low",
                            "reason": "",
                            "link_status": "unlinked",
                        }
                    )

    # 7. Sort: new (high→medium→low) → cached (high→medium→low) → linked
    def _sort_key(s: dict) -> tuple:
        group = (
            0
            if s.get("link_status") != "linked" and s not in cached_suggestions
            else (1 if s.get("link_status") != "linked" else 2)
        )
        rel_order = {"high": 0, "medium": 1, "low": 2}
        return (group, rel_order.get(s.get("relevance", "low"), 2))

    new_suggestions.sort(key=_sort_key)
    cached_suggestions.sort(key=_sort_key)
    linked_suggestions.sort(key=_sort_key)

    all_suggestions = new_suggestions + cached_suggestions + linked_suggestions

    return {
        "entity_id": event_id,
        "entity_title": event["title"],
        "suggestions": all_suggestions,
    }


def _contemplate_question_to_events(question_id: str) -> dict[str, object]:
    """Given a question, find which events might answer it.
    Uses full text for matching; persists results so repeated contemplation skips already-judged pairs.
    """
    # 1. Get the question
    with connect() as conn:
        q = conn.execute(
            "SELECT id, question FROM brainstorm_questions WHERE id = ?", (question_id,)
        ).fetchone()
    if not q:
        return {"entity_id": question_id, "suggestions": [], "error": "问题不存在"}

    # 2. Get already-linked event IDs
    with connect() as conn:
        linked = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    linked_ids = {r["event_id"] for r in linked}

    # 3. Get cached judgments for this question
    with connect() as conn:
        cached_rows = conn.execute(
            "SELECT event_id, relevance, reason FROM brainstorm_contemplate_cache WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    cached: dict[str, dict] = {
        r["event_id"]: {"relevance": r["relevance"], "reason": r["reason"]}
        for r in cached_rows
    }
    cached_ids = set(cached.keys())

    # 4. Get all non-RSS events with text, excluding linked AND cached
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, title, ai_summary, raw_summary FROM events
               WHERE source_id IN ('douyin', 'user-upload')
                 AND (ai_summary != '' OR raw_summary != '')
                 AND status = 'completed'
               ORDER BY created_at DESC LIMIT 60"""
        ).fetchall()

    candidates = [
        dict(r) for r in rows if r["id"] not in linked_ids and r["id"] not in cached_ids
    ]

    # Build cached suggestions (skipped from AI call)
    cached_suggestions = []
    for event_id, judgment in cached.items():
        if event_id not in linked_ids:
            # Look up title from rows, fallback to direct DB query for older events
            evt_row = next((r for r in rows if r["id"] == event_id), None)
            if evt_row is None:
                evt_row = conn.execute(
                    "SELECT title, source_id FROM events WHERE id = ?", (event_id,)
                ).fetchone()
                # Skip RSS-sourced events from cache (source_ids like bbc-world, reuters-world, etc.)
                if evt_row is None:
                    # Event has been deleted from the events table — skip stale cache entry
                    continue
                if evt_row["source_id"] not in (
                    "douyin",
                    "user-upload",
                    "user-concept",
                ):
                    continue
            title = evt_row["title"] if evt_row else event_id
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
            "entity_title": q["question"],
            "suggestions": [],
            "note": "所有内容已关联或已判断",
        }

    # 5. Ask AI for new candidates (full text, not snippet)
    new_suggestions: list[dict] = []
    if candidates:
        event_lines = []
        for i, evt in enumerate(candidates):
            text = (evt["ai_summary"] or "") or (evt["raw_summary"] or "")
            full_text = text[:3000] if len(text) > 3000 else text
            event_lines.append(f"[{i}] {evt['title']}\n内容：{full_text}")

        prompt = (
            "你是一个内容匹配助手。以下是一个问题，请判断下面哪些文章可以用于回答它。\n"
            "对每篇文章，仔细阅读全文后判断是否可基于其内容回答问题：\n"
            "- 如果文章直接涉及该问题的核心，标为 high\n"
            "- 如果文章部分相关或可提供背景信息，标为 medium\n"
            "- 如果完全无关，标为 low\n"
            "注意：不要因为文章标题或关键词看起来相关就误判，必须基于内容的实质关联。\n"
            '只输出 JSON 数组：[{"index": 0, "relevance": "high", "reason": "一句话原因"}, ...]\n'
            "只输出 high 或 medium，low 跳过。\n\n"
            f"问题：{q['question']}\n\n"
            f"待评估文章：\n" + "\n\n".join(event_lines)
        )

        matches = _call_contemplate_deepseek(prompt)

        # 6. Persist results to cache (including low for unmatched candidates)
        matched_indices: set[int] = set()
        with connect() as conn:
            for m in matches:
                idx = m.get("index")
                if idx is not None and 0 <= idx < len(candidates):
                    matched_indices.add(idx)
                    evt = candidates[idx]
                    relevance = m.get("relevance", "medium")
                    reason = m.get("reason", "")
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (question_id, evt["id"], relevance, reason),
                    )
                    new_suggestions.append(
                        {
                            "event_id": evt["id"],
                            "event_title": evt["title"],
                            "relevance": relevance,
                            "reason": reason,
                        }
                    )
            # Cache unmatched candidates as "low"
            for i, evt in enumerate(candidates):
                if i not in matched_indices:
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (question_id, evt["id"], "low", ""),
                    )

    # Combine cached + new
    all_suggestions = cached_suggestions + new_suggestions
    # Sort: high first, then medium
    all_suggestions.sort(key=lambda s: 0 if s["relevance"] == "high" else 1)

    return {
        "entity_id": question_id,
        "entity_title": q["question"],
        "suggestions": all_suggestions,
    }


def _call_contemplate_deepseek(prompt: str) -> list[dict]:
    """Call DeepSeek for contemplation matching. Returns parsed JSON list."""
    messages = [
        {
            "role": "system",
            "content": "You are a JSON-only API. Always output valid JSON array, nothing else.",
        },
        {"role": "user", "content": prompt},
    ]
    raw = chat(
        messages,
        temperature=0.1,
        max_tokens=4096,
        timeout=120,
        module="brainstorm",
        task="concept_extract",
    )
    if raw is None:
        return []

    # Parse JSON — handle markdown code fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3]

    # Fault-tolerant JSON parse — AI output may be truncated or malformed
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(
            "Contemplate JSON parse error at line %d col %d — trying partial recovery",
            e.lineno,
            e.colno,
        )
        # Try to recover by truncating at the error position
        try:
            truncated = raw[: e.pos]
            # Find last valid '}' to close the array
            last_brace = truncated.rfind("}")
            if last_brace > 0:
                partial = truncated[: last_brace + 1] + "]"
                return json.loads(partial)
        except Exception:
            pass
        return []


# ---------------------------------------------------------------------------
# Concept precipitation: extract concepts from summary and save to event store
# ---------------------------------------------------------------------------


class PrecipitateConceptRequest(BaseModel):
    question_id: SafeIdentifier
    name: str
    description: str = ""


@router.get("/api/brainstorm/{question_id}/concepts")
def list_summary_concepts(question_id: SafeIdentifier) -> dict[str, object]:
    """Parse concepts from the summary — both primary concepts (概念定义) and related concepts (相关概念).
    Returns each concept with its description and whether it already exists in the system."""
    with connect() as conn:
        q = conn.execute(
            "SELECT id, question, answer FROM brainstorm_questions WHERE id = ?",
            (question_id,),
        ).fetchone()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    answer = q["answer"] or ""
    if not answer:
        return {"question_id": question_id, "concepts": [], "message": "请先生成总结"}

    concepts: list[dict[str, object]] = []
    seen: set[str] = set()

    # ── 1. Parse "## 概念定义" section — primary concepts from the question ──
    def_section = re.search(r"## 概念定义\n+(.*?)(?=\n## |\Z)", answer, re.DOTALL)
    if def_section:
        section = def_section.group(1).strip()
        # Match: ### Concept Name (heading), followed by definition
        for m in re.finditer(r"### (.+?)\n", section):
            name = m.group(1).strip()
            if name in seen:
                continue
            # Try to extract the definition line: - **定义**：...
            rest_start = m.end()
            rest = section[rest_start:]
            def_match = re.match(
                r".*?定义\*\*[：:]\s*(.+?)(?=\n- |\n###|\n\n|\Z)", rest, re.DOTALL
            )
            desc = def_match.group(1).strip() if def_match else name
            concepts.append({"name": name, "description": desc})
            seen.add(name)

    # ── 2. Parse "## 相关概念" section — related/supplementary concepts ──
    rel_section = re.search(r"## 相关概念\n+(.*?)(?=\n## |\Z)", answer, re.DOTALL)
    if rel_section:
        section = rel_section.group(1).strip()
        for m in re.finditer(
            r"- \*\*(.+?)\*\*[：:]\s*(.+?)(?=\n- \*\*|\n$|\Z)", section, re.DOTALL
        ):
            name = m.group(1).strip()
            if name in seen:
                continue
            desc = m.group(2).strip()
            concepts.append({"name": name, "description": desc})
            seen.add(name)

    # Check which concepts already exist in the system
    existing_titles: set[str] = set()
    if concepts:
        with connect() as conn:
            rows = conn.execute(
                "SELECT title FROM events WHERE content_type = 'concept' AND title IN ({})".format(
                    ",".join("?" for _ in concepts)
                ),
                [c["name"] for c in concepts],
            ).fetchall()
            existing_titles = {r["title"] for r in rows}

    result = []
    for c in concepts:
        exists = c["name"] in existing_titles
        result.append(
            {
                "name": c["name"],
                "description": c["description"],
                "precipitated": exists,
            }
        )

    return {"question_id": question_id, "concepts": result}


@router.post("/api/brainstorm/concepts/precipitate")
def precipitate_concept(req: PrecipitateConceptRequest) -> dict[str, object]:
    """Save a concept from the brainstom summary into the event store as a concept entry."""
    from ..routes.ingest_routes import _create_concept

    # Dup check
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM events WHERE content_type = 'concept' AND title = ?",
            (req.name,),
        ).fetchone()
    if existing:
        return {
            "status": "exists",
            "event_id": existing["id"],
            "message": f"概念「{req.name}」已存在",
        }

    # Fetch linked documents for context
    context_docs: list[dict[str, str]] = []
    with connect() as conn:
        link_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            (req.question_id,),
        ).fetchall()
    linked_ids = [r["event_id"] for r in link_rows]
    if linked_ids:
        articles, _ = _build_reference_docs(linked_ids)
        context_docs = [{"title": a["title"], "content": a["text"]} for a in articles]

    try:
        result = _create_concept(
            req.name,
            "uncategorized",
            req.description,
            force_ai=True,
            context_docs=context_docs if context_docs else None,
        )
        # Link concept back to the question
        with connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
                (req.question_id, result["event_id"]),
            )
        return {
            "status": "created",
            "event_id": result["event_id"],
            "ai_summary": result.get("ai_summary", ""),
        }
    except Exception as e:
        logger.warning("Concept precipitation failed for %s: %s", req.name, e)
        raise HTTPException(status_code=500, detail=f"沉淀失败: {e}")
