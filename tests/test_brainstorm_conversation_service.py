from __future__ import annotations

import hashlib
import inspect
import json
import logging
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime as RealDateTime
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from zhiji_backend import brainstorm_conversation_service, prompt_registry


@dataclass
class StartRequest:
    event_ids: list[str]
    question: str


@dataclass
class MessageRequest:
    content: str


class FixedDateTime(RealDateTime):
    @classmethod
    def now(cls, tz: object = None) -> FixedDateTime:
        return cls(2026, 7, 24, 9, 30)


def _sql(sql: str) -> str:
    return " ".join(sql.split())


class Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class StaticConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = ()) -> Result:
        self.calls.append((_sql(sql), params))
        return Result(self.rows)


class StaticContext(AbstractContextManager[StaticConnection]):
    def __init__(self, connection: StaticConnection) -> None:
        self.connection = connection

    def __enter__(self) -> StaticConnection:
        return self.connection

    def __exit__(self, *args: object) -> None:
        return None


class RecordingConnection:
    def __init__(self, connection: sqlite3.Connection, events: list[object]) -> None:
        self.connection = connection
        self.events = events

    def execute(self, sql: str, params: object = ()) -> sqlite3.Cursor:
        self.events.append(("sql", _sql(sql), params))
        return self.connection.execute(sql, params)


class RecordingContext(AbstractContextManager[RecordingConnection]):
    def __init__(
        self,
        connection: sqlite3.Connection,
        events: list[object],
        index: int,
    ) -> None:
        self.connection = connection
        self.events = events
        self.index = index

    def __enter__(self) -> RecordingConnection:
        self.events.append(("enter", self.index))
        return RecordingConnection(self.connection, self.events)

    def __exit__(self, *args: object) -> None:
        self.connection.commit()
        self.events.append(("exit", self.index))
        return None


class Database:
    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.events: list[object] = []
        self.connect_count = 0
        self.connection.executescript(
            """
            CREATE TABLE events (
                id TEXT PRIMARY KEY,
                title TEXT,
                title_cn TEXT,
                ai_summary TEXT,
                raw_summary TEXT,
                content_type TEXT
            );
            CREATE TABLE brainstorm_questions (
                id TEXT PRIMARY KEY,
                question TEXT,
                content_md TEXT,
                answer TEXT,
                summary_created_at TEXT
            );
            CREATE TABLE brainstorm_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id TEXT,
                role TEXT,
                content TEXT,
                refs_json TEXT,
                created_at TEXT
            );
            CREATE TABLE brainstorm_event_links (
                question_id TEXT,
                event_id TEXT,
                UNIQUE(question_id, event_id)
            );
            """
        )

    def connect(self) -> RecordingContext:
        self.connect_count += 1
        return RecordingContext(self.connection, self.events, self.connect_count)

    def execute(self, sql: str, params: object = ()) -> sqlite3.Cursor:
        return self.connection.execute(sql, params)

    def commit(self) -> None:
        self.connection.commit()

    def clear_events(self) -> None:
        self.events.clear()
        self.connect_count = 0


def _docs() -> tuple[list[dict[str, object]], dict[str, str]]:
    return (
        [
            {"index": 1, "title": "甲文", "text": "甲文内容"},
            {"index": 2, "title": "乙文", "text": "乙文内容"},
        ],
        {"event-a": "文档1", "event-b": "文档2"},
    )


def _path_recorder(path: Path, calls: list[str]) -> Callable[[str], Path]:
    def markdown_path(question_id: str) -> Path:
        calls.append(question_id)
        return path

    return markdown_path


def _start_system_prompt() -> str:
    return (
        "你是严谨的研究分析助手。请基于以下参考文档回答用户问题。\n"
        "规则：\n"
        "1. 引用文档中的具体事实、数据、观点时，在对应句子末尾标注 [文档N]\n"
        "2. 概念性问题（如'XX是什么意思'）用通用知识回答，不强制引用文档\n"
        "3. 回答结构化、有深度，不要简单罗列\n\n"
        "参考文档：\n"
        "[文档1] 《甲文》\n甲文内容\n\n[文档2] 《乙文》\n乙文内容"
    )


