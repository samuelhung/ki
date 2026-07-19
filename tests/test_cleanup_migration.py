from __future__ import annotations

import os
import sqlite3
import stat
import threading
import time
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

BACKUP_TEMP_PREFIX = ".intelligence-backup-"


def _schema_names(conn: sqlite3.Connection, object_type: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = ?", (object_type,)
        )
    }


def _backup_temp_dirs(output_dir) -> list:
    if not output_dir.exists():
        return []
    return [
        path
        for path in output_dir.iterdir()
        if path.name.startswith(BACKUP_TEMP_PREFIX)
    ]


def _freeze_backup_timestamp(monkeypatch, database_backup) -> None:
    class FrozenDateTime:
        @classmethod
        def now(cls):
            return datetime(2026, 7, 19, 12, 34, 56)

    monkeypatch.setattr(database_backup, "datetime", FrozenDateTime)


def _create_populated_legacy_database(db_path, monkeypatch) -> dict[str, int]:
    monkeypatch.setenv("KI_DB_PATH", str(db_path))
    init_db()

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(
            """
            CREATE TABLE entities (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              type TEXT NOT NULL
            );
            CREATE TABLE event_entities (
              event_id TEXT NOT NULL,
              entity_id TEXT NOT NULL,
              FOREIGN KEY (event_id) REFERENCES events(id),
              FOREIGN KEY (entity_id) REFERENCES entities(id)
            );
            CREATE TABLE entity_relations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_entity_id TEXT NOT NULL,
              target_entity_id TEXT NOT NULL,
              relation_type TEXT NOT NULL,
              FOREIGN KEY (source_entity_id) REFERENCES entities(id),
              FOREIGN KEY (target_entity_id) REFERENCES entities(id)
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


def test_register_rejects_duplicate_migration_names(monkeypatch):
    def migration(_conn: sqlite3.Connection) -> None:
        pass

    monkeypatch.setattr(
        migrations,
        "_registry",
        [("20260719_existing", migration)],
    )

    with pytest.raises(ValueError, match="duplicate migration name"):
        migrations.register("20260719_existing")(migration)

    assert migrations._registry == [("20260719_existing", migration)]


def test_register_rejects_non_increasing_migration_names(monkeypatch):
    def migration(_conn: sqlite3.Connection) -> None:
        pass

    monkeypatch.setattr(
        migrations,
        "_registry",
        [("20260719_existing", migration)],
    )

    with pytest.raises(ValueError, match="chronological order"):
        migrations.register("20260718_older")(migration)

    assert migrations._registry == [("20260719_existing", migration)]


def test_register_accepts_strictly_increasing_migration_names(monkeypatch):
    def migration(_conn: sqlite3.Connection) -> None:
        pass

    monkeypatch.setattr(
        migrations,
        "_registry",
        [("20260718_existing", migration)],
    )

    migrations.register("20260719_newer")(migration)

    assert migrations._registry == [
        ("20260718_existing", migration),
        ("20260719_newer", migration),
    ]


def test_cleanup_migration_drops_retired_schema_and_preserves_active_rows(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "intelligence.sqlite"
    active_counts = _create_populated_legacy_database(db_path, monkeypatch)

    ensure_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
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
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


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


def test_concurrent_migration_runners_retry_lock_and_execute_body_once(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "concurrent.sqlite"
    monkeypatch.setattr(migrations, "_registry", [])
    ensure_migrations(db_path)

    body_lock = threading.Lock()
    body_calls = 0
    retry_observed = threading.Event()

    def counted_migration(conn: sqlite3.Connection) -> None:
        nonlocal body_calls
        with body_lock:
            body_calls += 1
            call_number = body_calls
        if call_number == 1:
            assert retry_observed.wait(timeout=1)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS migration_effects (id INTEGER PRIMARY KEY)"
        )
        conn.execute("INSERT INTO migration_effects DEFAULT VALUES")

    monkeypatch.setattr(
        migrations,
        "_registry",
        [("20260720_concurrent_test", counted_migration)],
    )

    precheck_barrier = threading.Barrier(2)
    real_connect = migrations.sqlite3.connect

    class TrackingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql.strip() == "SELECT name FROM _migrations":
                precheck_barrier.wait(timeout=5)
            return super().execute(sql, parameters)

    def tracked_connect(*args, **kwargs):
        kwargs["factory"] = TrackingConnection
        return real_connect(*args, **kwargs)

    real_sleep = time.sleep

    def observe_retry(delay: float) -> None:
        retry_observed.set()
        real_sleep(delay)

    monkeypatch.setattr(migrations, "MIGRATION_BUSY_TIMEOUT_MS", 20, raising=False)
    monkeypatch.setattr(
        migrations, "MIGRATION_LOCK_RETRY_SECONDS", 1.0, raising=False
    )
    monkeypatch.setattr(
        migrations, "MIGRATION_LOCK_RETRY_INITIAL_DELAY_SECONDS", 0.01, raising=False
    )
    monkeypatch.setattr(
        migrations, "MIGRATION_LOCK_RETRY_MAX_DELAY_SECONDS", 0.05, raising=False
    )
    monkeypatch.setattr(migrations, "_sleep", observe_retry, raising=False)
    monkeypatch.setattr(migrations.sqlite3, "connect", tracked_connect)
    start_barrier = threading.Barrier(3)
    errors = []

    def run_migrations() -> None:
        start_barrier.wait(timeout=5)
        try:
            ensure_migrations(db_path)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run_migrations) for _ in range(2)]
    for thread in threads:
        thread.start()
    start_barrier.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert retry_observed.is_set()
    assert body_calls == 1
    with real_connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM migration_effects").fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM _migrations WHERE name = ?",
            ("20260720_concurrent_test",),
        ).fetchone()[0] == 1


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


def test_backup_database_rejects_symlink_source(tmp_path):
    from zhiji_backend.database_backup import backup_database

    real_source = tmp_path / "real.sqlite"
    source = tmp_path / "source.sqlite"
    with sqlite3.connect(real_source) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
    source.symlink_to(real_source)
    output_dir = tmp_path / "backups"

    with pytest.raises(RuntimeError, match="regular non-symlink"):
        backup_database(source, output_dir)

    assert not output_dir.exists()


def test_backup_database_detects_source_replacement_before_connect(
    tmp_path, monkeypatch
):
    from zhiji_backend import database_backup

    source = tmp_path / "source.sqlite"
    replacement = tmp_path / "replacement.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.execute("INSERT INTO records VALUES ('original')")
    with sqlite3.connect(replacement) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.execute("INSERT INTO records VALUES ('replacement')")

    _freeze_backup_timestamp(monkeypatch, database_backup)
    source_uri = source.resolve().as_uri()
    real_connect = database_backup.sqlite3.connect
    swapped = False

    def replace_before_connect(database, *args, **kwargs):
        nonlocal swapped
        if not swapped and kwargs.get("uri") and str(database).startswith(source_uri):
            os.replace(replacement, source)
            swapped = True
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(database_backup.sqlite3, "connect", replace_before_connect)
    output_dir = tmp_path / "backups"
    target = output_dir / "intelligence-pre-cleanup-20260719-123456.sqlite"

    with pytest.raises(RuntimeError, match="source identity changed"):
        database_backup.backup_database(source, output_dir)

    assert swapped
    assert not target.exists()
    assert _backup_temp_dirs(output_dir) == []


def test_backup_database_detects_source_replacement_during_backup(
    tmp_path, monkeypatch
):
    from zhiji_backend import database_backup

    source = tmp_path / "source.sqlite"
    replacement = tmp_path / "replacement.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.execute("INSERT INTO records VALUES ('original')")
    with sqlite3.connect(replacement) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.execute("INSERT INTO records VALUES ('replacement')")

    _freeze_backup_timestamp(monkeypatch, database_backup)
    source_uri = source.resolve().as_uri()
    real_connect = database_backup.sqlite3.connect
    swapped = False

    class ReplacingSourceConnection:
        def __init__(self, conn):
            self._conn = conn

        def __enter__(self):
            self._conn.__enter__()
            return self

        def __exit__(self, exc_type, exc, traceback):
            return self._conn.__exit__(exc_type, exc, traceback)

        def backup(self, target_conn):
            nonlocal swapped
            os.replace(replacement, source)
            swapped = True
            return self._conn.backup(target_conn)

    def replace_during_backup(database, *args, **kwargs):
        conn = real_connect(database, *args, **kwargs)
        if kwargs.get("uri") and str(database).startswith(source_uri):
            return ReplacingSourceConnection(conn)
        return conn

    monkeypatch.setattr(database_backup.sqlite3, "connect", replace_during_backup)
    output_dir = tmp_path / "backups"
    target = output_dir / "intelligence-pre-cleanup-20260719-123456.sqlite"

    with pytest.raises(RuntimeError, match="source identity changed"):
        database_backup.backup_database(source, output_dir)

    assert swapped
    assert not target.exists()
    assert _backup_temp_dirs(output_dir) == []


def test_backup_database_refuses_target_collision(tmp_path, monkeypatch):
    from zhiji_backend import database_backup

    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")

    _freeze_backup_timestamp(monkeypatch, database_backup)
    output_dir = tmp_path / "backups"
    output_dir.mkdir()
    target = output_dir / "intelligence-pre-cleanup-20260719-123456.sqlite"
    target.write_bytes(b"existing backup")

    with pytest.raises(FileExistsError):
        database_backup.backup_database(source, output_dir)

    assert target.read_bytes() == b"existing backup"
    assert _backup_temp_dirs(output_dir) == []


def test_backup_database_never_follows_preexisting_target_symlink(
    tmp_path, monkeypatch
):
    from zhiji_backend import database_backup

    source = tmp_path / "source.sqlite"
    victim = tmp_path / "victim.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.execute("INSERT INTO records VALUES ('source')")
    with sqlite3.connect(victim) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.execute("INSERT INTO records VALUES ('victim')")

    _freeze_backup_timestamp(monkeypatch, database_backup)
    output_dir = tmp_path / "backups"
    output_dir.mkdir()
    target = output_dir / "intelligence-pre-cleanup-20260719-123456.sqlite"
    target.symlink_to(victim)

    with pytest.raises(FileExistsError):
        database_backup.backup_database(source, output_dir)

    assert target.is_symlink()
    with sqlite3.connect(victim) as conn:
        assert conn.execute("SELECT value FROM records").fetchall() == [("victim",)]
    assert _backup_temp_dirs(output_dir) == []


def test_backup_database_does_not_follow_replaced_target_during_copy(
    tmp_path, monkeypatch
):
    from zhiji_backend import database_backup

    source = tmp_path / "source.sqlite"
    victim = tmp_path / "victim.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.execute("INSERT INTO records VALUES ('source')")
    with sqlite3.connect(victim) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.execute("INSERT INTO records VALUES ('victim')")

    _freeze_backup_timestamp(monkeypatch, database_backup)
    output_dir = tmp_path / "backups"
    output_dir.mkdir()
    target = output_dir / "intelligence-pre-cleanup-20260719-123456.sqlite"
    real_connect = database_backup.sqlite3.connect
    attacked = False

    def replace_final_on_source_open(database, *args, **kwargs):
        nonlocal attacked
        database_text = str(database)
        if not attacked and (
            database_text == str(source)
            or database_text.startswith(source.resolve().as_uri())
        ):
            target.unlink(missing_ok=True)
            target.symlink_to(victim)
            attacked = True
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(database_backup.sqlite3, "connect", replace_final_on_source_open)

    with pytest.raises(FileExistsError):
        database_backup.backup_database(source, output_dir)

    assert attacked
    assert target.is_symlink()
    with real_connect(victim) as conn:
        assert conn.execute("SELECT value FROM records").fetchall() == [("victim",)]
    assert _backup_temp_dirs(output_dir) == []


def test_backup_database_source_disappearance_cannot_create_empty_database(
    tmp_path, monkeypatch
):
    from zhiji_backend import database_backup

    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")

    output_dir = tmp_path / "backups"
    real_connect = database_backup.sqlite3.connect
    removed = False

    def remove_source_before_open(database, *args, **kwargs):
        nonlocal removed
        if kwargs.get("uri") and str(database).startswith(source.resolve().as_uri()):
            source.unlink()
            removed = True
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(database_backup.sqlite3, "connect", remove_source_before_open)

    with pytest.raises(sqlite3.OperationalError):
        database_backup.backup_database(source, output_dir)

    assert removed
    assert not source.exists()
    assert _backup_temp_dirs(output_dir) == []


def test_backup_database_publishes_verified_temp_inode_and_cleans_temp_dir(
    tmp_path, monkeypatch
):
    from zhiji_backend import database_backup

    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.execute("INSERT INTO records VALUES ('source')")

    real_link = os.link
    publication = {}

    def capture_link(source_path, target_path, **kwargs):
        publication["source"] = os.lstat(source_path)
        publication["source_parent"] = os.stat(os.path.dirname(source_path))
        publication["source_path"] = source_path
        result = real_link(source_path, target_path, **kwargs)
        publication["target"] = os.lstat(target_path)
        return result

    monkeypatch.setattr(database_backup.os, "link", capture_link)
    output_dir = tmp_path / "backups"

    backup = database_backup.backup_database(source, output_dir)

    assert stat.S_ISREG(publication["source"].st_mode)
    assert stat.S_ISREG(publication["target"].st_mode)
    assert stat.S_IMODE(publication["source_parent"].st_mode) == 0o700
    assert (
        publication["source"].st_dev,
        publication["source"].st_ino,
    ) == (
        publication["target"].st_dev,
        publication["target"].st_ino,
    )
    assert not os.path.exists(os.path.dirname(publication["source_path"]))
    assert os.path.samestat(publication["target"], os.lstat(backup))
    assert _backup_temp_dirs(output_dir) == []


def test_backup_database_deletes_target_when_integrity_verification_fails(
    tmp_path, monkeypatch
):
    from zhiji_backend import database_backup

    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")

    def fail_verification(_target):
        raise RuntimeError("backup integrity check failed")

    _freeze_backup_timestamp(monkeypatch, database_backup)
    monkeypatch.setattr(database_backup, "_verify_backup", fail_verification)
    output_dir = tmp_path / "backups"
    target = output_dir / "intelligence-pre-cleanup-20260719-123456.sqlite"

    with pytest.raises(RuntimeError, match="backup integrity check failed"):
        database_backup.backup_database(source, output_dir)

    assert not target.exists()
    assert _backup_temp_dirs(output_dir) == []
