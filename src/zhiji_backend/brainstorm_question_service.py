"""Persistence and Markdown workflows for brainstorm questions."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException

type ConnectFn = Callable[[], AbstractContextManager[sqlite3.Connection]]
type ClassifyFn = Callable[[str, str], str]
type MarkdownPathFn = Callable[[str], Path]
type UnlinkFn = Callable[[str], None]
type UUIDFn = Callable[[], object]


class Timestamp(Protocol):
    def strftime(self, format: str) -> str: ...


type NowFn = Callable[[], Timestamp]


class CreateQuestionRequest(Protocol):
    question: str


class QuestionBatchRequest(Protocol):
    question_ids: list[str]


logger = logging.getLogger("zhiji_backend.routes.brainstorm_routes")


def list_brainstorm_questions(
    status: str | None,
    topic: str | None,
    offset: int,
    limit: int,
    *,
    connect_fn: ConnectFn,
    logger: logging.Logger,
) -> dict[str, object]:
    query = """
        SELECT b.id, b.event_id, b.question, b.status, b.created_at, b.topic,
               (SELECT json_group_array(bel.event_id) FROM brainstorm_event_links bel WHERE bel.question_id = b.id) as answered_event_ids,
               e.title, e.title_cn, e.source_id, e.url
        FROM brainstorm_questions b
        LEFT JOIN events e ON e.id = b.event_id
        WHERE 1=1
    """
    params: dict[str, object] = {}
    if status:
        query += " AND b.status = :status"
        params["status"] = status
    if topic:
        query += " AND b.topic = :topic"
        params["topic"] = topic
    query += " ORDER BY b.created_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = max(1, min(500, limit))
    params["offset"] = max(0, offset)

    with connect_fn() as conn:
        rows = conn.execute(query, params).fetchall()
    return {"questions": [dict(row) for row in rows]}


def brainstorm_topic_counts(
    *, connect_fn: ConnectFn, logger: logging.Logger
) -> dict[str, int]:
    topics = ["格局", "财富", "认知", "前瞻"]
    result: dict[str, int] = {}
    with connect_fn() as conn:
        for topic in topics:
            count = conn.execute(
                "SELECT COUNT(*) FROM brainstorm_questions WHERE topic = ?",
                (topic,),
            ).fetchone()[0]
            result[topic] = int(count)
    return result


def get_brainstorm_question(
    question_id: str,
    *,
    connect_fn: ConnectFn,
    markdown_path_fn: MarkdownPathFn,
    logger: logging.Logger,
) -> dict[str, object]:
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id, event_id, question, status, created_at, answer, summary_created_at FROM brainstorm_questions WHERE id = ?",
            (question_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Question not found")
    result = dict(row)
    with connect_fn() as conn:
        event_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    result["answered_event_ids"] = json.dumps(
        [event_row["event_id"] for event_row in event_rows]
    )
    with connect_fn() as conn:
        judged_rows = conn.execute(
            "SELECT event_id, relevance FROM brainstorm_contemplate_cache WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    result["judged_events"] = json.dumps(
        [
            {"event_id": judged_row["event_id"], "relevance": judged_row["relevance"]}
            for judged_row in judged_rows
        ]
    )
    markdown_path = markdown_path_fn(question_id)
    result["md_content"] = (
        markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
    )
    return result


def create_brainstorm_question(
    request: CreateQuestionRequest,
    *,
    connect_fn: ConnectFn,
    classify_fn: ClassifyFn,
    markdown_path_fn: MarkdownPathFn,
    uuid_fn: UUIDFn,
    now_fn: NowFn,
    logger: logging.Logger,
) -> dict[str, object]:
    question_id = str(uuid_fn())
    now = now_fn().strftime("%Y-%m-%d %H:%M")
    with connect_fn() as conn:
        conn.execute(
            "INSERT INTO brainstorm_questions (id, event_id, question) VALUES (?, '', ?)",
            (question_id, request.question),
        )
    markdown_path = markdown_path_fn(question_id)
    markdown_content = f"# 问题\n\n{request.question}\n\n创建时间：{now}\n\n---\n\n"
    markdown_path.write_text(markdown_content, encoding="utf-8")
    with connect_fn() as conn:
        conn.execute(
            "UPDATE brainstorm_questions SET content_md = ? WHERE id = ?",
            (markdown_content, question_id),
        )
    topic = "认知"
    try:
        topic = classify_fn(request.question, "")
        with connect_fn() as conn:
            conn.execute(
                "UPDATE brainstorm_questions SET topic = ? WHERE id = ?",
                (topic, question_id),
            )
    except Exception:
        pass
    return {
        "ok": True,
        "id": question_id,
        "question": request.question,
        "topic": topic,
    }


def delete_brainstorm_question(
    question_id: str,
    *,
    connect_fn: ConnectFn,
    unlink_fn: UnlinkFn,
    logger: logging.Logger,
) -> dict[str, object]:
    with connect_fn() as conn:
        existing = conn.execute(
            "SELECT id FROM brainstorm_questions WHERE id = ?", (question_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Question not found")
        conn.execute("DELETE FROM brainstorm_questions WHERE id = ?", (question_id,))
    unlink_fn(question_id)
    return {"ok": True, "deleted": question_id}


def batch_delete_brainstorm_questions(
    payload: QuestionBatchRequest,
    *,
    connect_fn: ConnectFn,
    unlink_fn: UnlinkFn,
    logger: logging.Logger,
) -> dict[str, object]:
    deleted = 0
    for question_id in payload.question_ids:
        with connect_fn() as conn:
            existing = conn.execute(
                "SELECT id FROM brainstorm_questions WHERE id = ?", (question_id,)
            ).fetchone()
            if existing is None:
                continue
            conn.execute(
                "DELETE FROM brainstorm_questions WHERE id = ?", (question_id,)
            )
        unlink_fn(question_id)
        deleted += 1
    return {"ok": True, "deleted": deleted}


def mark_brainstorm_done(
    question_id: str, *, connect_fn: ConnectFn, logger: logging.Logger
) -> dict[str, object]:
    with connect_fn() as conn:
        existing = conn.execute(
            "SELECT id FROM brainstorm_questions WHERE id = ?", (question_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Question not found")
        conn.execute(
            "UPDATE brainstorm_questions SET status = 'done' WHERE id = ?",
            (question_id,),
        )
    return {"ok": True, "id": question_id, "status": "done"}
