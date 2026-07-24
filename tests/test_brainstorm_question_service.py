from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

from zhiji_backend import brainstorm_question_service
from zhiji_backend.routes import brainstorm_routes


@contextmanager
def _connect(database: Path):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _create_schema(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE events (
                id TEXT PRIMARY KEY,
                title TEXT,
                title_cn TEXT,
                source_id TEXT,
                url TEXT
            );
            CREATE TABLE brainstorm_questions (
                id TEXT PRIMARY KEY,
                event_id TEXT,
                question TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                topic TEXT NOT NULL DEFAULT '',
                answer TEXT NOT NULL DEFAULT '',
                summary_created_at TEXT,
                content_md TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE brainstorm_event_links (
                question_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                PRIMARY KEY (question_id, event_id)
            );
            CREATE TABLE brainstorm_contemplate_cache (
                question_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                relevance TEXT NOT NULL,
                reason TEXT,
                PRIMARY KEY (question_id, event_id)
            );
            """
        )


def _connect_fn(database: Path):
    return lambda: _connect(database)


def test_list_questions_preserves_filters_order_pagination_and_limit_clamping(
    tmp_path: Path,
) -> None:
    database = tmp_path / "brainstorm.sqlite"
    _create_schema(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO events (id, title, title_cn, source_id, url) "
            "VALUES ('event-1', 'Title', '标题', 'source-1', 'https://example.test')"
        )
        connection.executemany(
            """INSERT INTO brainstorm_questions
               (id, event_id, question, status, created_at, topic)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                ("question-old", None, "old", "open", "2026-01-01", "认知"),
                (
                    "question-new",
                    "event-1",
                    "new",
                    "open",
                    "2026-01-03",
                    "认知",
                ),
                ("question-done", None, "done", "done", "2026-01-04", "认知"),
                ("question-other", None, "other", "open", "2026-01-05", "财富"),
            ],
        )
        connection.execute(
            "INSERT INTO brainstorm_event_links (question_id, event_id) "
            "VALUES ('question-new', 'event-1')"
        )

    result = brainstorm_question_service.list_brainstorm_questions(
        "open",
        "认知",
        0,
        1,
        connect_fn=_connect_fn(database),
        logger=logging.getLogger("test.brainstorm"),
    )

    assert result == {
        "questions": [
            {
                "id": "question-new",
                "event_id": "event-1",
                "question": "new",
                "status": "open",
                "created_at": "2026-01-03",
                "topic": "认知",
                "answered_event_ids": '["event-1"]',
                "title": "Title",
                "title_cn": "标题",
                "source_id": "source-1",
                "url": "https://example.test",
            }
        ]
    }
    assert (
        brainstorm_question_service.list_brainstorm_questions(
            "open",
            "认知",
            1,
            999,
            connect_fn=_connect_fn(database),
            logger=logging.getLogger("test.brainstorm"),
        )["questions"][0]["id"]
        == "question-old"
    )


def test_topic_counts_include_all_tabs_and_zero_counts(tmp_path: Path) -> None:
    database = tmp_path / "brainstorm.sqlite"
    _create_schema(database)
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO brainstorm_questions (id, question, topic) VALUES (?, ?, ?)",
            [
                ("question-1", "one", "格局"),
                ("question-2", "two", "认知"),
                ("question-3", "three", "认知"),
                ("question-4", "four", "other"),
            ],
        )

    assert brainstorm_question_service.brainstorm_topic_counts(
        connect_fn=_connect_fn(database),
        logger=logging.getLogger("test.brainstorm"),
    ) == {"格局": 1, "财富": 0, "认知": 2, "前瞻": 0}