def _follow_up_system_prompt() -> str:
    return (
        "你是严谨的研究分析助手。请基于以下参考文档和对话历史回答用户追问。\n"
        "规则：\n"
        "1. 引用文档中的具体事实、数据、观点时，在对应句子末尾标注 [文档N]\n"
        "2. 概念性问题（如'XX是什么意思'）用通用知识回答，不强制引用文档\n"
        "3. 回答简洁、有针对性\n\n"
        "参考文档：\n"
        "[文档1] 《甲文》\n甲文内容\n\n[文档2] 《乙文》\n乙文内容"
    )


def _summary_prompt() -> str:
    return (
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
        "参考文档：\n[文档1] 《甲文》\n甲文内容\n\n[文档2] 《乙文》\n乙文内容\n\n"
        "系统已有概念：\n### 《系统概念》\n概念说明\n\n"
        "原始问题：原始问题\n\n"
        "对话历史：\n**用户**：首问\n\n**AI助手**：首答 [文档1]"
    )


def test_call_ai_chat_preserves_arguments_and_none_error() -> None:
    calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []
    messages = [{"role": "user", "content": "问题"}]

    def chat(messages_arg: list[dict[str, str]], **kwargs: object) -> str:
        calls.append((messages_arg, kwargs))
        return "回答"

    assert (
        brainstorm_conversation_service._call_ai_chat(
            messages,
            temperature=0.7,
            max_tokens=321,
            module="module-x",
            task="task-y",
            chat_fn=chat,
        )
        == "回答"
    )
    assert calls == [
        (
            messages,
            {
                "temperature": 0.7,
                "max_tokens": 321,
                "timeout": 120,
                "module": "module-x",
                "task": "task-y",
            },
        )
    ]

    with pytest.raises(RuntimeError, match="AI API 未配置"):
        brainstorm_conversation_service._call_ai_chat(
            messages, chat_fn=lambda *_args, **_kwargs: None
        )


def test_reference_documents_preserve_query_row_order_indexes_and_truncation() -> None:
    rows = [
        {
            "id": "event-b",
            "title": "English B",
            "title_cn": "中文乙",
            "ai_summary": "乙" * 4001,
            "raw_summary": "备用乙",
        },
        {
            "id": "event-empty",
            "title": "Empty",
            "title_cn": None,
            "ai_summary": "   ",
            "raw_summary": "不会使用",
        },
        {
            "id": "event-a",
            "title": None,
            "title_cn": None,
            "ai_summary": None,
            "raw_summary": "甲摘要",
        },
    ]
    connection = StaticConnection(rows)

    articles, mapping = brainstorm_conversation_service._build_reference_docs(
        ["event-a", "event-b", "event-empty"],
        connect_fn=lambda: StaticContext(connection),
    )

    assert articles == [
        {"index": 1, "title": "中文乙", "text": "乙" * 4000},
        {"index": 3, "title": "未命名", "text": "甲摘要"},
    ]
    assert mapping == {"event-b": "文档1", "event-a": "文档3"}
    assert connection.calls == [
        (
            "SELECT id, title, title_cn, ai_summary, raw_summary FROM events WHERE id IN (?,?,?)",
            ("event-a", "event-b", "event-empty"),
        )
    ]


def test_message_history_preserves_order_and_ignores_role_filter() -> None:
    rows = [
        {"role": "assistant", "content": "先前回答"},
        {"role": "tool", "content": "工具内容"},
        {"role": "user", "content": "追问"},
    ]
    connection = StaticConnection(rows)

    messages = brainstorm_conversation_service._build_conversation_messages(
        "question-1",
        role_filter=False,
        connect_fn=lambda: StaticContext(connection),
    )

    assert messages == rows
    assert connection.calls == [
        (
            "SELECT role, content FROM brainstorm_messages WHERE question_id = ? ORDER BY id ASC",
            ("question-1",),
        )
    ]


