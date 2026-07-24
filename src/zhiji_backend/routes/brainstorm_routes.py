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

from .. import brainstorm_answer_service, brainstorm_question_service
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


def _call_ai_chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 2000,
                        module: str = "", task: str = "") -> str:
    """Call the configured AI API and return the assistant's text response."""
    content = chat(messages, temperature=temperature, max_tokens=max_tokens, timeout=120,
                   module=module, task=task)
    if content is None:
        raise RuntimeError("AI API 未配置")
    return content


def _build_reference_docs(event_ids: list[str]) -> tuple[list[dict], dict[str, str]]:
    """Return (article_list, id_to_index_map) from event IDs.
    article_list: [{"index": N, "title": ..., "text": ...}]
    id_to_index_map: {event_id: "文档N"}"""
    articles: list[dict[str, object]] = []
    id_to_idx: dict[str, str] = {}
    with connect() as conn:
        placeholders = ",".join(["?" for _ in event_ids])
        rows = conn.execute(
            f"SELECT id, title, title_cn, ai_summary, raw_summary FROM events WHERE id IN ({placeholders})",
            tuple(event_ids),
        ).fetchall()
    for i, row in enumerate(rows, 1):
        text = (row["ai_summary"] or "") or (row["raw_summary"] or "")
        if text.strip():
            title = row["title_cn"] or row["title"] or "未命名"
            articles.append({"index": i, "title": title, "text": text[:4000] if len(text) > 4000 else text})
            id_to_idx[row["id"]] = f"文档{i}"
    return articles, id_to_idx


