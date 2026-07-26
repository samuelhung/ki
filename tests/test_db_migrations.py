from __future__ import annotations

import importlib
import sqlite3
from types import ModuleType

import pytest

from zhiji_backend import db


def _db_modules() -> tuple[ModuleType, ModuleType]:
    return (
        importlib.import_module("zhiji_backend.db_schema"),
        importlib.import_module("zhiji_backend.db_migrations"),
    )


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


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


def test_run_migrations_preserves_the_existing_order(monkeypatch) -> None:
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


def test_partial_migration_rolls_back_with_the_connection_transaction(
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