def test_reference_parsing_uses_mapping_order_and_deduplicates() -> None:
    mapping = {"event-2": "文档2", "event-1": "文档1", "event-3": "文档3"}

    assert brainstorm_conversation_service._parse_refs_from_answer(
        "先提 [文档1]，再提 [文档2] 和 [文档1]。", mapping
    ) == ["event-2", "event-1"]


def test_start_validation_and_missing_documents_do_not_use_unneeded_dependencies() -> (
    None
):
    with pytest.raises(HTTPException) as error:
        brainstorm_conversation_service.start_conversation(
            "question-1",
            StartRequest([], "问题"),
            connect_fn=lambda: pytest.fail("database should not be used"),
            chat_fn=lambda *_args, **_kwargs: pytest.fail("chat should not be used"),
            build_reference_docs_fn=lambda _ids: pytest.fail(
                "helper should not be used"
            ),
            markdown_path_fn=lambda _id: pytest.fail("path should not be used"),
            logger=brainstorm_conversation_service.logger,
        )
    assert (error.value.status_code, error.value.detail) == (
        400,
        "至少选择一个参考文档",
    )

    assert brainstorm_conversation_service.start_conversation(
        "question-1",
        StartRequest(["event-1"], "问题"),
        connect_fn=lambda: pytest.fail("database should not be used"),
        chat_fn=lambda *_args, **_kwargs: pytest.fail("chat should not be used"),
        build_reference_docs_fn=lambda _ids: ([], {}),
        markdown_path_fn=lambda _id: pytest.fail("path should not be used"),
        logger=brainstorm_conversation_service.logger,
    ) == {"error": "所选事件没有可用的文本内容"}


def test_start_preserves_exact_ai_writes_markdown_response_and_injections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(brainstorm_conversation_service, "datetime", FixedDateTime)
    database = Database()
    database.execute(
        "INSERT INTO brainstorm_questions (id, question, content_md) VALUES (?, ?, ?)",
        ("question-1", "原始问题", ""),
    )
    database.commit()
    markdown = tmp_path / "question-1.md"
    markdown.write_text("# 问题\n\n原始问题\n\n---\n\n", encoding="utf-8")
    path_calls: list[str] = []
    helper_calls: list[list[str]] = []
    chat_calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []

    def build_docs(
        event_ids: list[str],
    ) -> tuple[list[dict[str, object]], dict[str, str]]:
        helper_calls.append(event_ids)
        return _docs()

    def chat(messages: list[dict[str, str]], **kwargs: object) -> str:
        chat_calls.append((messages, kwargs))
        return "先引用乙 [文档2]，再引用甲 [文档1]。"

    request = StartRequest(["event-b", "event-a"], "为什么？")
    result = brainstorm_conversation_service.start_conversation(
        "question-1",
        request,
        connect_fn=database.connect,
        chat_fn=chat,
        build_reference_docs_fn=build_docs,
        markdown_path_fn=_path_recorder(markdown, path_calls),
        logger=brainstorm_conversation_service.logger,
    )

    assert helper_calls == [request.event_ids]
    assert chat_calls == [
        (
            [
                {"role": "system", "content": _start_system_prompt()},
                {"role": "user", "content": "为什么？"},
            ],
            {
                "temperature": 0.3,
                "max_tokens": 2000,
                "timeout": 120,
                "module": "brainstorm",
                "task": "answer",
            },
        )
    ]
    assert result == {
        "messages": [
            {"role": "user", "content": "为什么？", "created_at": "2026-07-24 09:30"},
            {
                "role": "assistant",
                "content": "先引用乙 [文档2]，再引用甲 [文档1]。",
                "refs": ["event-a", "event-b"],
                "created_at": "2026-07-24 09:30",
            },
        ],
        "locked_event_ids": request.event_ids,
    }
    assert path_calls == ["question-1"]
    assert markdown.read_text(encoding="utf-8") == (
        "# 问题\n\n原始问题\n\n---\n\n"
        "## 回答 (2026-07-24 09:30)\n\n"
        "先引用乙 [文档2]，再引用甲 [文档1]。\n\n---\n\n"
    )
    messages = database.execute(
        "SELECT role, content, refs_json, created_at FROM brainstorm_messages ORDER BY id"
    ).fetchall()
    assert [tuple(row) for row in messages] == [
        ("user", "为什么？", "[]", "2026-07-24 09:30"),
        (
            "assistant",
            "先引用乙 [文档2]，再引用甲 [文档1]。",
            '["event-a", "event-b"]',
            "2026-07-24 09:30",
        ),
    ]
    assert [
        tuple(row)
        for row in database.execute(
            "SELECT question_id, event_id FROM brainstorm_event_links ORDER BY rowid"
        ).fetchall()
    ] == [
        ("question-1", "event-b"),
        ("question-1", "event-a"),
    ]
    assert database.execute(
        "SELECT content_md FROM brainstorm_questions WHERE id = 'question-1'"
    ).fetchone()[0] == markdown.read_text(encoding="utf-8")
    assert database.events[0] == ("enter", 1)
    assert database.events[-1] == ("exit", 1)
    assert [event[1] for event in database.events if event[0] == "sql"] == [
        "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'user', ?, '[]', ?)",
        "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'assistant', ?, ?, ?)",
        "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
        "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
        "UPDATE brainstorm_questions SET content_md = ? WHERE id = ?",
    ]


