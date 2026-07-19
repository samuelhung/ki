from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zhiji_backend import database_backup, migrations


MIGRATION_NAME = "20260719_remove_retired_features"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _create_legacy_database(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE entities (id TEXT PRIMARY KEY);
            CREATE TABLE event_entities (event_id TEXT, entity_id TEXT);
            CREATE TABLE entity_relations (id INTEGER PRIMARY KEY);
            CREATE TABLE digests (date TEXT PRIMARY KEY);
            CREATE TABLE topics (id TEXT PRIMARY KEY);
            CREATE TABLE ai_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module TEXT,
                task TEXT
            );
            INSERT INTO entities VALUES ('entity-1');
            INSERT INTO topics VALUES ('topic-1');
            INSERT INTO ai_usage (module, task)
            VALUES ('knowledge_graph', 'entity_insight');
            """
        )


def _write_legacy_config(path: Path) -> str:
    source = json.dumps(
        {
            "general": {"base_url": "https://rollback.example/v1"},
            "digest_briefing": {
                "briefing_quick": {"max_tokens": 4567},
                "digest": {"max_tokens": 9999},
            },
            "knowledge_graph": {"entity_insight": {"max_tokens": 2048}},
        },
        ensure_ascii=False,
        indent=2,
    )
    path.write_text(source, encoding="utf-8")
    return source


def _bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "intelligence.sqlite"
    config_path = data_dir / "system_config.json"
    _create_legacy_database(db_path)
    _write_legacy_config(config_path)
    manifest_path = database_backup.create_rollback_backup(
        db_path,
        config_path,
        tmp_path / "backups",
        migration_name=MIGRATION_NAME,
    )
    return db_path, config_path, manifest_path


def _rewrite_manifest_and_marker(manifest_path: Path, payload: dict) -> None:
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    marker_path = Path(payload["marker_path"])
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["manifest_sha256"] = _sha256(manifest_path)
    marker_path.write_text(json.dumps(marker, indent=2), encoding="utf-8")


def _assert_cleanup_not_started(db_path: Path, *, entity_count: int = 1) -> None:
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"entities", "event_entities", "entity_relations", "digests", "topics"} <= tables
        assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == entity_count
        if "_migrations" in tables:
            assert conn.execute(
                "SELECT COUNT(*) FROM _migrations WHERE name = ?", (MIGRATION_NAME,)
            ).fetchone()[0] == 0


def test_rollback_backup_archives_database_config_and_canonical_manifest_through_parent_symlink(
    tmp_path,
):
    real_home = tmp_path / "real-home"
    data_dir = real_home / "data"
    data_dir.mkdir(parents=True)
    alias_home = tmp_path / "alias-home"
    alias_home.symlink_to(real_home, target_is_directory=True)
    db_path = alias_home / "data" / "intelligence.sqlite"
    config_path = alias_home / "data" / "system_config.json"
    _create_legacy_database(db_path)
    config_source = _write_legacy_config(config_path)

    manifest_path = database_backup.create_rollback_backup(
        db_path,
        config_path,
        tmp_path / "backups",
        migration_name=MIGRATION_NAME,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_path.is_absolute()
    assert manifest_path == manifest_path.resolve()
    assert manifest["migration_name"] == MIGRATION_NAME
    assert manifest["source"]["database_path"] == str(db_path.resolve())
    assert manifest["source"]["config_path"] == str(config_path.resolve())
    assert Path(manifest["artifacts"]["database"]["path"]).is_absolute()
    assert Path(manifest["artifacts"]["config"]["path"]).is_absolute()
    assert manifest["artifacts"]["database"]["integrity_check"] == "ok"
    assert manifest["artifacts"]["database"]["sha256"] == _sha256(
        Path(manifest["artifacts"]["database"]["path"])
    )
    assert manifest["artifacts"]["config"]["sha256"] == _sha256(
        Path(manifest["artifacts"]["config"]["path"])
    )
    assert Path(manifest["artifacts"]["config"]["path"]).read_text(
        encoding="utf-8"
    ) == config_source
    marker_path = database_backup.backup_marker_path(db_path, MIGRATION_NAME)
    assert marker_path == Path(manifest["marker_path"])
    assert marker_path.exists()
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker["manifest_path"] == str(manifest_path)
    assert marker["manifest_sha256"] == _sha256(manifest_path)


def test_destructive_migration_refuses_missing_backup_marker_before_deletion(
    tmp_path,
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "intelligence.sqlite"
    _create_legacy_database(db_path)
    _write_legacy_config(data_dir / "system_config.json")

    with pytest.raises(RuntimeError, match="backup prerequisite marker is missing"):
        migrations.ensure_migrations(db_path)

    _assert_cleanup_not_started(db_path)


@pytest.mark.parametrize("failure", ["migration", "stale", "backup_missing", "backup_checksum", "config_missing"])
def test_destructive_migration_refuses_invalid_backup_prerequisite_before_deletion(
    tmp_path,
    failure,
):
    db_path, _config_path, manifest_path = _bundle(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    marker_path = Path(manifest["marker_path"])

    if failure == "migration":
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["migration_name"] = "20260720_wrong_migration"
        marker_path.write_text(json.dumps(marker), encoding="utf-8")
    elif failure == "stale":
        manifest["created_at"] = (
            datetime.now(timezone.utc) - timedelta(days=2)
        ).isoformat()
        _rewrite_manifest_and_marker(manifest_path, manifest)
    elif failure == "backup_missing":
        Path(manifest["artifacts"]["database"]["path"]).unlink()
    elif failure == "backup_checksum":
        Path(manifest["artifacts"]["database"]["path"]).write_bytes(b"not sqlite")
    elif failure == "config_missing":
        Path(manifest["artifacts"]["config"]["path"]).unlink()

    with pytest.raises(RuntimeError, match="backup prerequisite"):
        migrations.ensure_migrations(db_path)

    _assert_cleanup_not_started(db_path)


def test_destructive_migration_refuses_live_source_identity_change_before_deletion(
    tmp_path,
):
    db_path, _config_path, _manifest_path = _bundle(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO entities VALUES ('entity-2')")

    with pytest.raises(RuntimeError, match="source identity mismatch"):
        migrations.ensure_migrations(db_path)

    _assert_cleanup_not_started(db_path, entity_count=2)


def test_successful_destructive_migration_consumes_marker_after_commit(tmp_path):
    db_path, _config_path, manifest_path = _bundle(tmp_path)
    ready_marker = database_backup.backup_marker_path(db_path, MIGRATION_NAME)
    consumed_marker = database_backup.consumed_backup_marker_path(
        db_path, MIGRATION_NAME
    )

    migrations.ensure_migrations(db_path)

    assert not ready_marker.exists()
    assert consumed_marker.exists()
    receipt = json.loads(consumed_marker.read_text(encoding="utf-8"))
    assert receipt["state"] == "consumed"
    assert receipt["migration_name"] == MIGRATION_NAME
    assert receipt["manifest_path"] == str(manifest_path)
    assert receipt["consumed_at"]
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert not {"entities", "event_entities", "entity_relations", "digests", "topics"} & tables
        assert conn.execute("SELECT COUNT(*) FROM _migrations WHERE name = ?", (MIGRATION_NAME,)).fetchone()[0] == 1


def test_rollback_manifest_restores_database_and_legacy_config_for_prior_wheel(
    tmp_path,
):
    db_path, config_path, manifest_path = _bundle(tmp_path)
    original_config = config_path.read_text(encoding="utf-8")
    migrations.ensure_migrations(db_path)
    config_path.write_text('{"briefing": {}}', encoding="utf-8")

    restored = database_backup.restore_rollback_backup(manifest_path)

    assert restored == {"database": db_path.resolve(), "config": config_path.resolve()}
    assert config_path.read_text(encoding="utf-8") == original_config
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT id FROM entities").fetchall() == [("entity-1",)]
    assert not Path(f"{db_path}-wal").exists()
    assert not Path(f"{db_path}-shm").exists()


def test_backup_command_refuses_migration_that_is_not_pending(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "intelligence.sqlite"
    config_path = data_dir / "system_config.json"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE _migrations (name TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO _migrations VALUES (?)", (MIGRATION_NAME,))
    _write_legacy_config(config_path)

    with pytest.raises(RuntimeError, match="is not pending"):
        database_backup.create_rollback_backup(
            db_path,
            config_path,
            tmp_path / "backups",
            migration_name=MIGRATION_NAME,
        )


def test_rollback_backup_refuses_live_database_change_during_bundle_creation(
    tmp_path, monkeypatch
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "intelligence.sqlite"
    config_path = data_dir / "system_config.json"
    _create_legacy_database(db_path)
    _write_legacy_config(config_path)
    real_copy = database_backup._copy_regular_file

    def mutate_database_then_copy(source, target):
        with sqlite3.connect(db_path) as conn:
            conn.execute("INSERT INTO entities VALUES ('late-change')")
        real_copy(source, target)

    monkeypatch.setattr(database_backup, "_copy_regular_file", mutate_database_then_copy)

    with pytest.raises(RuntimeError, match="changed during rollback backup"):
        database_backup.create_rollback_backup(
            db_path,
            config_path,
            tmp_path / "backups",
            migration_name=MIGRATION_NAME,
        )

    assert not database_backup.backup_marker_path(db_path, MIGRATION_NAME).exists()
    assert list((tmp_path / "backups").glob("rollback-manifest-*.json")) == []


def test_concurrent_startup_recovery_consumes_ready_marker_idempotently(
    tmp_path, monkeypatch
):
    db_path, _config_path, _manifest_path = _bundle(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE _migrations (name TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO _migrations VALUES (?)", (MIGRATION_NAME,))

    ready = database_backup.backup_marker_path(db_path, MIGRATION_NAME)
    real_load = database_backup._load_json_regular
    load_barrier = threading.Barrier(2)

    def synchronized_load(path, label):
        payload = real_load(path, label)
        if Path(path) == ready:
            load_barrier.wait(timeout=5)
        return payload

    monkeypatch.setattr(database_backup, "_load_json_regular", synchronized_load)
    start_barrier = threading.Barrier(3)
    errors: list[BaseException] = []

    def run_startup():
        start_barrier.wait(timeout=5)
        try:
            migrations.ensure_migrations(db_path)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run_startup) for _ in range(2)]
    for thread in threads:
        thread.start()
    start_barrier.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert not ready.exists()
    receipt = json.loads(
        database_backup.consumed_backup_marker_path(
            db_path, MIGRATION_NAME
        ).read_text(encoding="utf-8")
    )
    assert receipt["state"] == "consumed"


def test_rollback_backup_replaces_marker_symlink_without_recording_its_target(
    tmp_path,
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "intelligence.sqlite"
    config_path = data_dir / "system_config.json"
    _create_legacy_database(db_path)
    _write_legacy_config(config_path)
    marker_path = database_backup.backup_marker_path(db_path, MIGRATION_NAME)
    victim = tmp_path / "victim.json"
    victim.write_text('{"untouched": true}', encoding="utf-8")
    marker_path.symlink_to(victim)

    manifest_path = database_backup.create_rollback_backup(
        db_path,
        config_path,
        tmp_path / "backups",
        migration_name=MIGRATION_NAME,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert not marker_path.is_symlink()
    assert manifest["marker_path"] == str(marker_path)
    assert victim.read_text(encoding="utf-8") == '{"untouched": true}'
    database_backup.validate_backup_prerequisite(
        db_path, config_path, MIGRATION_NAME
    )


def test_startup_recovers_consumed_marker_receipt_after_post_commit_write_failure(
    tmp_path, monkeypatch
):
    db_path, _config_path, _manifest_path = _bundle(tmp_path)
    consumed = database_backup.consumed_backup_marker_path(db_path, MIGRATION_NAME)
    real_write = database_backup._write_json_atomic
    failed_once = False

    def fail_consumed_receipt_once(path, payload):
        nonlocal failed_once
        if Path(path) == consumed and payload.get("state") == "consumed" and not failed_once:
            failed_once = True
            raise OSError("injected receipt write failure")
        real_write(path, payload)

    monkeypatch.setattr(database_backup, "_write_json_atomic", fail_consumed_receipt_once)

    with pytest.raises(OSError, match="receipt write failure"):
        migrations.ensure_migrations(db_path)

    assert json.loads(consumed.read_text(encoding="utf-8"))["state"] == "ready"
    monkeypatch.setattr(database_backup, "_write_json_atomic", real_write)

    migrations.ensure_migrations(db_path)

    assert json.loads(consumed.read_text(encoding="utf-8"))["state"] == "consumed"


def test_applied_migration_refuses_mismatched_ready_marker_during_recovery(
    tmp_path,
):
    db_path, _config_path, _manifest_path = _bundle(tmp_path)
    ready = database_backup.backup_marker_path(db_path, MIGRATION_NAME)
    marker = json.loads(ready.read_text(encoding="utf-8"))
    marker["migration_name"] = "20260720_wrong_migration"
    ready.write_text(json.dumps(marker), encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE _migrations (name TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO _migrations VALUES (?)", (MIGRATION_NAME,))

    with pytest.raises(RuntimeError, match="migration mismatch"):
        migrations.ensure_migrations(db_path)

    assert ready.exists()
    assert not database_backup.consumed_backup_marker_path(
        db_path, MIGRATION_NAME
    ).exists()
