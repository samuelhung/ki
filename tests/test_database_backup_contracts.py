from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import sqlite3
import stat
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import get_type_hints

import pytest

from zhiji_backend import database_backup

MIGRATION_NAME = "20260719_remove_retired_features"

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


def _create_rollback_bundle(root: Path) -> dict[str, Path]:
    data_dir = root / "home with spaces" / "data"
    data_dir.mkdir(parents=True)
    database_path = data_dir / "intelligence main.sqlite"
    config_path = data_dir / "system config.json"
    output_dir = root / "backup output"
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


@pytest.fixture
def rollback_bundle(tmp_path: Path) -> dict[str, Path]:
    return _create_rollback_bundle(tmp_path)


@contextmanager
def _temporary_umask(mask: int):
    previous = os.umask(mask)
    try:
        yield
    finally:
        os.umask(previous)


def _utc_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == UTC.utcoffset(parsed)
    return parsed


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

    assert manifest_path.parent == output_dir
    assert re.fullmatch(r"rollback-manifest-\d{8}-\d{6}\.json", manifest_path.name)
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
    _utc_timestamp(manifest["created_at"])
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


@pytest.mark.parametrize("mask", [0o022, 0o077], ids=["umask-022", "umask-077"])
def test_rollback_bundle_file_modes_respect_umask_and_keep_marker_private(
    tmp_path: Path, mask: int
) -> None:
    with _temporary_umask(mask):
        bundle = _create_rollback_bundle(tmp_path)

    manifest_path = bundle["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    marker_path = database_backup.backup_marker_path(bundle["database"], MIGRATION_NAME)
    creation_mode = 0o666 & ~mask
    inherited_mode_paths = {
        "database": Path(manifest["artifacts"]["database"]["path"]),
        "config": Path(manifest["artifacts"]["config"]["path"]),
        "manifest": manifest_path,
    }

    for path in inherited_mode_paths.values():
        file_stat = os.lstat(path)
        assert stat.S_ISREG(file_stat.st_mode)
        assert stat.S_IMODE(file_stat.st_mode) & ~creation_mode == 0

    marker_stat = os.lstat(marker_path)
    assert stat.S_ISREG(marker_stat.st_mode)
    assert stat.S_IMODE(marker_stat.st_mode) == 0o600


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
    assert _utc_timestamp(receipt["consumed_at"]) >= _utc_timestamp(
        receipt["created_at"]
    )
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


def test_restore_second_stage_failure_cleans_first_stage_before_journal(
    rollback_bundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = rollback_bundle["database"]
    config_path = rollback_bundle["config"]
    manifest_path = rollback_bundle["manifest"]
    with sqlite3.connect(database_path) as conn:
        conn.execute("INSERT INTO entities VALUES ('current')")
    config_path.write_text('{"current": true}', encoding="utf-8")
    database_before = database_path.read_bytes()
    config_before = config_path.read_bytes()
    real_named_temporary_file = tempfile.NamedTemporaryFile
    first_stage_paths: list[Path] = []
    staging_calls = 0

    def interrupt_second_stage(*args, **kwargs):
        nonlocal staging_calls
        staging_calls += 1
        if staging_calls == 2:
            raise OSError("injected second restore staging failure")
        handle = real_named_temporary_file(*args, **kwargs)
        first_stage_paths.append(Path(handle.name))
        return handle

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", interrupt_second_stage)

    with pytest.raises(OSError) as exc_info:
        database_backup.restore_rollback_backup(manifest_path)

    assert type(exc_info.value) is OSError
    assert str(exc_info.value) == "injected second restore staging failure"
    assert staging_calls == 2
    assert len(first_stage_paths) == 1
    assert not first_stage_paths[0].exists()
    assert database_path.read_bytes() == database_before
    assert config_path.read_bytes() == config_before
    assert not database_backup.restore_journal_path(database_path).exists()
    assert list(database_path.parent.glob("*.restore-stage")) == []


def test_restore_journal_schema_recovery_result_and_repeated_recovery(
    rollback_bundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = rollback_bundle["database"]
    config_path = rollback_bundle["config"]
    manifest_path = rollback_bundle["manifest"]
    config_path.write_text('{"current": true}', encoding="utf-8")
    real_replace = os.replace

    def interrupt_database_replace(source, destination):
        if Path(destination) == database_path:
            raise OSError("injected database replacement failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", interrupt_database_replace)

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
    assert _utc_timestamp(journal["created_at"]) >= _utc_timestamp(
        json.loads(manifest_path.read_text(encoding="utf-8"))["created_at"]
    )
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

    monkeypatch.setattr(os, "replace", real_replace)
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
    real_replace = os.replace
    replaced = False

    def replace_destination_after_restore(source, destination):
        nonlocal replaced
        real_replace(source, destination)
        if Path(destination) == database_path:
            real_replace(attacker, destination)
            replaced = True

    monkeypatch.setattr(os, "replace", replace_destination_after_restore)

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