def test_start_ai_failure_preserves_error_and_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="zhiji_backend.routes.brainstorm_routes")

    result = brainstorm_conversation_service.start_conversation(
        "question-1",
        StartRequest(["event-a"], "问题"),
        connect_fn=lambda: pytest.fail("database should not be used"),
        chat_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("boom")),
        build_reference_docs_fn=lambda _ids: _docs(),
        markdown_path_fn=lambda _id: tmp_path / "unused.md",
        logger=brainstorm_conversation_service.logger,
    )

    assert result == {"error": "AI 回答生成失败: boom"}
    assert (
        caplog.messages[-1] == "Conversation start failed for question question-1: boom"
    )


def test_follow_up_validation_requires_content_and_locked_documents() -> None:
    with pytest.raises(HTTPException) as error:
        brainstorm_conversation_service.send_conversation_message(
            "question-1",
            MessageRequest("   "),
            connect_fn=lambda: pytest.fail("database should not be used"),
            chat_fn=lambda *_args, **_kwargs: pytest.fail("chat should not be used"),
            build_reference_docs_fn=lambda _ids: pytest.fail(
                "helper should not be used"
            ),
            markdown_path_fn=lambda _id: pytest.fail("path should not be used"),
            logger=brainstorm_conversation_service.logger,
        )
    assert (error.value.status_code, error.value.detail) == (400, "追问内容不能为空")

    database = Database()
    with pytest.raises(HTTPException) as error:
        brainstorm_conversation_service.send_conversation_message(
            "question-1",
            MessageRequest("追问"),
            connect_fn=database.connect,
            chat_fn=lambda *_args, **_kwargs: pytest.fail("chat should not be used"),
            build_reference_docs_fn=lambda _ids: pytest.fail(
                "helper should not be used"
            ),
            markdown_path_fn=lambda _id: pytest.fail("path should not be used"),
            logger=brainstorm_conversation_service.logger,
        )
    assert (error.value.status_code, error.value.detail) == (
        400,
        "请先选择参考文档并开始对话",
    )