def _build_conversation_messages(question_id: str, role_filter: bool = True) -> list[dict]:
    """Return conversation messages from DB as LLM-ready list."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM brainstorm_messages WHERE question_id = ? ORDER BY id ASC",
            (question_id,),
        ).fetchall()
    msgs: list[dict] = []
    for r in rows:
        msgs.append({"role": r["role"], "content": r["content"]})
    return msgs


def _parse_refs_from_answer(answer: str, id_to_idx: dict[str, str]) -> list[str]:
    """Parse [文档N] references from answer text, return list of event_ids that were referenced."""
    ref_ids: list[str] = []
    seen: set[str] = set()
    for eid, label in id_to_idx.items():
        if label in answer and eid not in seen:
            ref_ids.append(eid)
            seen.add(eid)
    return ref_ids


@router.post("/api/brainstorm/{question_id}/conversation/start")
def start_conversation(question_id: SafeIdentifier, request: ConversationStartRequest) -> dict[str, object]:
    """Start a new conversation thread: lock reference docs, generate first answer."""
    if not request.event_ids:
        raise HTTPException(status_code=400, detail="至少选择一个参考文档")

    articles, id_to_idx = _build_reference_docs(request.event_ids)
    if not articles:
        return {"error": "所选事件没有可用的文本内容"}
    try:
        docs_text = "\n\n".join(
            f"[文档{a['index']}] 《{a['title']}》\n{a['text']}"
            for a in articles
        )
        system_prompt = (
            "你是严谨的研究分析助手。请基于以下参考文档回答用户问题。\n"
            "规则：\n"
            "1. 引用文档中的具体事实、数据、观点时，在对应句子末尾标注 [文档N]\n"
            "2. 概念性问题（如'XX是什么意思'）用通用知识回答，不强制引用文档\n"
            "3. 回答结构化、有深度，不要简单罗列\n\n"
            "参考文档：\n"
            f"{docs_text}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.question},
        ]
        answer = _call_ai_chat(messages, temperature=0.3, max_tokens=2000,
                                     module="brainstorm", task="answer")
    except Exception as e:
        logger.warning("Conversation start failed for question %s: %s", question_id, e)
        return {"error": f"AI 回答生成失败: {e}"}

    refs = _parse_refs_from_answer(answer, id_to_idx)

    # Persist messages
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with connect() as conn:
        conn.execute(
            "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'user', ?, '[]', ?)",
            (question_id, request.question, now),
        )
        conn.execute(
            "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'assistant', ?, ?, ?)",
            (question_id, answer, json.dumps(refs), now),
        )
        for eid in request.event_ids:
            conn.execute("INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)", (question_id, eid))
        # Update md file
        md = _brainstorm_md_path(question_id)
        md_block = f"## 回答 ({now})\n\n{answer}\n\n---\n\n"
        with open(md, "a", encoding="utf-8") as f:
            f.write(md_block)
        full_md = md.read_text(encoding="utf-8") if md.exists() else ""
        conn.execute("UPDATE brainstorm_questions SET content_md = ? WHERE id = ?", (full_md, question_id))

    return {
        "messages": [
            {"role": "user", "content": request.question, "created_at": now},
            {"role": "assistant", "content": answer, "refs": refs, "created_at": now},
        ],
        "locked_event_ids": request.event_ids,
    }


@router.post("/api/brainstorm/{question_id}/conversation/message")
def send_conversation_message(question_id: SafeIdentifier, request: ConversationMessageRequest) -> dict[str, object]:
    """Send a follow-up question in an existing conversation thread."""
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="追问内容不能为空")

    # Load locked event IDs
    with connect() as conn:
        evt_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?", (question_id,)
        ).fetchall()
    locked_ids = [r["event_id"] for r in evt_rows]

    if not locked_ids:
        raise HTTPException(status_code=400, detail="请先选择参考文档并开始对话")

    # Build reference docs + conversation history
    articles, id_to_idx = _build_reference_docs(locked_ids)
    history = _build_conversation_messages(question_id)

    try:
        docs_text = "\n\n".join(
            f"[文档{a['index']}] 《{a['title']}》\n{a['text']}"
            for a in articles
        )
        system_prompt = (
            "你是严谨的研究分析助手。请基于以下参考文档和对话历史回答用户追问。\n"
            "规则：\n"
            "1. 引用文档中的具体事实、数据、观点时，在对应句子末尾标注 [文档N]\n"
            "2. 概念性问题（如'XX是什么意思'）用通用知识回答，不强制引用文档\n"
            "3. 回答简洁、有针对性\n\n"
            "参考文档：\n"
            f"{docs_text}"
        )
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": request.content})
        answer = _call_ai_chat(messages, temperature=0.3, max_tokens=2000,
                                     module="brainstorm", task="answer")
    except Exception as e:
        logger.warning("Conversation message failed for question %s: %s", question_id, e)
        return {"error": f"AI 回答生成失败: {e}"}

    refs = _parse_refs_from_answer(answer, id_to_idx)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    with connect() as conn:
        conn.execute("INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'user', ?, '[]', ?)", (question_id, request.content, now))
        conn.execute("INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'assistant', ?, ?, ?)", (question_id, answer, json.dumps(refs), now))
        # Update md file
        md = _brainstorm_md_path(question_id)
        md_block = f"## 追问 ({now})\n\n**问：**{request.content}\n\n{answer}\n\n---\n\n"
        with open(md, "a", encoding="utf-8") as f:
            f.write(md_block)
        full_md = md.read_text(encoding="utf-8") if md.exists() else ""
        conn.execute("UPDATE brainstorm_questions SET content_md = ? WHERE id = ?", (full_md, question_id))

    return {"message": {"role": "assistant", "content": answer, "refs": refs, "created_at": now}}


@router.get("/api/brainstorm/{question_id}/conversation")
def get_conversation(question_id: SafeIdentifier) -> dict[str, object]:
    """Get the full conversation history + locked event IDs for a question."""
    with connect() as conn:
        # Check question exists
        q = conn.execute("SELECT id FROM brainstorm_questions WHERE id = ?", (question_id,)).fetchone()
        if not q:
            raise HTTPException(status_code=404, detail="Question not found")
        evt_rows = conn.execute("SELECT event_id FROM brainstorm_event_links WHERE question_id = ?", (question_id,)).fetchall()
        msg_rows = conn.execute("SELECT id, role, content, refs_json, created_at FROM brainstorm_messages WHERE question_id = ? ORDER BY id ASC", (question_id,)).fetchall()

    locked_ids = [r["event_id"] for r in evt_rows]
    messages: list[dict] = []
    for r in msg_rows:
        refs: list[str] = []
        try:
            refs = json.loads(r["refs_json"])
        except (json.JSONDecodeError, TypeError):
            pass
        messages.append({
            "id": r["id"], "role": r["role"], "content": r["content"],
            "refs": refs, "created_at": r["created_at"],
        })
    return {"locked_event_ids": locked_ids, "messages": messages}


@router.post("/api/brainstorm/{question_id}/conversation/summary")
def generate_conversation_summary(question_id: SafeIdentifier) -> dict[str, object]:
    """Generate a structured summary of the full conversation thread."""
    with connect() as conn:
        q = conn.execute("SELECT id, question FROM brainstorm_questions WHERE id = ?", (question_id,)).fetchone()
        if not q:
            raise HTTPException(status_code=404, detail="Question not found")
        evt_rows = conn.execute("SELECT event_id FROM brainstorm_event_links WHERE question_id = ?", (question_id,)).fetchall()

    locked_ids = [r["event_id"] for r in evt_rows]
    if not locked_ids:
        return {"error": "请先选择参考文档并开始对话"}

    articles, id_to_idx = _build_reference_docs(locked_ids)
    history = _build_conversation_messages(question_id)
    if not history:
        return {"error": "没有对话历史可总结"}

    # Fetch system concepts for relevance matching
    concepts: list[dict[str, str]] = []
    with connect() as conn:
        concept_rows = conn.execute(
            "SELECT title, ai_summary FROM events WHERE content_type = 'concept' AND ai_summary IS NOT NULL AND ai_summary != ''"
        ).fetchall()
        concepts = [{"title": r["title"], "summary": r["ai_summary"]} for r in concept_rows]

    # Build conversation transcript
    transcript_parts: list[str] = []
    for msg in history:
        role_label = "用户" if msg["role"] == "user" else "AI助手"
        transcript_parts.append(f"**{role_label}**：{msg['content']}")
    transcript = "\n\n".join(transcript_parts)

    try:
        docs_text = "\n\n".join(
            f"[文档{a['index']}] 《{a['title']}》\n{a['text']}"
            for a in articles
        )
        concepts_text = "\n".join(
            f"### 《{c['title']}》\n{c['summary']}" for c in concepts
        ) if concepts else "（暂无）"
        prompt = (
            "你正在进行研究对话的最终总结。以下是参考文档和完整对话历史。\n"
            "请提炼为一个结构化总结，格式如下：\n\n"
            "## 核心结论\n"
            "（用一两段话清晰回答原始问题，标注引用 [文档N]）\n\n"
            "## 概念定义\n"
            "（如果问题是询问特定概念/术语的含义，请从对话和文档中提取每个概念的完整定义。\n"
            "不要省略——对话中给出的核心特征、表现形式、运作机制、具体举例等都应纳入。格式：\n"
            "### 概念名称\n"
            "- **定义**：一句话概括\n"
            "- **核心特征**：...\n"
            "- **表现形式/运作机制**：...\n"
            "若问题不涉及概念定义（如纯分析/判断类问题），本节可省略）\n\n"
            "## 关键论点\n"
            "1. 论点一 [文档N][文档M]\n"
            "2. 论点二 [文档N]\n"
            "...\n\n"
            "## 待深挖方向\n"
            "- 方向一\n"
            "- 方向二\n\n"
            "## 相关概念\n"
            "（分析对话中涉及的概念，对比下方「系统已有概念」，列出相关的并简述关联点。格式：\n"
            "- **概念名称**：关联说明\n"
            "若无相关则标注「暂无明确相关概念」）\n\n"
            "## 参考文档清单\n"
            "[文档1] 标题一\n"
            "[文档2] 标题二\n"
            "...\n\n"
            "要求：每条论点独立标注来源；引用格式为 [文档N]。\n\n"
            f"参考文档：\n{docs_text}\n\n"
            f"系统已有概念：\n{concepts_text}\n\n"
            f"原始问题：{q['question']}\n\n"
            f"对话历史：\n{transcript}"
        )
        messages = [
            {"role": "system", "content": "你是严谨的研究总结助手，请基于对话和参考文档生成结构化总结。"},
            {"role": "user", "content": prompt},
        ]
        summary = _call_ai_chat(messages, temperature=0.3, max_tokens=3000,
                                     module="brainstorm", task="summary")
    except Exception as e:
        logger.warning("Summary generation failed for question %s: %s", question_id, e)
        return {"error": f"AI 总结生成失败: {e}"}

    # Parse refs from summary
    refs = _parse_refs_from_answer(summary, id_to_idx)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Persist summary as a special message type? No — save to md file and update content_md
    with connect() as conn:
        md = _brainstorm_md_path(question_id)
        md_block = f"## 总结 ({now})\n\n{summary}\n\n---\n\n"
        with open(md, "a", encoding="utf-8") as f:
            f.write(md_block)
        full_md = md.read_text(encoding="utf-8") if md.exists() else ""
        conn.execute("UPDATE brainstorm_questions SET content_md = ?, answer = ?, summary_created_at = ? WHERE id = ?", (full_md, summary, now, question_id))

    return {"summary": summary, "refs": refs, "created_at": now}


# ---------------------------------------------------------------------------
# Contemplate: bidirectional matching between events and brainstorm questions
# ---------------------------------------------------------------------------

class ContemplateRequest(BaseModel):
    direction: str   # "event_to_questions" or "question_to_events"
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
        return {"entity_id": request.entity_id, "suggestions": [], "error": "invalid direction"}


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
            "SELECT id, title, ai_summary, raw_summary FROM events WHERE id = ?", (event_id,)
        ).fetchone()
    if not event:
        return {"entity_id": event_id, "suggestions": [], "error": "事件不存在"}

    event_text = (event["ai_summary"] or "") or (event["raw_summary"] or "")
    if not event_text.strip():
        return {"entity_id": event_id, "suggestions": [], "error": "事件没有文本内容"}

    # 2. Get already-linked question IDs
    with connect() as conn:
        linked_rows = conn.execute(
            "SELECT question_id FROM brainstorm_event_links WHERE event_id = ?", (event_id,)
        ).fetchall()
    linked_ids = {r["question_id"] for r in linked_rows}

    # 3. Get cached judgments for this event
    with connect() as conn:
        cached_rows = conn.execute(
            "SELECT question_id, relevance, reason FROM brainstorm_contemplate_cache WHERE event_id = ?",
            (event_id,),
        ).fetchall()
    cached: dict[str, dict] = {r["question_id"]: {"relevance": r["relevance"], "reason": r["reason"]} for r in cached_rows}
    cached_ids = set(cached.keys())

    # 4. Get all open questions
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, question FROM brainstorm_questions WHERE status = 'open' ORDER BY created_at DESC LIMIT 50"
        ).fetchall()

    # Split: linked, cached (unlinked), new candidates
    all_questions = [dict(r) for r in rows]
    candidates = [q for q in all_questions if q["id"] not in linked_ids and q["id"] not in cached_ids]

    # Build linked suggestions (always at the end)
    linked_suggestions = []
    for q in all_questions:
        if q["id"] in linked_ids:
            # Look up relevance from cache if available, else mark as linked
            j = cached.get(q["id"])
            linked_suggestions.append({
                "question_id": q["id"],
                "question_text": q["question"],
                "relevance": j["relevance"] if j else "high",
                "reason": j["reason"] if j else "已关联",
                "link_status": "linked",
            })

    # Build cached suggestions (unlinked, already judged)
    cached_suggestions = []
    for q in all_questions:
        if q["id"] not in linked_ids and q["id"] in cached_ids:
            j = cached[q["id"]]
            cached_suggestions.append({
                "question_id": q["id"],
                "question_text": q["question"],
                "relevance": j["relevance"],
                "reason": j["reason"] or "",
                "link_status": "unlinked",
            })

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
                    new_suggestions.append({
                        "question_id": q["id"],
                        "question_text": q["question"],
                        "relevance": relevance,
                        "reason": reason,
                        "link_status": "unlinked",
                    })
            # Cache unmatched candidates as "low"
            for i, q in enumerate(candidates):
                if i not in matched_indices:
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (q["id"], event_id, "low", ""),
                    )
                    new_suggestions.append({
                        "question_id": q["id"],
                        "question_text": q["question"],
                        "relevance": "low",
                        "reason": "",
                        "link_status": "unlinked",
                    })

    # 7. Sort: new (high→medium→low) → cached (high→medium→low) → linked
    def _sort_key(s: dict) -> tuple:
        group = 0 if s.get("link_status") != "linked" and s not in cached_suggestions else (
            1 if s.get("link_status") != "linked" else 2
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
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?", (question_id,)
        ).fetchall()
    linked_ids = {r["event_id"] for r in linked}

    # 3. Get cached judgments for this question
    with connect() as conn:
        cached_rows = conn.execute(
            "SELECT event_id, relevance, reason FROM brainstorm_contemplate_cache WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    cached: dict[str, dict] = {r["event_id"]: {"relevance": r["relevance"], "reason": r["reason"]} for r in cached_rows}
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

    candidates = [dict(r) for r in rows if r["id"] not in linked_ids and r["id"] not in cached_ids]

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
                if evt_row["source_id"] not in ("douyin", "user-upload", "user-concept"):
                    continue
            title = evt_row["title"] if evt_row else event_id
            cached_suggestions.append({
                "event_id": event_id,
                "event_title": title,
                "relevance": judgment["relevance"],
                "reason": judgment["reason"] or "",
            })

    if not candidates and not cached_suggestions:
        return {"entity_id": question_id, "entity_title": q["question"], "suggestions": [], "note": "所有内容已关联或已判断"}

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
            "只输出 JSON 数组：[{\"index\": 0, \"relevance\": \"high\", \"reason\": \"一句话原因\"}, ...]\n"
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
                    new_suggestions.append({
                        "event_id": evt["id"],
                        "event_title": evt["title"],
                        "relevance": relevance,
                        "reason": reason,
                    })
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
    all_suggestions.sort(key=lambda s: (0 if s["relevance"] == "high" else 1))

    return {
        "entity_id": question_id,
        "entity_title": q["question"],
        "suggestions": all_suggestions,
    }


def _call_contemplate_deepseek(prompt: str) -> list[dict]:
    """Call DeepSeek for contemplation matching. Returns parsed JSON list."""
    messages = [
        {"role": "system", "content": "You are a JSON-only API. Always output valid JSON array, nothing else."},
        {"role": "user", "content": prompt},
    ]
    raw = chat(messages, temperature=0.1, max_tokens=4096, timeout=120,
               module="brainstorm", task="concept_extract")
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
        logger.warning("Contemplate JSON parse error at line %d col %d — trying partial recovery", e.lineno, e.colno)
        # Try to recover by truncating at the error position
        try:
            truncated = raw[:e.pos]
            # Find last valid '}' to close the array
            last_brace = truncated.rfind('}')
            if last_brace > 0:
                partial = truncated[:last_brace + 1] + ']'
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
        q = conn.execute("SELECT id, question, answer FROM brainstorm_questions WHERE id = ?", (question_id,)).fetchone()
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
            def_match = re.match(r".*?定义\*\*[：:]\s*(.+?)(?=\n- |\n###|\n\n|\Z)", rest, re.DOTALL)
            desc = def_match.group(1).strip() if def_match else name
            concepts.append({"name": name, "description": desc})
            seen.add(name)

    # ── 2. Parse "## 相关概念" section — related/supplementary concepts ──
    rel_section = re.search(r"## 相关概念\n+(.*?)(?=\n## |\Z)", answer, re.DOTALL)
    if rel_section:
        section = rel_section.group(1).strip()
        for m in re.finditer(r"- \*\*(.+?)\*\*[：:]\s*(.+?)(?=\n- \*\*|\n$|\Z)", section, re.DOTALL):
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
                ), [c["name"] for c in concepts]
            ).fetchall()
            existing_titles = {r["title"] for r in rows}

    result = []
    for c in concepts:
        exists = c["name"] in existing_titles
        result.append({
            "name": c["name"],
            "description": c["description"],
            "precipitated": exists,
        })

    return {"question_id": question_id, "concepts": result}


@router.post("/api/brainstorm/concepts/precipitate")
def precipitate_concept(req: PrecipitateConceptRequest) -> dict[str, object]:
    """Save a concept from the brainstom summary into the event store as a concept entry."""
    from ..routes.ingest_routes import _create_concept

    # Dup check
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM events WHERE content_type = 'concept' AND title = ?", (req.name,)
        ).fetchone()
    if existing:
        return {"status": "exists", "event_id": existing["id"], "message": f"概念「{req.name}」已存在"}

    # Fetch linked documents for context
    context_docs: list[dict[str, str]] = []
    with connect() as conn:
        link_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?", (req.question_id,)
        ).fetchall()
    linked_ids = [r["event_id"] for r in link_rows]
    if linked_ids:
        articles, _ = _build_reference_docs(linked_ids)
        context_docs = [{"title": a["title"], "content": a["text"]} for a in articles]

    try:
        result = _create_concept(req.name, "uncategorized", req.description,
                                 force_ai=True, context_docs=context_docs if context_docs else None)
        # Link concept back to the question
        with connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
                (req.question_id, result["event_id"]),
            )
        return {"status": "created", "event_id": result["event_id"], "ai_summary": result.get("ai_summary", "")}
    except Exception as e:
        logger.warning("Concept precipitation failed for %s: %s", req.name, e)
        raise HTTPException(status_code=500, detail=f"沉淀失败: {e}")
