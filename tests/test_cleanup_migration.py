from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from zhiji_backend import migrations
from zhiji_backend.db import init_db
from zhiji_backend.migrations import ensure_migrations


RETIRED_TABLES = {
    "event_entities",
    "entity_relations",
    "entities",
    "digests",
    "topics",
}

ACTIVE_TABLES = (
    "sources",
    "events",
    "briefings",
    "series",
    "tasks",
    "study_materials",
)


def _schema_names(conn: sqlite3.Connection, object_type: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = ?", (object_type,)
        )
    }


def _create_populated_legacy_database(db_path, monkeypatch) -> dict[str, int]:
    monkeypatch.setenv("KI_DB_PATH", str(db_path))
    init_db()

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE entities (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              type TEXT NOT NULL
            );
            CREATE TABLE event_entities (
              event_id TEXT NOT NULL,
              entity_id TEXT NOT NULL
            );
            CREATE TABLE entity_relations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_entity_id TEXT NOT NULL,
              target_entity_id TEXT NOT NULL,
              relation_type TEXT NOT NULL
            );
            CREATE TABLE digests (
              date TEXT PRIMARY KEY,
              markdown TEXT NOT NULL
            );
            CREATE TABLE topics (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL
            );
            CREATE INDEX idx_entities_type ON entities(type);
            CREATE INDEX idx_entities_name ON entities(name);
            CREATE INDEX idx_event_entities_event ON event_entities(event_id);
            CREATE INDEX idx_event_entities_entity ON event_entities(entity_id);
            CREATE INDEX idx_entity_relations_src ON entity_relations(source_entity_id);
            CREATE INDEX idx_entity_relations_tgt ON entity_relations(target_entity_id);
            """
        )
        conn.execute(
            "INSERT INTO sources (id, name, type, url) VALUES (?, ?, ?, ?)",
            ("source-1", "Source", "rss", "https://example.com/feed"),
        )
        conn.execute(
            """
            INSERT INTO events (id, source_id, title, url)
            VALUES (?, ?, ?, ?)
            """,
            ("event-1", "source-1", "Active event", "https://example.com/event"),
        )
        conn.execute(
            "INSERT INTO briefings (id, type, topics_json) VALUES (?, ?, ?)",
            ("briefing-1", "quick", "[]"),
        )
        conn.execute(
            "INSERT INTO series (id, name) VALUES (?, ?)",
            ("series-1", "Active series"),
        )
        conn.execute(
            "INSERT INTO tasks (id, title) VALUES (?, ?)",
            ("task-1", "Active task"),
        )
        conn.execute(
            "INSERT INTO study_materials (id, title) VALUES (?, ?)",
            ("study-1", "Active study"),
        )
        conn.executemany(
            "INSERT INTO ai_usage (module, task, total_tokens) VALUES (?, ?, ?)",
            [
                ("knowledge_graph", "entity_insight", 10),
                ("digest_briefing", "digest", 20),
                ("briefing", "digest", 30),
                ("digest_briefing", "briefing_quick", 40),
                ("digest_briefing", "briefing_daily", 50),
                ("briefing", "briefing_quick", 60),
                ("series", "digest", 70),
                ("digest_briefing", None, 80),
            ],
        )

        conn.execute(
            "INSERT INTO entities (id, name, type) VALUES (?, ?, ?)",
            ("entity-1", "Retired entity", "concept"),
        )
        conn.execute(
            "INSERT INTO event_entities (event_id, entity_id) VALUES (?, ?)",
            ("event-1", "entity-1"),
        )
        conn.execute(
            """
            INSERT INTO entity_relations (source_entity_id, target_entity_id, relation_type)
            VALUES (?, ?, ?)
            """,
            ("entity-1", "entity-1", "claims"),
        )
        conn.execute(
            "INSERT INTO digests (date, markdown) VALUES (?, ?)",
            ("2026-07-19", "retired digest"),
        )
        conn.execute(
            "INSERT INTO topics (id, name) VALUES (?, ?)",
            ("topic-1", "Retired topic"),
        )

        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ACTIVE_TABLES
        }


def test_cleanup_migration_is_registered_on_import():
    assert "20260719_remove_retired_features" in {
        name for name, _migration in migrations._registry
    }


def test_cleanup_migration_drops_retired_schema_and_preserves_active_rows(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "intelligence.sqlite"
    active_counts = _create_populated_legacy_database(db_path, monkeypatch)

    ensure_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        assert RETIRED_TABLES.isdisjoint(_schema_names(conn, "table"))
        assert not any(
            name.startswith(
                ("idx_entities", "idx_event_entities", "idx_entity_relations")
            )
            for name in _schema_names(conn, "index")
        )
        assert {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ACTIVE_TABLES
        } == active_counts
        assert conn.execute(
            "SELECT module, task, total_tokens FROM ai_usage ORDER BY id"
        ).fetchall() == [
            ("briefing", "briefing_quick", 40),
            ("briefing", "briefing_daily", 50),
            ("briefing", "briefing_quick", 60),
            ("series", "digest", 70),
            ("digest_briefing", None, 80),
        ]


def test_each_migration_and_marker_roll_back_together(tmp_path, monkeypatch):
    db_path = tmp_path / "rollback.sqlite"

    def failing_migration(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE should_roll_back (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO should_roll_back (id) VALUES (1)")
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(
        migrations,
        "_registry",
        [("test_injected_failure", failing_migration)],
    )

    with pytest.raises(RuntimeError, match="injected migration failure"):
        ensure_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        assert "should_roll_back" not in _schema_names(conn, "table")
        assert conn.execute(
            "SELECT COUNT(*) FROM _migrations WHERE name = ?",
            ("test_injected_failure",),
        ).fetchone()[0] == 0


def test_cleanup_migration_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "idempotent.sqlite"
    _create_populated_legacy_database(db_path, monkeypatch)

    ensure_migrations(db_path)
    ensure_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM _migrations WHERE name = ?",
            ("20260719_remove_retired_features",),
        ).fetchone()[0] == 1
        assert RETIRED_TABLES.isdisjoint(_schema_names(conn, "table"))


def test_fresh_init_never_creates_retired_tables_or_indexes(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.sqlite"
    monkeypatch.setenv("KI_DB_PATH", str(db_path))

    init_db()

    with sqlite3.connect(db_path) as conn:
        assert RETIRED_TABLES.isdisjoint(_schema_names(conn, "table"))
        assert not any(
            name.startswith(
                ("idx_entities", "idx_event_entities", "idx_entity_relations")
            )
            for name in _schema_names(conn, "index")
        )
        assert {"events", "briefings", "ai_usage", "series"} <= _schema_names(
            conn, "table"
        )


def test_backup_database_includes_committed_wal_data_and_is_verified(tmp_path):
    from zhiji_backend.database_backup import backup_database

    source = tmp_path / "source.sqlite"
    output_dir = tmp_path / "backups"
    writer = sqlite3.connect(source)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE records (value TEXT NOT NULL)")
        writer.execute("INSERT INTO records (value) VALUES ('committed')")
        writer.commit()
        writer.execute("INSERT INTO records (value) VALUES ('uncommitted')")

        backup = backup_database(source, output_dir)
    finally:
        writer.rollback()
        writer.close()

    assert backup.parent == output_dir
    assert backup.name.startswith("intelligence-pre-cleanup-")
    assert backup.name.endswith(".sqlite")
    with sqlite3.connect(backup) as conn:
        assert conn.execute("SELECT value FROM records").fetchall() == [("committed",)]
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_backup_database_fails_when_source_is_missing(tmp_path):
    from zhiji_backend.database_backup import backup_database

    with pytest.raises(FileNotFoundError):
        backup_database(tmp_path / "missing.sqlite", tmp_path / "backups")


def test_backup_database_refuses_target_collision(tmp_path, monkeypatch):
    from zhiji_backend import database_backup

    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")

    class FrozenDateTime:
        @classmethod
        def now(cls):
            return datetime(2026, 7, 19, 12, 34, 56)

    monkeypatch.setattr(database_backup, "datetime", FrozenDateTime)
    output_dir = tmp_path / "backups"
    output_dir.mkdir()
    target = output_dir / "intelligence-pre-cleanup-20260719-123456.sqlite"
    target.write_bytes(b"existing backup")

    with pytest.raises(FileExistsError):
        database_backup.backup_database(source, output_dir)

    assert target.read_bytes() == b"existing backup"


def test_backup_database_deletes_target_when_integrity_verification_fails(
    tmp_path, monkeypatch
):
    from zhiji_backend import database_backup

    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")

    class FrozenDateTime:
        @classmethod
        def now(cls):
            return datetime(2026, 7, 19, 12, 34, 56)

    def fail_verification(_target):
        raise RuntimeError("backup integrity check failed")

    monkeypatch.setattr(database_backup, "datetime", FrozenDateTime)
    monkeypatch.setattr(database_backup, "_verify_backup", fail_verification)
    output_dir = tmp_path / "backups"
    target = output_dir / "intelligence-pre-cleanup-20260719-123456.sqlite"

    with pytest.raises(RuntimeError, match="backup integrity check failed"):
        database_backup.backup_database(source, output_dir)

    assert not target.exists()