def test_follow_up_preserves_history_ai_writes_and_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(brainstorm_conversation_service, "datetime", FixedDateTime)
    database = Database()
    database.execute(
        "INSERT INTO brainstorm_questions (id, question, content_md) VALUES (?, ?, ?)",
        ("question-1", "原始问题", ""),
    )
    database.execute(
        "INSERT INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
        ("question-1", "event-b"),
    )
    database.execute(
        "INSERT INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
        ("question-1", "event-a"),
    )
    database.execute(
        "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, ?, ?, ?, ?)",
        ("question-1", "user", "首问", "[]", "old"),
    )
    database.execute(
        "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, ?, ?, ?, ?)",
        ("question-1", "assistant", "首答", "[]", "old"),
    )
    database.commit()
    database.clear_events()
    markdown = tmp_path / "question-1.md"
    markdown.write_text("existing\n", encoding="utf-8")
    chat_calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []

    def chat(messages: list[dict[str, str]], **kwargs: object) -> str:
        chat_calls.append((messages, kwargs))
        return "追答 [文档2]"

    result = brainstorm_conversation_service.send_conversation_message(
        "question-1",
        MessageRequest("继续？"),
        connect_fn=database.connect,
        chat_fn=chat,
        build_reference_docs_fn=lambda ids: (
            _docs() if ids == ["event-a", "event-b"] else pytest.fail(str(ids))
        ),
        markdown_path_fn=lambda _id: markdown,
        logger=brainstorm_conversation_service.logger,
    )

    assert chat_calls == [
        (
            [
                {"role": "system", "content": _follow_up_system_prompt()},
                {"role": "user", "content": "首问"},
                {"role": "assistant", "content": "首答"},
                {"role": "user", "content": "继续？"},
            ],
            {
                "temperature": 0.3,
                "max_tokens": 2000,
                "timeout": 120,
                "module": "brainstorm",
                "task": "answer",
            },
        )
    ]
    assert result == {
        "message": {
            "role": "assistant",
            "content": "追答 [文档2]",
            "refs": ["event-b"],
            "created_at": "2026-07-24 09:30",
        }
    }
    assert markdown.read_text(encoding="utf-8") == (
        "existing\n## 追问 (2026-07-24 09:30)\n\n**问：**继续？\n\n"
        "追答 [文档2]\n\n---\n\n"
    )
    assert [event for event in database.events if event[0] in {"enter", "exit"}] == [
        ("enter", 1),
        ("exit", 1),
        ("enter", 2),
        ("exit", 2),
        ("enter", 3),
        ("exit", 3),
    ]
    assert [event[1] for event in database.events if event[0] == "sql"] == [
        "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
        "SELECT role, content FROM brainstorm_messages WHERE question_id = ? ORDER BY id ASC",
        "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'user', ?, '[]', ?)",
        "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'assistant', ?, ?, ?)",
        "UPDATE brainstorm_questions SET content_md = ? WHERE id = ?",
    ]


def test_follow_up_ai_failure_preserves_error_and_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    database = Database()
    database.execute(
        "INSERT INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
        ("question-1", "event-a"),
    )
    database.commit()
    caplog.set_level(logging.WARNING, logger="zhiji_backend.routes.brainstorm_routes")

    result = brainstorm_conversation_service.send_conversation_message(
        "question-1",
        MessageRequest("追问"),
        connect_fn=database.connect,
        chat_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("offline")
        ),
        build_reference_docs_fn=lambda _ids: _docs(),
        markdown_path_fn=lambda _id: tmp_path / "unused.md",
        logger=brainstorm_conversation_service.logger,
    )

    assert result == {"error": "AI 回答生成失败: offline"}
    assert caplog.messages[-1] == (
        "Conversation message failed for question question-1: offline"
    )


