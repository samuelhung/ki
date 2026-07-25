"""One-shot answer generation for brainstorm questions."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

type ConnectFn = Callable[[], AbstractContextManager[sqlite3.Connection]]
type MarkdownPathFn = Callable[[str], Path]


class ChatFn(Protocol):
    def __call__(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        timeout: int,
        module: str,
        task: str,
    ) -> str | None: ...


class Timestamp(Protocol):
    def strftime(self, format: str) -> str: ...


type NowFn = Callable[[], Timestamp]


class AnswerRequest(Protocol):
    question_id: str
    question: str
    event_ids: list[str]


logger = logging.getLogger("zhiji_backend.routes.brainstorm_routes")


def _extract_latest_answer(md_path: Path) -> str:
    """Extract the latest answer from a brainstorm .md file."""
    if not md_path.exists():
        return ""
    content = md_path.read_text(encoding="utf-8")
    blocks = content.split("## 回答")
    if len(blocks) < 2:
        return ""
    last = blocks[-1]
    lines = last.strip().split("\n")
    answer_lines = []
    started = False
    for line in lines:
        if not started:
            # Skip timestamp line like "(2026-06-08 14:58)"
            started = True
            continue
        if line.strip() == "---":
            break
        answer_lines.append(line)
    return "\n".join(answer_lines).strip()


def get_answer_for_question(
    request: AnswerRequest,
    *,
    connect_fn: ConnectFn,
    chat_fn: ChatFn,
    markdown_path_fn: MarkdownPathFn,
    logger: logging.Logger,
    now_fn: NowFn,
) -> dict[str, object]:
    if not request.event_ids:
        return {"answer": "请至少选择一个事件作为参考文档。", "event_ids": []}

    articles: list[dict[str, str]] = []
    with connect_fn() as conn:
        placeholders = ",".join(["?" for _ in request.event_ids])
        rows = conn.execute(
            f"SELECT id, ai_summary, raw_summary, title FROM events WHERE id IN ({placeholders})",
            tuple(request.event_ids),
        ).fetchall()

    if not rows:
        return {"answer": "未找到所选事件。", "event_ids": request.event_ids}

    for row in rows:
        text = (row["ai_summary"] or "") or (row["raw_summary"] or "")
        if text.strip():
            title = row["title"] or "未命名"
            articles.append(
                {
                    "title": title,
                    "text": text[:3000] if len(text) > 3000 else text,
                }
            )

    if not articles:
        return {
            "answer": "所选事件没有可用的文本内容。",
            "event_ids": request.event_ids,
        }

    now = now_fn().strftime("%Y-%m-%d %H:%M")
    md_parts: list[str] = []
    display_parts: list[str] = []

    for art in articles:
        prompt = (
            "你是一个文章分析助手。请严格基于以下文章内容，回答用户的问题。\n"
            "规则：只使用文章中的信息；如果文章没有涉及该问题，请明确说明'本文未涉及该问题'；\n"
            "回答简洁，控制在300字以内。\n\n"
            f"问题：{request.question}\n\n"
            f"文章内容：\n{art['text']}"
        )

        messages = [
            {
                "role": "system",
                "content": "你是严谨的文章分析助手，只基于给定文章回答问题，绝不编造。",
            },
            {"role": "user", "content": prompt},
        ]

        answer = chat_fn(
            messages,
            temperature=0.3,
            max_tokens=800,
            timeout=60,
            module="brainstorm",
            task="contemplate",
        )
        if answer is None:
            logger.warning(
                "Answer extraction failed for article '%s': API unavailable",
                art["title"],
            )
            answer = "（AI 回答生成失败）"

        md_parts.append(f"### 基于「{art['title']}」回答\n\n{answer}\n")
        display_parts.append(f"### 基于「{art['title']}」回答\n\n{answer}\n")

    combined_display = "\n---\n\n".join(display_parts)
    combined_md = "\n".join(md_parts) + "\n"

    markdown_path = markdown_path_fn(request.question_id)
    answer_block = f"## 回答 ({now})\n\n{combined_md}---\n\n"
    with open(markdown_path, "a", encoding="utf-8") as file:
        file.write(answer_block)

    with connect_fn() as conn:
        for event_id in request.event_ids:
            conn.execute(
                "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
                (request.question_id, event_id),
            )
        full_markdown = (
            markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
        )
        conn.execute(
            "UPDATE brainstorm_questions SET content_md = ? WHERE id = ?",
            (full_markdown, request.question_id),
        )
        event_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            (request.question_id,),
        ).fetchall()
    merged = [row["event_id"] for row in event_rows]

    return {
        "answer": combined_display,
        "event_ids": request.event_ids,
        "answered_event_ids": merged,
    }
