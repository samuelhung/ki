"""Concept parsing and precipitation for brainstorm summaries."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

type ConnectFn = Callable[[], Any]
type BuildReferenceDocsFn = Callable[
    [list[str]], tuple[list[dict[str, str]], dict[str, str]]
]
type CreateConceptFn = Callable[..., dict]


logger = logging.getLogger("zhiji_backend.routes.brainstorm_routes")


def list_summary_concepts(
    question_id: str, *, connect_fn: ConnectFn
) -> dict[str, object]:
    """Parse summary concepts and report whether each already exists."""
    with connect_fn() as conn:
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

    def_section = re.search(r"## 概念定义\n+(.*?)(?=\n## |\Z)", answer, re.DOTALL)
    if def_section:
        section = def_section.group(1).strip()
        for match in re.finditer(r"### (.+?)\n", section):
            name = match.group(1).strip()
            if name in seen:
                continue
            rest_start = match.end()
            rest = section[rest_start:]
            def_match = re.match(
                r".*?定义\*\*[：:]\s*(.+?)(?=\n- |\n###|\n\n|\Z)",
                rest,
                re.DOTALL,
            )
            desc = def_match.group(1).strip() if def_match else name
            concepts.append({"name": name, "description": desc})
            seen.add(name)

    rel_section = re.search(r"## 相关概念\n+(.*?)(?=\n## |\Z)", answer, re.DOTALL)
    if rel_section:
        section = rel_section.group(1).strip()
        for match in re.finditer(
            r"- \*\*(.+?)\*\*[：:]\s*(.+?)(?=\n- \*\*|\n$|\Z)",
            section,
            re.DOTALL,
        ):
            name = match.group(1).strip()
            if name in seen:
                continue
            desc = match.group(2).strip()
            concepts.append({"name": name, "description": desc})
            seen.add(name)

    existing_titles: set[str] = set()
    if concepts:
        with connect_fn() as conn:
            rows = conn.execute(
                "SELECT title FROM events WHERE content_type = 'concept' AND title IN ({})".format(
                    ",".join("?" for _ in concepts)
                ),
                [concept["name"] for concept in concepts],
            ).fetchall()
            existing_titles = {row["title"] for row in rows}

    result = []
    for concept in concepts:
        exists = concept["name"] in existing_titles
        result.append(
            {
                "name": concept["name"],
                "description": concept["description"],
                "precipitated": exists,
            }
        )

    return {"question_id": question_id, "concepts": result}


def precipitate_concept(
    req: Any,
    *,
    connect_fn: ConnectFn,
    build_reference_docs_fn: BuildReferenceDocsFn,
    create_concept_fn: CreateConceptFn,
    logger: logging.Logger,
) -> dict[str, object]:
    """Save a summary concept into the event store."""
    with connect_fn() as conn:
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

    context_docs: list[dict[str, str]] = []
    with connect_fn() as conn:
        link_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            (req.question_id,),
        ).fetchall()
    linked_ids = [row["event_id"] for row in link_rows]
    if linked_ids:
        articles, _ = build_reference_docs_fn(linked_ids)
        context_docs = [
            {"title": article["title"], "content": article["text"]}
            for article in articles
        ]

    try:
        result = create_concept_fn(
            req.name,
            "uncategorized",
            req.description,
            force_ai=True,
            context_docs=context_docs if context_docs else None,
        )
        with connect_fn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
                (req.question_id, result["event_id"]),
            )
        return {
            "status": "created",
            "event_id": result["event_id"],
            "ai_summary": result.get("ai_summary", ""),
        }
    except Exception as error:
        logger.warning("Concept precipitation failed for %s: %s", req.name, error)
        raise HTTPException(status_code=500, detail=f"沉淀失败: {error}")