def test_get_conversation_missing_question_and_malformed_refs_json() -> None:
    database = Database()
    with pytest.raises(HTTPException) as error:
        brainstorm_conversation_service.get_conversation(
            "missing", connect_fn=database.connect
        )
    assert (error.value.status_code, error.value.detail) == (404, "Question not found")

    database.execute(
        "INSERT INTO brainstorm_questions (id, question) VALUES (?, ?)",
        ("question-1", "问题"),
    )
    database.execute(
        "INSERT INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
        ("question-1", "event-a"),
    )
    for content, refs in (("bad", "{"), ("null", None), ("good", '["event-a"]')):
        database.execute(
            "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'assistant', ?, ?, ?)",
            ("question-1", content, refs, "2026-07-24 09:30"),
        )
    database.commit()
    database.clear_events()

    result = brainstorm_conversation_service.get_conversation(
        "question-1", connect_fn=database.connect
    )

    assert result == {
        "locked_event_ids": ["event-a"],
        "messages": [
            {
                "id": 1,
                "role": "assistant",
                "content": "bad",
                "refs": [],
                "created_at": "2026-07-24 09:30",
            },
            {
                "id": 2,
                "role": "assistant",
                "content": "null",
                "refs": [],
                "created_at": "2026-07-24 09:30",
            },
            {
                "id": 3,
                "role": "assistant",
                "content": "good",
                "refs": ["event-a"],
                "created_at": "2026-07-24 09:30",
            },
        ],
    }
    assert [event[1] for event in database.events if event[0] == "sql"] == [
        "SELECT id FROM brainstorm_questions WHERE id = ?",
        "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
        "SELECT id, role, content, refs_json, created_at FROM brainstorm_messages WHERE question_id = ? ORDER BY id ASC",
    ]


def test_summary_preconditions_cover_missing_question_documents_and_history() -> None:
    database = Database()
    dependencies = {
        "connect_fn": database.connect,
        "chat_fn": lambda *_args, **_kwargs: pytest.fail("chat should not be used"),
        "build_reference_docs_fn": lambda _ids: pytest.fail(
            "helper should not be used"
        ),
        "markdown_path_fn": lambda _id: pytest.fail("path should not be used"),
        "logger": brainstorm_conversation_service.logger,
    }
    with pytest.raises(HTTPException) as error:
        brainstorm_conversation_service.generate_conversation_summary(
            "missing", **dependencies
        )
    assert (error.value.status_code, error.value.detail) == (404, "Question not found")

    database.execute(
        "INSERT INTO brainstorm_questions (id, question) VALUES (?, ?)",
        ("question-1", "问题"),
    )
    database.commit()
    assert brainstorm_conversation_service.generate_conversation_summary(
        "question-1", **dependencies
    ) == {"error": "请先选择参考文档并开始对话"}

    database.execute(
        "INSERT INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
        ("question-1", "event-a"),
    )
    database.commit()
    history_dependencies = {
        **dependencies,
        "build_reference_docs_fn": lambda ids: (
            _docs() if ids == ["event-a"] else pytest.fail(str(ids))
        ),
    }
    assert brainstorm_conversation_service.generate_conversation_summary(
        "question-1", **history_dependencies
    ) == {"error": "没有对话历史可总结"}


