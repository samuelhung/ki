from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from zhiji_backend import brainstorm_answer_service, prompt_registry


@dataclass
class AnswerRequest:
    question_id: str
    question: str
    event_ids: list[str]


class Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class RecordingConnection:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]],
        linked_event_ids: list[str],
        statements: list[tuple[str, object]],
    ) -> None:
        self.rows = rows
        self.linked_event_ids = linked_event_ids
        self.statements = statements
        self.content_md: str | None = None

    def execute(self, sql: str, params: object = ()) -> Result:
        self.statements.append((sql, params))
        if sql.startswith("SELECT id, ai_summary"):
            return Result(self.rows)
        if sql.startswith("INSERT OR IGNORE"):
            _question_id, event_id = params  # type: ignore[misc]
            if event_id not in self.linked_event_ids:
                self.linked_event_ids.append(event_id)
            return Result([])
        if sql.startswith("UPDATE brainstorm_questions SET content_md"):
            self.content_md = params[0]  # type: ignore[index]
            return Result([])
        if sql.startswith("SELECT event_id FROM brainstorm_event_links"):
            return Result(
                [{"event_id": event_id} for event_id in self.linked_event_ids]
            )
        raise AssertionError(f"Unexpected SQL: {sql}")


class ConnectionContext(AbstractContextManager[RecordingConnection]):
    def __init__(
        self,
        connection: RecordingConnection,
        on_enter: Callable[[], None] | None = None,
    ) -> None:
        self.connection = connection
        self.on_enter = on_enter

    def __enter__(self) -> RecordingConnection:
        if self.on_enter is not None:
            self.on_enter()
        return self.connection

    def __exit__(self, *args: object) -> None:
        return None


def _connect_fn(
    connection: RecordingConnection,
    *,
    on_second_enter: Callable[[], None] | None = None,
) -> Callable[[], ConnectionContext]:
    call_count = 0

    def connect() -> ConnectionContext:
        nonlocal call_count
        call_count += 1
        return ConnectionContext(
            connection,
            on_second_enter if call_count == 2 else None,
        )

    return connect


