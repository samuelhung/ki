from __future__ import annotations

import importlib
import json
import sqlite3
from contextlib import nullcontext
from contextvars import Context
from pathlib import Path
from types import ModuleType

import pytest

from zhiji_backend import db

FIXTURE_DIR = Path(__file__).with_name("fixtures")


def _db_modules() -> tuple[ModuleType, ModuleType]:
    return (
        importlib.import_module("zhiji_backend.db_schema"),
        importlib.import_module("zhiji_backend.db_migrations"),
    )


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _original_script_fixture(name: str, *, closing_indent: int) -> str:
    lines = (FIXTURE_DIR / name).read_text(encoding="utf-8").splitlines()
    indented = "\n".join(f"            {line}" if line else "" for line in lines)
    return f"\n{indented}\n{' ' * closing_indent}"


def test_schema_sql_is_immutable_and_repeated_initialization_is_idempotent(
    tmp_path, monkeypatch
) -> None:
    db_schema, _db_migrations = _db_modules()
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "fresh.sqlite"))

    assert isinstance(db_schema.SCHEMA_SCRIPTS, tuple)
    assert isinstance(db_schema.INDEX_SCRIPTS, tuple)

    db.init_db()
    db.init_db()

    with db.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        triggers = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }

    assert {
        "sources",
        "events",
        "events_fts",
        "brainstorm_questions",
        "brainstorm_event_links",
        "brainstorm_messages",
        "ingest_tasks",
        "tasks",
        "series",
        "ai_usage",
        "study_materials",
        "industry_chain_nodes",
        "chain_data_hints",
        "chain_suggestions",
        "chain_reports",
        "chain_meta",
    } <= tables
    assert {
        "idx_events_translation_status",
        "idx_brainstorm_messages_question",
        "idx_study_created",
    } <= indexes
    assert triggers == {
        "trg_events_fts_insert",
        "trg_events_fts_delete",
        "trg_events_fts_update",
    }


def test_fresh_database_preserves_readable_exact_ddl_and_catalog_order(
    tmp_path, monkeypatch
) -> None:
    db_schema, _db_migrations = _db_modules()
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "exact-schema.sqlite"))

    assert db_schema.SCHEMA_SCRIPTS == (
        _original_script_fixture("db_schema.sql", closing_indent=12),
    )
    assert db_schema.INDEX_SCRIPTS == (
        _original_script_fixture("db_indexes.sql", closing_indent=8),
    )

    db.init_db()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY rowid"
        ).fetchall()
    actual_catalog = [
        {"type": row[0], "name": row[1], "table": row[2], "sql": row[3]}
        for row in rows
    ]
    expected_catalog = json.loads(
        (FIXTURE_DIR / "db_catalog.json").read_text(encoding="utf-8")
    )

    assert actual_catalog == expected_catalog


def test_direct_run_migrations_resolves_local_steps_at_call_time(monkeypatch) -> None:
    db_schema, db_migrations = _db_modules()
    calls: list[str] = []
    migration_names = (
        "_migrate_events_cn",
        "_migrate_brainstorm",
        "_migrate_series",
        "_migrate_ingest_tasks_retry",
        "_migrate_video_md5",
        "_migrate_textbook",
        "_migrate_lessons_json",
        "_migrate_chain_reports",
        "_migrate_chain_meta",
        "_backfill_fts",
    )
    for name in migration_names:
        monkeypatch.setattr(
            db_migrations, name, lambda _conn, name=name: calls.append(name)
        )
    monkeypatch.setattr(
        db_schema, "create_indexes", lambda _conn: calls.append("create_indexes")
    )

    db_migrations.run_migrations(object())

    assert calls == [
        *migration_names[:5],
        "create_indexes",
        *migration_names[5:],
    ]