def test_summary_preserves_concepts_prompt_ai_persistence_and_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(brainstorm_conversation_service, "datetime", FixedDateTime)
    database = Database()
    database.execute(
        "INSERT INTO brainstorm_questions (id, question, content_md) VALUES (?, ?, ?)",
        ("question-1", "原始问题", "old"),
    )
    database.execute(
        "INSERT INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
        ("question-1", "event-a"),
    )
    database.execute(
        "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, ?, ?, '[]', 'old')",
        ("question-1", "user", "首问"),
    )
    database.execute(
        "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, ?, ?, '[]', 'old')",
        ("question-1", "assistant", "首答 [文档1]"),
    )
    database.execute(
        "INSERT INTO events (id, title, ai_summary, content_type) VALUES (?, ?, ?, ?)",
        ("concept-1", "系统概念", "概念说明", "concept"),
    )
    database.execute(
        "INSERT INTO events (id, title, ai_summary, content_type) VALUES (?, ?, ?, ?)",
        ("concept-empty", "空概念", "", "concept"),
    )
    database.commit()
    database.clear_events()
    markdown = tmp_path / "question-1.md"
    markdown.write_text("existing\n", encoding="utf-8")
    chat_calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []

    def chat(messages: list[dict[str, str]], **kwargs: object) -> str:
        chat_calls.append((messages, kwargs))
        return "结构化总结 [文档1]"

    result = brainstorm_conversation_service.generate_conversation_summary(
        "question-1",
        connect_fn=database.connect,
        chat_fn=chat,
        build_reference_docs_fn=lambda ids: (
            _docs() if ids == ["event-a"] else pytest.fail(str(ids))
        ),
        markdown_path_fn=lambda _id: markdown,
        logger=brainstorm_conversation_service.logger,
    )

    assert chat_calls == [
        (
            [
                {
                    "role": "system",
                    "content": "你是严谨的研究总结助手，请基于对话和参考文档生成结构化总结。",
                },
                {"role": "user", "content": _summary_prompt()},
            ],
            {
                "temperature": 0.3,
                "max_tokens": 3000,
                "timeout": 120,
                "module": "brainstorm",
                "task": "summary",
            },
        )
    ]
    assert result == {
        "summary": "结构化总结 [文档1]",
        "refs": ["event-a"],
        "created_at": "2026-07-24 09:30",
    }
    assert markdown.read_text(encoding="utf-8") == (
        "existing\n## 总结 (2026-07-24 09:30)\n\n结构化总结 [文档1]\n\n---\n\n"
    )
    row = database.execute(
        "SELECT content_md, answer, summary_created_at FROM brainstorm_questions WHERE id = ?",
        ("question-1",),
    ).fetchone()
    assert tuple(row) == (
        markdown.read_text(encoding="utf-8"),
        "结构化总结 [文档1]",
        "2026-07-24 09:30",
    )
    assert [event for event in database.events if event[0] in {"enter", "exit"}] == [
        ("enter", 1),
        ("exit", 1),
        ("enter", 2),
        ("exit", 2),
        ("enter", 3),
        ("exit", 3),
        ("enter", 4),
        ("exit", 4),
    ]
    assert [event[1] for event in database.events if event[0] == "sql"] == [
        "SELECT id, question FROM brainstorm_questions WHERE id = ?",
        "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
        "SELECT role, content FROM brainstorm_messages WHERE question_id = ? ORDER BY id ASC",
        "SELECT title, ai_summary FROM events WHERE content_type = 'concept' AND ai_summary IS NOT NULL AND ai_summary != ''",
        "UPDATE brainstorm_questions SET content_md = ?, answer = ?, summary_created_at = ? WHERE id = ?",
    ]


def test_summary_with_no_concepts_and_no_reference_text_preserves_fallback_prompt(
    tmp_path: Path,
) -> None:
    database = Database()
    database.execute(
        "INSERT INTO brainstorm_questions (id, question) VALUES ('question-1', '问题')"
    )
    database.execute(
        "INSERT INTO brainstorm_event_links (question_id, event_id) VALUES ('question-1', 'event-a')"
    )
    database.execute(
        "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES ('question-1', 'user', '问题', '[]', 'old')"
    )
    database.commit()
    markdown = tmp_path / "question-1.md"
    markdown.write_text("", encoding="utf-8")
    captured: list[list[dict[str, str]]] = []

    def chat(messages: list[dict[str, str]], **_kwargs: object) -> str:
        captured.append(messages)
        return "总结"

    brainstorm_conversation_service.generate_conversation_summary(
        "question-1",
        connect_fn=database.connect,
        chat_fn=chat,
        build_reference_docs_fn=lambda _ids: ([], {}),
        markdown_path_fn=lambda _id: markdown,
        logger=brainstorm_conversation_service.logger,
    )

    assert "参考文档：\n\n\n系统已有概念：\n（暂无）" in captured[0][1]["content"]


