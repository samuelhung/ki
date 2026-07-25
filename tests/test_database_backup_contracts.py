from __future__ import annotations

import hashlib
import inspect
import json
import os
import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import get_type_hints

import pytest

from zhiji_backend import database_backup

MIGRATION_NAME = "20260719_remove_retired_features"
FROZEN_NOW = datetime(2026, 7, 25, 10, 11, 12, 345678, tzinfo=UTC)

PUBLIC_BACKUP_FACADE = {
    "backup_marker_path": "(source: 'Path', migration_name: 'str') -> 'Path'",
    "consumed_backup_marker_path": (
        "(source: 'Path', migration_name: 'str') -> 'Path'"
    ),
    "create_rollback_backup": (
        "(source: 'Path', config_path: 'Path', output_dir: 'Path', *, "
        "migration_name: 'str' = '20260719_remove_retired_features') -> 'Path'"
    ),
    "validate_backup_prerequisite": (
        "(source: 'Path', config_path: 'Path', migration_name: 'str', *, "
        "allow_stale: 'bool' = False, pin_artifacts: 'bool' = False) -> "
        "'BackupPrerequisiteLease'"
    ),
    "assert_backup_prerequisite_published": (
        "(prerequisite: 'BackupPrerequisiteLease') -> 'None'"
    ),
    "release_backup_prerequisite": (
        "(prerequisite: 'BackupPrerequisiteLease | None') -> 'None'"
    ),
    "consume_backup_prerequisite": (
        "(source: 'Path', migration_name: 'str', prerequisite: "
        "'BackupPrerequisiteLease | None' = None) -> 'Path | None'"
    ),
    "restore_journal_path": "(database_path: 'Path') -> 'Path'",
    "recover_rollback_restore": (
        "(journal_path: 'Path', *, expected_manifest_path: 'Path | None' = "
        "None, expected_manifest_sha256: 'str | None' = None) -> "
        "'dict[str, Path]'"
    ),
    "restore_rollback_backup": "(manifest_path: 'Path') -> 'dict[str, Path]'",
    "backup_database": "(source: 'Path', output_dir: 'Path') -> 'Path'",
}