def test_all_legacy_migrations_and_fts_backfill_are_idempotent(tmp_path) -> None:
    db_schema, db_migrations = _db_modules()
    db_path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(
            """
            CREATE TABLE sources (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
              url TEXT NOT NULL
            );
            CREATE TABLE events (
              id TEXT PRIMARY KEY, source_id TEXT NOT NULL, title TEXT NOT NULL,
              url TEXT NOT NULL, raw_summary TEXT, ai_summary TEXT,
              topic TEXT, status TEXT NOT NULL DEFAULT 'new',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE brainstorm_questions (
              id TEXT PRIMARY KEY, event_id TEXT, question TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'open',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              answered_event_ids TEXT
            );
            CREATE TABLE ingest_tasks (
              id TEXT PRIMARY KEY, event_id TEXT NOT NULL,
              ingest_type TEXT NOT NULL, payload_json TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE series (
              id TEXT PRIMARY KEY, name TEXT NOT NULL
            );
            CREATE TABLE study_materials (
              id TEXT PRIMARY KEY, subject TEXT NOT NULL DEFAULT '',
              study_type TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
              status TEXT DEFAULT 'draft',
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE chain_meta (
              chain_name TEXT PRIMARY KEY, icon TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO sources VALUES ('source-1', 'Source', 'rss', 'https://example.com');
            INSERT INTO events VALUES (
              'event-1', 'source-1', 'Legacy title', 'https://example.com/event',
              'Legacy summary', 'AI summary', 'tech-ai', 'new', CURRENT_TIMESTAMP
            );
            INSERT INTO brainstorm_questions
              VALUES (
                'question-1', 'event-1', 'Legacy question', 'open',
                CURRENT_TIMESTAMP, '["event-1"]'
              );
            """
        )

        db_schema.create_schema(conn)
        db_migrations.run_migrations(conn)
        db_migrations.run_migrations(conn)

        assert {
            "title_cn",
            "summary_cn",
            "translation_status",
            "translation_error",
            "last_error",
            "progress_stages",
            "video_path",
            "audio_path",
            "document_path",
            "content_type",
            "overview",
            "last_discovered_at",
            "suggested_series_json",
            "chain_analysis",
            "video_md5",
        } <= _column_names(conn, "events")
        assert {"content_md", "topic", "answer", "summary_created_at"} <= (
            _column_names(conn, "brainstorm_questions")
        )
        assert {"intro", "updated_at", "summary"} <= _column_names(conn, "series")
        assert "retry_count" in _column_names(conn, "ingest_tasks")
        assert {"textbook", "lessons_json"} <= _column_names(conn, "study_materials")
        assert "flow_summary" in _column_names(conn, "chain_meta")
        assert [
            tuple(row)
            for row in conn.execute(
                "SELECT event_id FROM brainstorm_event_links"
            ).fetchall()
        ] == [("event-1",)]
        assert [
            tuple(row)
            for row in conn.execute("SELECT event_id, title FROM events_fts").fetchall()
        ] == [("event-1", "Legacy title")]
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'chain_reports'"
        ).fetchone()
    finally:
        conn.close()