def test_summary_ai_failure_preserves_error_and_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    database = Database()
    database.execute(
        "INSERT INTO brainstorm_questions (id, question) VALUES ('question-1', '问题')"
    )
    database.execute(
        "INSERT INTO brainstorm_event_links (question_id, event_id) VALUES ('question-1', 'event-a')"
    )
    database.execute(
        "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES ('question-1', 'user', '问题', '[]', 'old')"
    )
    database.commit()
    caplog.set_level(logging.WARNING, logger="zhiji_backend.routes.brainstorm_routes")

    result = brainstorm_conversation_service.generate_conversation_summary(
        "question-1",
        connect_fn=database.connect,
        chat_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("bad summary")
        ),
        build_reference_docs_fn=lambda _ids: _docs(),
        markdown_path_fn=lambda _id: tmp_path / "unused.md",
        logger=brainstorm_conversation_service.logger,
    )

    assert result == {"error": "AI 总结生成失败: bad summary"}
    assert caplog.messages[-1] == (
        "Summary generation failed for question question-1: bad summary"
    )


def test_conversation_dependencies_are_required_and_logger_is_historical() -> None:
    for function_name in (
        "start_conversation",
        "send_conversation_message",
        "generate_conversation_summary",
    ):
        parameters = inspect.signature(
            getattr(brainstorm_conversation_service, function_name)
        ).parameters
        assert tuple(parameters)[-5:] == (
            "connect_fn",
            "chat_fn",
            "build_reference_docs_fn",
            "markdown_path_fn",
            "logger",
        )
        assert all(
            parameters[name].default is inspect.Parameter.empty
            for name in tuple(parameters)[-5:]
        )
    assert tuple(
        inspect.signature(brainstorm_conversation_service.get_conversation).parameters
    ) == (
        "question_id",
        "connect_fn",
    )
    assert brainstorm_conversation_service.logger.name == (
        "zhiji_backend.routes.brainstorm_routes"
    )


def test_summary_prompt_registry_moves_owner_without_digest_or_task_drift() -> None:
    assert prompt_registry.MODULE_MAP["brainstorm"]["summary"] == (
        "brainstorm_conversation_service.py",
        ["generate_conversation_summary", "start_conversation"],
    )
    prompts = prompt_registry.get_all_prompts()["brainstorm"]
    expected_digests = {
        "answer": "62a22b6f6bdc260a7d4cb2693410027111b4f84e48b60d279c793273799afc2e",
        "summary": "13fc6ec7264b75b8461c69f44e0de44aaf73339682197ffbec2854492b6fb8be",
        "contemplate": "f75a1511dc8c491108bcfb7ca09414238cbecd3094b6672afd026e5bd59d00c3",
        "concept_extract": "577e63d9b7591a5884608f0714ea3bc9299c620822906f78ffb7c2fdc7a73745",
    }

    assert set(prompts) == set(expected_digests)
    for task, digest in expected_digests.items():
        payload = json.dumps(
            sorted(prompts[task].items()), ensure_ascii=False, separators=(",", ":")
        )
        assert hashlib.sha256(payload.encode()).hexdigest() == digest


def test_summary_registry_does_not_publish_follow_up_or_summary_prompt_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extract = prompt_registry._extract_prompts_by_function

    def extract_with_unrelated(path: Path) -> dict[str, dict[str, str]]:
        result = extract(path)
        result.setdefault("start_conversation", {})["unrelated_prompt"] = "private"
        result.setdefault("send_conversation_message", {})["system_prompt"] = "private"
        result.setdefault("generate_conversation_summary", {})["prompt"] = "private"
        return result

    monkeypatch.setattr(
        prompt_registry, "_extract_prompts_by_function", extract_with_unrelated
    )

    assert set(prompt_registry.get_all_prompts()["brainstorm"]["summary"]) == {
        "prompt",
        "system_prompt",
    }