PUBLIC_RETURN_TYPES = {
    "backup_marker_path": Path,
    "consumed_backup_marker_path": Path,
    "create_rollback_backup": Path,
    "validate_backup_prerequisite": database_backup.BackupPrerequisiteLease,
    "assert_backup_prerequisite_published": type(None),
    "release_backup_prerequisite": type(None),
    "consume_backup_prerequisite": Path | None,
    "restore_journal_path": Path,
    "recover_rollback_restore": dict[str, Path],
    "restore_rollback_backup": dict[str, Path],
    "backup_database": Path,
}


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FROZEN_NOW.replace(tzinfo=None)
        return FROZEN_NOW.astimezone(tz)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_database(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE entities (id TEXT PRIMARY KEY);
            CREATE TABLE ai_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module TEXT,
                task TEXT
            );
            INSERT INTO entities VALUES ('entity-1');
            """
        )


@pytest.fixture
def rollback_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.setattr(database_backup, "datetime", FrozenDateTime)
    data_dir = tmp_path / "home with spaces" / "data"
    data_dir.mkdir(parents=True)
    database_path = data_dir / "intelligence main.sqlite"
    config_path = data_dir / "system config.json"
    output_dir = tmp_path / "backup output"
    _create_database(database_path)
    config_path.write_text('{"digest_briefing": {}}', encoding="utf-8")

    manifest_path = database_backup.create_rollback_backup(
        database_path,
        config_path,
        output_dir,
        migration_name=MIGRATION_NAME,
    )
    return {
        "database": database_path.resolve(),
        "config": config_path.resolve(),
        "output": output_dir.resolve(),
        "manifest": manifest_path,
    }


def test_public_backup_facade_signatures_and_return_types_are_stable() -> None:
    assert set(PUBLIC_BACKUP_FACADE) == set(PUBLIC_RETURN_TYPES)

    for name, expected_signature in PUBLIC_BACKUP_FACADE.items():
        public_callable = getattr(database_backup, name)
        assert callable(public_callable)
        assert str(inspect.signature(public_callable)) == expected_signature
        assert get_type_hints(public_callable)["return"] == PUBLIC_RETURN_TYPES[name]


def test_marker_and_journal_paths_preserve_canonical_names(tmp_path: Path) -> None:
    database_path = tmp_path / "parent with spaces" / "database name.sqlite"

    assert database_backup.backup_marker_path(database_path, "migration name") == (
        database_path.parent / ".database name.sqlite.migration name.backup-ready.json"
    )
    assert database_backup.consumed_backup_marker_path(
        database_path, "migration name"
    ) == (
        database_path.parent
        / ".database name.sqlite.migration name.backup-consumed.json"
    )
    assert database_backup.restore_journal_path(database_path) == (
        database_path.parent / ".database name.sqlite.rollback-restore.json"
    )


def test_rollback_bundle_manifest_and_ready_marker_schema(rollback_bundle) -> None:
    database_path = rollback_bundle["database"]
    config_path = rollback_bundle["config"]
    output_dir = rollback_bundle["output"]
    manifest_path = rollback_bundle["manifest"]
    marker_path = database_backup.backup_marker_path(database_path, MIGRATION_NAME)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    marker = json.loads(marker_path.read_text(encoding="utf-8"))

    assert manifest_path == output_dir / "rollback-manifest-20260725-101112.json"
    assert set(manifest) == {
        "artifacts",
        "created_at",
        "marker_path",
        "migration_name",
        "schema_version",
        "source",
    }
    assert manifest["schema_version"] == 1
    assert manifest["migration_name"] == MIGRATION_NAME
    assert manifest["created_at"] == "2026-07-25T10:11:12.345678+00:00"
    assert manifest["marker_path"] == str(marker_path)
    assert set(manifest["source"]) == {
        "config_identity",
        "config_path",
        "database_identity",
        "database_path",
        "sqlite_snapshot_sha256",
    }
    assert manifest["source"]["database_path"] == str(database_path)
    assert manifest["source"]["config_path"] == str(config_path)
    assert len(manifest["source"]["sqlite_snapshot_sha256"]) == 64
    assert set(manifest["source"]["database_identity"]) == {
        "device",
        "inode",
        "mtime_ns",
        "size",
    }
    assert set(manifest["source"]["config_identity"]) == {
        "device",
        "inode",
        "mtime_ns",
        "size",
    }

    artifacts = manifest["artifacts"]
    assert set(artifacts) == {"config", "database", "digest_archive"}
    assert artifacts["digest_archive"] is None
    assert set(artifacts["database"]) == {
        "integrity_check",
        "path",
        "sha256",
        "size",
    }
    assert set(artifacts["config"]) == {"path", "sha256", "size"}
    assert artifacts["database"]["integrity_check"] == "ok"
    for key in ("database", "config"):
        artifact_path = Path(artifacts[key]["path"])
        assert artifact_path.is_absolute()
        assert artifact_path.parent == output_dir
        assert artifacts[key]["size"] == artifact_path.stat().st_size
        assert artifacts[key]["sha256"] == _sha256(artifact_path)

    assert set(marker) == {
        "created_at",
        "manifest_path",
        "manifest_sha256",
        "migration_name",
        "schema_version",
        "source",
        "state",
    }
    assert marker == {
        "schema_version": 1,
        "state": "ready",
        "migration_name": MIGRATION_NAME,
        "created_at": manifest["created_at"],
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "source": manifest["source"],
    }
    assert {
        "database": stat.S_IMODE(os.lstat(artifacts["database"]["path"]).st_mode),
        "config": stat.S_IMODE(os.lstat(artifacts["config"]["path"]).st_mode),
        "manifest": stat.S_IMODE(os.lstat(manifest_path).st_mode),
        "marker": stat.S_IMODE(os.lstat(marker_path).st_mode),
    } == {
        "database": 0o644,
        "config": 0o644,
        "manifest": 0o644,
        "marker": 0o600,
    }


def test_prerequisite_lease_release_and_marker_consumption_are_idempotent(
    rollback_bundle,
) -> None:
    database_path = rollback_bundle["database"]
    config_path = rollback_bundle["config"]
    manifest_path = rollback_bundle["manifest"]
    ready_path = database_backup.backup_marker_path(database_path, MIGRATION_NAME)
    consumed_path = database_backup.consumed_backup_marker_path(
        database_path, MIGRATION_NAME
    )
    lease = database_backup.validate_backup_prerequisite(
        database_path,
        config_path,
        MIGRATION_NAME,
        pin_artifacts=True,
    )

    database_backup.assert_backup_prerequisite_published(lease)
    assert (
        database_backup.consume_backup_prerequisite(
            database_path, MIGRATION_NAME, lease
        )
        == consumed_path
    )
    assert not ready_path.exists()
    receipt_before = consumed_path.read_bytes()
    receipt = json.loads(receipt_before)
    assert set(receipt) == {
        "consumed_at",
        "created_at",
        "manifest_path",
        "manifest_sha256",
        "migration_name",
        "schema_version",
        "source",
        "state",
    }
    assert receipt["state"] == "consumed"
    assert receipt["consumed_at"] == "2026-07-25T10:11:12.345678+00:00"
    assert receipt["manifest_path"] == str(manifest_path)

    assert (
        database_backup.consume_backup_prerequisite(database_path, MIGRATION_NAME)
        == consumed_path
    )
    assert consumed_path.read_bytes() == receipt_before

    database_backup.release_backup_prerequisite(lease)
    database_backup.release_backup_prerequisite(lease)
    database_backup.release_backup_prerequisite(None)
    with pytest.raises(RuntimeError, match="^backup prerequisite lease is not pinned$"):
        database_backup.assert_backup_prerequisite_published(lease)


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        ("truncated marker", "backup prerequisite marker is invalid"),
        ("invalid manifest hash", "backup prerequisite manifest checksum mismatch"),
        ("changed config", "backup prerequisite config source identity mismatch"),
    ],
)
def test_prerequisite_validation_preserves_failure_messages(
    rollback_bundle, damage: str, message: str
) -> None:
    database_path = rollback_bundle["database"]
    config_path = rollback_bundle["config"]
    manifest_path = rollback_bundle["manifest"]
    marker_path = database_backup.backup_marker_path(database_path, MIGRATION_NAME)

    if damage == "truncated marker":
        marker_path.write_text('{"state":', encoding="utf-8")
    elif damage == "invalid manifest hash":
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["manifest_sha256"] = "0" * 64
        marker_path.write_text(json.dumps(marker), encoding="utf-8")
    else:
        config_path.write_text('{"changed": true}', encoding="utf-8")

    with pytest.raises(RuntimeError) as exc_info:
        database_backup.validate_backup_prerequisite(
            database_path, config_path, MIGRATION_NAME
        )

    assert str(exc_info.value) == message
    assert manifest_path.exists()


def test_restore_interrupted_during_staging_removes_stages_and_journal(
    rollback_bundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = rollback_bundle["database"]
    config_path = rollback_bundle["config"]
    manifest_path = rollback_bundle["manifest"]
    database_before = database_path.read_bytes()
    config_before = config_path.read_bytes()
    real_stage = database_backup._stage_pinned_restore
    staged_paths: list[Path] = []

    def fail_second_stage(pinned, destination):
        if staged_paths:
            raise OSError("injected config staging failure")
        stage = real_stage(pinned, destination)
        staged_paths.append(stage)
        return stage

    monkeypatch.setattr(database_backup, "_stage_pinned_restore", fail_second_stage)

    with pytest.raises(OSError) as exc_info:
        database_backup.restore_rollback_backup(manifest_path)

    assert str(exc_info.value) == "injected config staging failure"
    assert len(staged_paths) == 1
    assert not staged_paths[0].exists()
    assert database_path.read_bytes() == database_before
    assert config_path.read_bytes() == config_before
    assert not database_backup.restore_journal_path(database_path).exists()


def test_restore_journal_schema_recovery_result_and_repeated_recovery(
    rollback_bundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = rollback_bundle["database"]
    config_path = rollback_bundle["config"]
    manifest_path = rollback_bundle["manifest"]
    config_path.write_text('{"current": true}', encoding="utf-8")
    real_replace = database_backup._replace_staged_restore

    def interrupt_database_replace(stage, destination):
        if Path(destination) == database_path:
            raise OSError("injected database replacement failure")
        real_replace(stage, destination)

    monkeypatch.setattr(
        database_backup, "_replace_staged_restore", interrupt_database_replace
    )

    with pytest.raises(RuntimeError) as exc_info:
        database_backup.restore_rollback_backup(manifest_path)
    journal_path = database_backup.restore_journal_path(database_path)
    assert str(exc_info.value) == (
        f"rollback restore is incomplete; recover from {journal_path}"
    )

    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert set(journal) == {
        "created_at",
        "entries",
        "manifest_path",
        "manifest_sha256",
        "schema_version",
        "state",
    }
    assert journal["schema_version"] == 1
    assert journal["state"] == "staged"
    assert journal["created_at"] == "2026-07-25T10:11:12.345678+00:00"
    assert journal["manifest_path"] == str(manifest_path)
    assert journal["manifest_sha256"] == _sha256(manifest_path)
    assert set(journal["entries"]) == {"config", "database"}
    for key, destination in {"config": config_path, "database": database_path}.items():
        entry = journal["entries"][key]
        assert set(entry) == {"destination", "sha256", "size", "stage_path"}
        assert entry["destination"] == str(destination)
        if key == "database":
            stage_path = Path(entry["stage_path"])
            assert stage_path.exists()
            assert stat.S_IMODE(os.lstat(stage_path).st_mode) == 0o600

    monkeypatch.setattr(database_backup, "_replace_staged_restore", real_replace)
    assert database_backup.recover_rollback_restore(journal_path) == {
        "database": database_path,
        "config": config_path,
    }
    assert not journal_path.exists()
    with pytest.raises(FileNotFoundError):
        database_backup.recover_rollback_restore(journal_path)


def test_restore_detects_destination_replacement_and_keeps_journal(
    rollback_bundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = rollback_bundle["database"]
    manifest_path = rollback_bundle["manifest"]
    attacker = database_path.with_name("replacement.sqlite")
    _create_database(attacker)
    with sqlite3.connect(attacker) as conn:
        conn.execute("INSERT INTO entities VALUES ('replacement')")
    real_replace = database_backup._replace_staged_restore
    replaced = False

    def replace_destination_after_restore(stage, destination):
        nonlocal replaced
        real_replace(stage, destination)
        if Path(destination) == database_path:
            os.replace(attacker, destination)
            replaced = True

    monkeypatch.setattr(
        database_backup,
        "_replace_staged_restore",
        replace_destination_after_restore,
    )

    with pytest.raises(RuntimeError) as exc_info:
        database_backup.restore_rollback_backup(manifest_path)

    journal_path = database_backup.restore_journal_path(database_path)
    assert replaced
    assert str(exc_info.value) == (
        f"rollback restore is incomplete; recover from {journal_path}"
    )
    assert journal_path.exists()
    with sqlite3.connect(database_path) as conn:
        assert conn.execute("SELECT id FROM entities ORDER BY id").fetchall() == [
            ("entity-1",),
            ("replacement",),
        ]