def test_pre_index_migration_failure_rolls_back_pending_dml(
    monkeypatch,
) -> None:
    _db_schema, db_migrations = _db_modules()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE brainstorm_questions (
          id TEXT PRIMARY KEY, question TEXT NOT NULL, answered_event_ids TEXT
        );
        CREATE TABLE brainstorm_event_links (
          question_id TEXT NOT NULL, event_id TEXT NOT NULL,
          PRIMARY KEY (question_id, event_id)
        );
        CREATE TABLE brainstorm_messages (
          id INTEGER PRIMARY KEY, question_id TEXT NOT NULL
        );
        INSERT INTO brainstorm_questions
          VALUES ('question-1', 'Legacy question', '["event-1"]');
        """
    )
    monkeypatch.setattr(db_migrations, "_migrate_events_cn", lambda _conn: None)
    monkeypatch.setattr(
        db_migrations,
        "_migrate_series",
        lambda _conn: (_ for _ in ()).throw(RuntimeError("migration failed")),
    )

    with pytest.raises(RuntimeError, match="migration failed"):
        with conn:
            db_migrations.run_migrations(conn)

    assert conn.execute("SELECT * FROM brainstorm_event_links").fetchall() == []
    conn.close()


def test_post_index_failure_preserves_pre_index_work_committed_by_executescript(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "post-index-failure.sqlite"
    monkeypatch.setenv("KI_DB_PATH", str(db_path))
    db.init_db()
    with db.connect() as conn:
        conn.execute(
            "ALTER TABLE brainstorm_questions ADD COLUMN answered_event_ids TEXT"
        )
        conn.execute(
            "INSERT INTO sources (id, name, type, url) VALUES (?, ?, ?, ?)",
            ("source-1", "Source", "rss", "https://example.com/feed"),
        )
        conn.execute(
            "INSERT INTO events (id, source_id, title, url) VALUES (?, ?, ?, ?)",
            ("event-1", "source-1", "Event", "https://example.com/event"),
        )
        conn.execute(
            "INSERT INTO brainstorm_questions "
            "(id, question, answered_event_ids) VALUES (?, ?, ?)",
            ("question-1", "Question", '["event-1"]'),
        )
        conn.execute("DROP INDEX idx_events_status")
    monkeypatch.setattr(
        db,
        "_migrate_textbook",
        lambda _conn: (_ for _ in ()).throw(RuntimeError("post-index failure")),
    )

    with pytest.raises(RuntimeError, match="post-index failure"):
        db.init_db()

    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT question_id, event_id FROM brainstorm_event_links"
        ).fetchall() == [("question-1", "event-1")]
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND name = 'idx_events_status'"
        ).fetchone() == ("idx_events_status",)


def _recording_steps(db_migrations, label: str, calls: list[str], logger) -> object:
    def record(_conn) -> None:
        calls.append(label)

    return db_migrations.MigrationSteps(
        migrate_events_cn=record,
        migrate_brainstorm=record,
        migrate_brainstorm_answers_to_messages=record,
        migrate_series=record,
        migrate_ingest_tasks_retry=record,
        migrate_video_md5=record,
        migrate_textbook=record,
        migrate_lessons_json=record,
        migrate_chain_reports=record,
        migrate_chain_meta=record,
        backfill_fts=record,
        logger=logger,
    )


def test_scoped_migration_steps_do_not_leak_across_contexts(monkeypatch) -> None:
    db_schema, db_migrations = _db_modules()
    calls: list[str] = []
    logger = object()
    scoped_steps = _recording_steps(db_migrations, "scoped", calls, logger)
    monkeypatch.setattr(db_schema, "create_indexes", lambda _conn: None)
    for name in (
        "_migrate_events_cn",
        "_migrate_brainstorm",
        "_migrate_series",
        "_migrate_ingest_tasks_retry",
        "_migrate_video_md5",
        "_migrate_textbook",
        "_migrate_lessons_json",
        "_migrate_chain_reports",
        "_migrate_chain_meta",
        "_backfill_fts",
    ):
        monkeypatch.setattr(
            db_migrations, name, lambda _conn: calls.append("default")
        )

    with db_migrations.migration_steps_scope(scoped_steps):
        db_migrations.run_migrations(object())
        Context().run(db_migrations.run_migrations, object())
    db_migrations.run_migrations(object())

    assert calls == ["scoped"] * 10 + ["default"] * 10 + ["default"] * 10


def test_scoped_logger_is_used_without_reverse_facade_import(monkeypatch) -> None:
    _db_schema, db_migrations = _db_modules()
    messages: list[tuple[str, tuple[object, ...]]] = []

    class LoggerSpy:
        def info(self, message: str, *args: object) -> None:
            messages.append((message, args))

    class ConnectionSpy:
        def execute(self, sql: str):
            class CursorSpy:
                @staticmethod
                def fetchall() -> list[object]:
                    return []

            return CursorSpy()

    steps = _recording_steps(db_migrations, "unused", [], LoggerSpy())
    with db_migrations.migration_steps_scope(steps):
        db_migrations._migrate_ingest_tasks_retry(ConnectionSpy())

    assert messages == [
        ("Migration: added retry_count column to ingest_tasks", ()),
    ]


def test_init_db_captures_facade_logger_at_call_time(monkeypatch) -> None:
    db_schema, db_migrations = _db_modules()
    messages: list[tuple[str, tuple[object, ...]]] = []

    class LoggerSpy:
        def info(self, message: str, *args: object) -> None:
            messages.append((message, args))

    class ConnectionSpy:
        def execute(self, sql: str):
            class CursorSpy:
                @staticmethod
                def fetchall() -> list[object]:
                    return []

            return CursorSpy()

    monkeypatch.setattr(db, "connect", lambda **_kwargs: nullcontext(ConnectionSpy()))
    monkeypatch.setattr(db_schema, "create_schema", lambda _conn: None)
    monkeypatch.setattr(db_schema, "create_indexes", lambda _conn: None)
    for name in (
        "_migrate_events_cn",
        "_migrate_brainstorm",
        "_migrate_series",
        "_migrate_video_md5",
        "_migrate_textbook",
        "_migrate_lessons_json",
        "_migrate_chain_reports",
        "_migrate_chain_meta",
        "_backfill_fts",
    ):
        monkeypatch.setattr(db, name, lambda _conn: None)
    monkeypatch.setattr(
        db, "_migrate_ingest_tasks_retry", db_migrations._migrate_ingest_tasks_retry
    )
    monkeypatch.setattr(db, "logger", LoggerSpy())

    db.init_db()

    assert messages == [
        ("Migration: added retry_count column to ingest_tasks", ()),
    ]


def test_legacy_markdown_answer_migration_preserves_content_metadata_and_order(
    tmp_path, monkeypatch
) -> None:
    from zhiji_backend import paths

    db_path = tmp_path / "brainstorm-legacy.sqlite"
    monkeypatch.setenv("KI_DB_PATH", str(db_path))
    monkeypatch.setattr(paths, "BRAINSTORM_DIR", tmp_path)
    db.init_db()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, url) VALUES (?, ?, ?, ?)",
            ("source-1", "Source", "rss", "https://example.com/feed"),
        )
        conn.execute(
            "INSERT INTO events (id, source_id, title, url) VALUES (?, ?, ?, ?)",
            ("event-1", "source-1", "Event", "https://example.com/event"),
        )
        conn.execute(
            "INSERT INTO brainstorm_questions (id, question) VALUES (?, ?)",
            ("question-1", "Legacy question"),
        )
        conn.execute(
            "INSERT INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
            ("question-1", "event-1"),
        )
    (tmp_path / "question-1.md").write_text(
        "# Legacy question\n\nCreated at: 2026-06-08\n\n---\n\n"
        "## 回答 (2026-06-08 17:00)\n\nLegacy answer\n\nSecond paragraph\n",
        encoding="utf-8",
    )

    db.init_db()
    db.init_db()

    with db.connect() as conn:
        messages = conn.execute(
            "SELECT role, content, refs_json, created_at FROM brainstorm_messages "
            "WHERE question_id = ? ORDER BY id",
            ("question-1",),
        ).fetchall()

    assert [row["role"] for row in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "Legacy question"
    assert messages[0]["refs_json"] == "[]"
    assert messages[1]["content"] == "Legacy answer\n\nSecond paragraph"
    assert json.loads(messages[1]["refs_json"]) == ["event-1"]
    assert messages[1]["created_at"] == "2026-06-08 17:00:00"