def test_extract_latest_answer_handles_missing_unanswered_and_latest_blocks(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.md"
    unanswered = tmp_path / "unanswered.md"
    unanswered.write_text("# 问题\n\n为什么？\n", encoding="utf-8")
    answered = tmp_path / "answered.md"
    answered.write_text(
        "# 问题\n\n为什么？\n\n"
        "## 回答 (2026-07-23 08:00)\n\n旧回答\n\n---\n\n"
        "## 回答 (2026-07-24 09:30)\n\n最新回答第一行\n最新回答第二行\n\n---\n\n尾注",
        encoding="utf-8",
    )

    assert brainstorm_answer_service._extract_latest_answer(missing) == ""
    assert brainstorm_answer_service._extract_latest_answer(unanswered) == ""
    assert (
        brainstorm_answer_service._extract_latest_answer(answered)
        == "最新回答第一行\n最新回答第二行"
    )


def test_answer_rejects_empty_selection_without_using_dependencies(
    tmp_path: Path,
) -> None:
    request = AnswerRequest("question-1", "为什么？", [])

    result = brainstorm_answer_service.get_answer_for_question(
        request,
        connect_fn=lambda: pytest.fail("database should not be used"),
        chat_fn=lambda *_args, **_kwargs: pytest.fail("chat should not be used"),
        markdown_path_fn=lambda _question_id: pytest.fail("path should not be used"),
        logger=brainstorm_answer_service.logger,
        now_fn=lambda: pytest.fail("clock should not be used"),
    )

    assert result == {"answer": "请至少选择一个事件作为参考文档。", "event_ids": []}


def test_answer_preserves_missing_row_response_and_selection_query() -> None:
    statements: list[tuple[str, object]] = []
    connection = RecordingConnection(
        rows=[], linked_event_ids=[], statements=statements
    )
    request = AnswerRequest("question-1", "为什么？", ["event-2", "event-1"])

    result = brainstorm_answer_service.get_answer_for_question(
        request,
        connect_fn=_connect_fn(connection),
        chat_fn=lambda *_args, **_kwargs: pytest.fail("chat should not be used"),
        markdown_path_fn=lambda _question_id: pytest.fail("path should not be used"),
        logger=brainstorm_answer_service.logger,
        now_fn=lambda: pytest.fail("clock should not be used"),
    )

    assert result == {"answer": "未找到所选事件。", "event_ids": request.event_ids}
    assert statements == [
        (
            "SELECT id, ai_summary, raw_summary, title FROM events WHERE id IN (?,?)",
            ("event-2", "event-1"),
        )
    ]


def test_answer_preserves_no_text_response_and_summary_selection() -> None:
    rows = [
        {
            "id": "event-1",
            "ai_summary": "   ",
            "raw_summary": "not used",
            "title": "One",
        },
        {"id": "event-2", "ai_summary": None, "raw_summary": "", "title": "Two"},
    ]
    connection = RecordingConnection(rows=rows, linked_event_ids=[], statements=[])
    request = AnswerRequest("question-1", "为什么？", ["event-1", "event-2"])

    result = brainstorm_answer_service.get_answer_for_question(
        request,
        connect_fn=_connect_fn(connection),
        chat_fn=lambda *_args, **_kwargs: pytest.fail("chat should not be used"),
        markdown_path_fn=lambda _question_id: pytest.fail("path should not be used"),
        logger=brainstorm_answer_service.logger,
        now_fn=lambda: pytest.fail("clock should not be used"),
    )

    assert result == {
        "answer": "所选事件没有可用的文本内容。",
        "event_ids": request.event_ids,
    }


def test_answer_preserves_ai_markdown_database_and_response_contract(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    markdown = tmp_path / "question-1.md"
    original_markdown = "# 问题\n\n为什么？\n\n---\n\n"
    markdown.write_text(original_markdown, encoding="utf-8")
    long_text = "长" * 3001
    rows = [
        {"id": "event-1", "ai_summary": None, "raw_summary": "原始摘要", "title": None},
        {
            "id": "event-2",
            "ai_summary": long_text,
            "raw_summary": "备用摘要",
            "title": "长文",
        },
    ]
    statements: list[tuple[str, object]] = []
    connection = RecordingConnection(
        rows=rows,
        linked_event_ids=["event-old", "event-2"],
        statements=statements,
    )
    request = AnswerRequest("question-1", "核心原因？", ["event-2", "event-1"])
    chat_calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []
    answers = iter([None, "第二篇回答"])
    write_seen_before_database = False

    def chat_fn(messages: list[dict[str, str]], **kwargs: object) -> str | None:
        chat_calls.append((messages, kwargs))
        return next(answers)

    def record_second_connection() -> None:
        nonlocal write_seen_before_database
        write_seen_before_database = (
            markdown.read_text(encoding="utf-8") != original_markdown
        )

    with caplog.at_level(
        logging.WARNING, logger="zhiji_backend.routes.brainstorm_routes"
    ):
        result = brainstorm_answer_service.get_answer_for_question(
            request,
            connect_fn=_connect_fn(
                connection, on_second_enter=record_second_connection
            ),
            chat_fn=chat_fn,
            markdown_path_fn=lambda question_id: tmp_path / f"{question_id}.md",
            logger=brainstorm_answer_service.logger,
            now_fn=lambda: SimpleNamespace(
                strftime=lambda format: (
                    "2026-07-24 09:30"
                    if format == "%Y-%m-%d %H:%M"
                    else pytest.fail(f"unexpected format: {format}")
                )
            ),
        )

    def messages_for(text: str) -> list[dict[str, str]]:
        prompt = (
            "你是一个文章分析助手。请严格基于以下文章内容，回答用户的问题。\n"
            "规则：只使用文章中的信息；如果文章没有涉及该问题，请明确说明'本文未涉及该问题'；\n"
            "回答简洁，控制在300字以内。\n\n"
            "问题：核心原因？\n\n"
            f"文章内容：\n{text}"
        )
        return [
            {
                "role": "system",
                "content": "你是严谨的文章分析助手，只基于给定文章回答问题，绝不编造。",
            },
            {"role": "user", "content": prompt},
        ]

    expected_kwargs = {
        "temperature": 0.3,
        "max_tokens": 800,
        "timeout": 60,
        "module": "brainstorm",
        "task": "contemplate",
    }
    assert chat_calls == [
        (messages_for("原始摘要"), expected_kwargs),
        (messages_for("长" * 3000), expected_kwargs),
    ]
    expected_display = (
        "### 基于「未命名」回答\n\n（AI 回答生成失败）\n\n"
        "---\n\n"
        "### 基于「长文」回答\n\n第二篇回答\n"
    )
    expected_block = (
        "## 回答 (2026-07-24 09:30)\n\n"
        "### 基于「未命名」回答\n\n（AI 回答生成失败）\n\n"
        "### 基于「长文」回答\n\n第二篇回答\n\n"
        "---\n\n"
    )
    assert result == {
        "answer": expected_display,
        "event_ids": request.event_ids,
        "answered_event_ids": ["event-old", "event-2", "event-1"],
    }
    assert markdown.read_text(encoding="utf-8") == original_markdown + expected_block
    assert connection.content_md == original_markdown + expected_block
    assert write_seen_before_database is True
    assert caplog.messages == [
        "Answer extraction failed for article '未命名': API unavailable"
    ]
    assert statements == [
        (
            "SELECT id, ai_summary, raw_summary, title FROM events WHERE id IN (?,?)",
            ("event-2", "event-1"),
        ),
        (
            "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
            ("question-1", "event-2"),
        ),
        (
            "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
            ("question-1", "event-1"),
        ),
        (
            "UPDATE brainstorm_questions SET content_md = ? WHERE id = ?",
            (original_markdown + expected_block, "question-1"),
        ),
        (
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            ("question-1",),
        ),
    ]


def test_answer_prompt_registry_points_to_service_without_digest_drift() -> None:
    assert prompt_registry.MODULE_MAP["brainstorm"]["answer"] == (
        "brainstorm_answer_service.py",
        ["get_answer_for_question"],
    )
    prompts = prompt_registry.get_all_prompts()["brainstorm"]["answer"]
    payload = json.dumps(
        sorted(prompts.items()), ensure_ascii=False, separators=(",", ":")
    )

    assert tuple(sorted(prompts)) == ("prompt",)
    assert hashlib.sha256(payload.encode()).hexdigest() == (
        "62a22b6f6bdc260a7d4cb2693410027111b4f84e48b60d279c793273799afc2e"
    )
    assert brainstorm_answer_service.logger.name == (
        "zhiji_backend.routes.brainstorm_routes"
    )