def test_get_question_preserves_not_found_contract(tmp_path: Path) -> None:
    database = tmp_path / "brainstorm.sqlite"
    _create_schema(database)

    with pytest.raises(HTTPException) as exc_info:
        brainstorm_question_service.get_brainstorm_question(
            "missing",
            connect_fn=_connect_fn(database),
            markdown_path_fn=lambda question_id: tmp_path / f"{question_id}.md",
            logger=logging.getLogger("test.brainstorm"),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Question not found"


def test_get_question_serializes_links_and_judgments_and_reads_markdown(
    tmp_path: Path,
) -> None:
    database = tmp_path / "brainstorm.sqlite"
    _create_schema(database)
    markdown = tmp_path / "question-1.md"
    markdown.write_text("# 问题\n\n为什么？\n", encoding="utf-8")
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO brainstorm_questions
               (id, event_id, question, status, created_at, answer, summary_created_at)
               VALUES ('question-1', 'event-1', 'why', 'open', '2026-01-01',
                       'stored answer', '2026-01-02')"""
        )
        connection.executemany(
            "INSERT INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
            [("question-1", "event-1"), ("question-1", "event-2")],
        )
        connection.executemany(
            """INSERT INTO brainstorm_contemplate_cache
               (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)""",
            [
                ("question-1", "event-2", "高", "reason"),
                ("question-1", "event-3", "低", "reason"),
            ],
        )

    result = brainstorm_question_service.get_brainstorm_question(
        "question-1",
        connect_fn=_connect_fn(database),
        markdown_path_fn=lambda _question_id: markdown,
        logger=logging.getLogger("test.brainstorm"),
    )

    assert result == {
        "id": "question-1",
        "event_id": "event-1",
        "question": "why",
        "status": "open",
        "created_at": "2026-01-01",
        "answer": "stored answer",
        "summary_created_at": "2026-01-02",
        "answered_event_ids": '["event-1", "event-2"]',
        "judged_events": json.dumps(
            [
                {"event_id": "event-2", "relevance": "高"},
                {"event_id": "event-3", "relevance": "低"},
            ]
        ),
        "md_content": "# 问题\n\n为什么？\n",
    }


def test_create_question_preserves_write_order_content_and_classification() -> None:
    question_id = UUID("11111111-1111-1111-1111-111111111111")
    events: list[tuple[object, ...]] = []

    class RecordingConnection:
        def execute(self, sql, params=()):
            events.append(("sql", sql, params))

    class RecordingPath:
        def write_text(self, content: str, *, encoding: str) -> None:
            events.append(("write", content, encoding))

    @contextmanager
    def connect_fn():
        yield RecordingConnection()

    def classify(question: str, content: str) -> str:
        events.append(("classify", question, content))
        return "前瞻"

    result = brainstorm_question_service.create_brainstorm_question(
        SimpleNamespace(question="未来如何？"),
        connect_fn=connect_fn,
        classify_fn=classify,
        markdown_path_fn=lambda _question_id: RecordingPath(),
        uuid_fn=lambda: question_id,
        now_fn=lambda: SimpleNamespace(strftime=lambda _format: "2026-07-24 09:30"),
        logger=logging.getLogger("test.brainstorm"),
    )
    markdown = "# 问题\n\n未来如何？\n\n创建时间：2026-07-24 09:30\n\n---\n\n"

    assert result == {
        "ok": True,
        "id": str(question_id),
        "question": "未来如何？",
        "topic": "前瞻",
    }
    assert events == [
        (
            "sql",
            "INSERT INTO brainstorm_questions (id, event_id, question) VALUES (?, '', ?)",
            (str(question_id), "未来如何？"),
        ),
        ("write", markdown, "utf-8"),
        (
            "sql",
            "UPDATE brainstorm_questions SET content_md = ? WHERE id = ?",
            (markdown, str(question_id)),
        ),
        ("classify", "未来如何？", ""),
        (
            "sql",
            "UPDATE brainstorm_questions SET topic = ? WHERE id = ?",
            ("前瞻", str(question_id)),
        ),
    ]


def test_create_question_keeps_default_topic_when_classification_fails(
    tmp_path: Path,
) -> None:
    database = tmp_path / "brainstorm.sqlite"
    _create_schema(database)
    question_id = UUID("22222222-2222-2222-2222-222222222222")

    result = brainstorm_question_service.create_brainstorm_question(
        SimpleNamespace(question="fallback"),
        connect_fn=_connect_fn(database),
        classify_fn=lambda *_args: (_ for _ in ()).throw(RuntimeError("offline")),
        markdown_path_fn=lambda qid: tmp_path / f"{qid}.md",
        uuid_fn=lambda: question_id,
        now_fn=lambda: SimpleNamespace(strftime=lambda _format: "2026-07-24 09:30"),
        logger=logging.getLogger("test.brainstorm"),
    )

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT question, topic, content_md FROM brainstorm_questions WHERE id = ?",
            (str(question_id),),
        ).fetchone()
    assert result == {
        "ok": True,
        "id": str(question_id),
        "question": "fallback",
        "topic": "认知",
    }
    assert row is not None
    assert row[0] == "fallback"
    assert row[1] == ""
    assert row[2] == (tmp_path / f"{question_id}.md").read_text(encoding="utf-8")


def test_single_and_batch_delete_preserve_missing_and_unlink_behavior(
    tmp_path: Path,
) -> None:
    database = tmp_path / "brainstorm.sqlite"
    _create_schema(database)
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO brainstorm_questions (id, question) VALUES (?, ?)",
            [
                ("question-1", "one"),
                ("question-2", "two"),
                ("question-3", "three"),
            ],
        )
    unlinked: list[str] = []

    assert brainstorm_question_service.delete_brainstorm_question(
        "question-1",
        connect_fn=_connect_fn(database),
        unlink_fn=unlinked.append,
        logger=logging.getLogger("test.brainstorm"),
    ) == {"ok": True, "deleted": "question-1"}
    with pytest.raises(HTTPException) as exc_info:
        brainstorm_question_service.delete_brainstorm_question(
            "missing",
            connect_fn=_connect_fn(database),
            unlink_fn=unlinked.append,
            logger=logging.getLogger("test.brainstorm"),
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Question not found"

    assert brainstorm_question_service.batch_delete_brainstorm_questions(
        SimpleNamespace(question_ids=["question-2", "missing", "question-3"]),
        connect_fn=_connect_fn(database),
        unlink_fn=unlinked.append,
        logger=logging.getLogger("test.brainstorm"),
    ) == {"ok": True, "deleted": 2}
    assert unlinked == ["question-1", "question-2", "question-3"]
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT id FROM brainstorm_questions ORDER BY id"
            ).fetchall()
            == []
        )


def test_delete_uses_safe_facade_and_preserves_unsafe_artifact_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    database = tmp_path / "brainstorm.sqlite"
    _create_schema(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO brainstorm_questions (id, question) VALUES ('question-1', 'one')"
        )
    brainstorm_root = tmp_path / "brainstorm"
    brainstorm_root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("keep", encoding="utf-8")
    (brainstorm_root / "question-1.md").symlink_to(outside)
    monkeypatch.setattr(brainstorm_routes, "BRAINSTORM_DIR", brainstorm_root)

    with caplog.at_level(
        logging.WARNING, logger="zhiji_backend.routes.brainstorm_routes"
    ):
        result = brainstorm_question_service.delete_brainstorm_question(
            "question-1",
            connect_fn=_connect_fn(database),
            unlink_fn=brainstorm_routes._safe_brainstorm_unlink,
            logger=brainstorm_routes.logger,
        )

    assert result == {"ok": True, "deleted": "question-1"}
    assert outside.read_text(encoding="utf-8") == "keep"
    assert "Refusing to delete unsafe brainstorm artifact" in caplog.text
    assert {record.name for record in caplog.records} == {
        "zhiji_backend.routes.brainstorm_routes"
    }


def test_mark_done_updates_existing_and_preserves_not_found_contract(
    tmp_path: Path,
) -> None:
    database = tmp_path / "brainstorm.sqlite"
    _create_schema(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO brainstorm_questions (id, question) VALUES ('question-1', 'one')"
        )

    assert brainstorm_question_service.mark_brainstorm_done(
        "question-1",
        connect_fn=_connect_fn(database),
        logger=logging.getLogger("test.brainstorm"),
    ) == {"ok": True, "id": "question-1", "status": "done"}
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT status FROM brainstorm_questions WHERE id = 'question-1'"
            ).fetchone()[0]
            == "done"
        )

    with pytest.raises(HTTPException) as exc_info:
        brainstorm_question_service.mark_brainstorm_done(
            "missing",
            connect_fn=_connect_fn(database),
            logger=logging.getLogger("test.brainstorm"),
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Question not found"
