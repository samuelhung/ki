from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import (
    _database_backup_fs,
    database_backup_artifacts,
    database_backup_creation,
    database_backup_manifest,
    database_backup_prerequisite,
    database_backup_restore,
)

BACKUP_TEMP_PREFIX = database_backup_artifacts.BACKUP_TEMP_PREFIX
DEFAULT_DESTRUCTIVE_MIGRATION = "20260719_remove_retired_features"
BACKUP_MANIFEST_SCHEMA_VERSION = 1
BACKUP_MAX_AGE_SECONDS = 24 * 60 * 60
RESTORE_JOURNAL_SCHEMA_VERSION = 1
_EXPECTED_SHA256_UNSET = database_backup_artifacts.EXPECTED_SHA256_UNSET
PinnedArtifact = database_backup_artifacts.PinnedArtifact
BackupPrerequisiteLease = database_backup_prerequisite.BackupPrerequisiteLease

def _read_only_uri(path: Path) -> str:
    return _database_backup_fs.read_only_uri(path)

def _regular_file_identity(path: Path) -> tuple[int, int]:
    return _database_backup_fs.regular_file_identity(path)

def _regular_non_symlink_identity(path: Path) -> tuple[int, int]:
    return _database_backup_fs.regular_non_symlink_identity(path)

def _canonical_regular_source(path: Path, label: str) -> tuple[Path, tuple[int, int]]:
    return database_backup_artifacts.canonical_regular_source(
        path, label, regular_non_symlink_identity=_regular_non_symlink_identity
    )

def _require_source_identity(path: Path, expected: tuple[int, int]) -> None:
    database_backup_artifacts.require_source_identity(
        path, expected, regular_non_symlink_identity=_regular_non_symlink_identity
    )

def _verify_backup(target: Path) -> None:
    database_backup_artifacts.verify_backup(
        target, regular_file_identity=_regular_file_identity, read_only_uri=_read_only_uri
    )

def _publish_backup(staged_backup: Path, target: Path, identity: tuple[int, int]) -> None:
    database_backup_artifacts.publish_backup(
        staged_backup, target, identity, regular_file_identity=_regular_file_identity
    )

def _unlink_if_identity(path: Path, identity: tuple[int, int]) -> None:
    database_backup_artifacts.unlink_if_identity(path, identity)

def _sha256(path: Path) -> str:
    return _database_backup_fs.sha256(path)

def _stat_signature(file_stat: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return _database_backup_fs.stat_signature(file_stat)

def _hash_fd(fd: int) -> str:
    return _database_backup_fs.hash_fd(fd)

def _read_fd_bytes(fd: int) -> bytes:
    return _database_backup_fs.read_fd_bytes(fd)

def _pin_json_file(
    path: Path, label: str, *, expected_sha256: object = _EXPECTED_SHA256_UNSET
) -> tuple[PinnedArtifact, dict[str, Any]]:
    return database_backup_artifacts.pin_json_file(
        path, label,
        canonical_path=_canonical_manifest_path,
        stat_signature=_stat_signature,
        read_fd_bytes=_read_fd_bytes,
        expected_sha256=expected_sha256,
    )

def _pin_artifact(
    metadata: object, label: str, *, sqlite_backup: bool = False
) -> PinnedArtifact:
    return database_backup_artifacts.pin_artifact(
        metadata, label,
        canonical_path=_canonical_manifest_path,
        stat_signature=_stat_signature,
        hash_fd=_hash_fd,
        read_only_uri=_read_only_uri,
        sqlite_backup=sqlite_backup,
    )

def _assert_pinned_artifact(pinned: PinnedArtifact, label: str) -> None:
    database_backup_artifacts.assert_pinned_artifact(
        pinned, label, stat_signature=_stat_signature, hash_fd=_hash_fd
    )

def _lease_assert_pinned_artifact(pinned: PinnedArtifact, label: str) -> None:
    _assert_pinned_artifact(pinned, label)

def _sqlite_snapshot_sha256(path: Path) -> str:
    return database_backup_artifacts.sqlite_snapshot_sha256(path, read_only_uri=_read_only_uri)

def _source_metadata(path: Path) -> dict[str, int]:
    return _database_backup_fs.source_metadata(path)

def _artifact_metadata(path: Path, *, integrity_check: str | None = None) -> dict[str, Any]:
    return database_backup_artifacts.artifact_metadata(
        path, sha256=_sha256, integrity_check=integrity_check
    )

def _fsync_parent(path: Path) -> None:
    database_backup_artifacts.fsync_parent(path)

def _write_json_exclusive(path: Path, payload: dict[str, Any]) -> None:
    database_backup_artifacts.write_json_exclusive(
        path,
        payload,
        regular_file_identity=_regular_file_identity,
        publish_backup=_publish_backup,
        fsync_parent=_fsync_parent,
        unlink_if_identity=_unlink_if_identity,
    )

def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    database_backup_artifacts.write_json_atomic(path, payload, fsync_parent=_fsync_parent)

def _copy_regular_file(source: Path, target: Path) -> None:
    database_backup_artifacts.copy_regular_file(
        source,
        target,
        canonical_regular_source=lambda path, label, **_kwargs: _canonical_regular_source(path, label),
        require_source_identity=lambda path, identity, **_kwargs: _require_source_identity(path, identity),
        regular_non_symlink_identity=_regular_non_symlink_identity,
        regular_file_identity=_regular_file_identity,
        publish_backup=_publish_backup,
        fsync_parent=_fsync_parent,
        unlink_if_identity=_unlink_if_identity,
    )

def backup_marker_path(source: Path, migration_name: str) -> Path:
    return database_backup_prerequisite.backup_marker_path(source, migration_name)

def consumed_backup_marker_path(source: Path, migration_name: str) -> Path:
    return database_backup_prerequisite.consumed_backup_marker_path(source, migration_name)

def create_rollback_backup(
    source: Path, config_path: Path, output_dir: Path, *,
    migration_name: str = DEFAULT_DESTRUCTIVE_MIGRATION,
) -> Path:
    """Archive the live database and config, then publish the migration marker."""
    return database_backup_creation.create_rollback_backup(
        source, config_path, output_dir,
        migration_name=migration_name,
        schema_version=BACKUP_MANIFEST_SCHEMA_VERSION,
        canonical_regular_source=_canonical_regular_source,
        source_metadata=_source_metadata,
        marker_path_for=backup_marker_path,
        sqlite_snapshot_sha256=_sqlite_snapshot_sha256,
        backup_database=backup_database,
        copy_regular_file=_copy_regular_file,
        artifact_metadata=_artifact_metadata,
        write_json_exclusive=_write_json_exclusive,
        pin_json_file=_pin_json_file,
        write_json_atomic=_write_json_atomic,
        read_only_uri=_read_only_uri,
        connect=sqlite3.connect,
        now=lambda: datetime.now(),
        now_utc=lambda: datetime.now(UTC),
    )

def _load_json_regular(path: Path, label: str) -> dict[str, Any]:
    return database_backup_manifest.load_json_regular(path, label, pin_json_file=_pin_json_file)

def _canonical_manifest_path(value: object, label: str) -> Path:
    return database_backup_manifest.canonical_manifest_path(value, label)

def _parse_created_at(value: object) -> datetime:
    return database_backup_manifest.parse_created_at(value)

def _require_current_source(
    path: Path, expected_path: object, expected_identity: object, label: str
) -> None:
    database_backup_manifest.require_current_source(
        path, expected_path, expected_identity, label,
        canonical_regular_source=_canonical_regular_source,
        source_metadata=_source_metadata,
    )

def _verify_artifact(
    metadata: object, label: str, *, sqlite_backup: bool = False
) -> Path:
    return database_backup_manifest.verify_artifact(
        metadata, label, pin_artifact=_pin_artifact, sqlite_backup=sqlite_backup
    )

def validate_backup_prerequisite(
    source: Path, config_path: Path, migration_name: str, *,
    allow_stale: bool = False,
    pin_artifacts: bool = False,
) -> BackupPrerequisiteLease:
    return database_backup_prerequisite.validate_backup_prerequisite(
        source, config_path, migration_name,
        allow_stale=allow_stale,
        pin_artifacts=pin_artifacts,
        marker_path_for=backup_marker_path,
        canonical_manifest_path=_canonical_manifest_path,
        pin_json_file=_pin_json_file,
        parse_created_at=_parse_created_at,
        require_fresh=database_backup_manifest.require_fresh,
        require_current_source=_require_current_source,
        sqlite_snapshot_sha256=_sqlite_snapshot_sha256,
        pin_artifact=_pin_artifact,
        now=lambda: datetime.now(UTC),
        schema_version=BACKUP_MANIFEST_SCHEMA_VERSION,
        max_age_seconds=BACKUP_MAX_AGE_SECONDS,
        assert_pinned_artifact=_lease_assert_pinned_artifact,
    )

def assert_backup_prerequisite_published(
    prerequisite: BackupPrerequisiteLease,
) -> None:
    database_backup_prerequisite.assert_backup_prerequisite_published(
        prerequisite, assert_pinned_artifact=_assert_pinned_artifact
    )

def release_backup_prerequisite(prerequisite: BackupPrerequisiteLease | None) -> None:
    database_backup_prerequisite.release_backup_prerequisite(prerequisite)

def consume_backup_prerequisite(
    source: Path,
    migration_name: str,
    prerequisite: BackupPrerequisiteLease | None = None,
) -> Path | None:
    return database_backup_prerequisite.consume_backup_prerequisite(
        source, migration_name, prerequisite,
        ready_marker_path=backup_marker_path,
        consumed_marker_path=consumed_backup_marker_path,
        load_json_regular=_load_json_regular,
        validate_marker_for_consumption=_validate_marker_for_consumption,
        validate_loaded_marker_for_consumption=_validate_loaded_marker_for_consumption,
        write_json_atomic=_write_json_atomic,
        now=lambda: datetime.now(UTC),
        schema_version=BACKUP_MANIFEST_SCHEMA_VERSION,
        replace=os.replace,
    )

def _validate_marker_for_consumption(
    source: Path, migration_name: str, marker: dict[str, Any]
) -> None:
    database_backup_manifest.validate_marker_for_consumption(
        source, migration_name, marker,
        canonical_path=_canonical_manifest_path,
        pin_json_file=_pin_json_file,
        validate_loaded_marker=_validate_loaded_marker_for_consumption,
        verify_artifact_metadata=_verify_artifact,
    )

def _validate_loaded_marker_for_consumption(
    source: Path,
    migration_name: str,
    marker: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    database_backup_manifest.validate_loaded_marker_for_consumption(
        source, migration_name, marker, manifest,
        marker_path_for=backup_marker_path,
        schema_version=BACKUP_MANIFEST_SCHEMA_VERSION,
    )

def restore_journal_path(database_path: Path) -> Path:
    return database_backup_restore.restore_journal_path(database_path)

def _validate_rollback_manifest(
    manifest_path: Path,
    *,
    allow_stale: bool = False,
    pin_artifacts: bool = True,
    expected_sha256: object = _EXPECTED_SHA256_UNSET,
) -> tuple[dict[str, Any], list[PinnedArtifact], dict[str, Path], str]:
    return database_backup_manifest.validate_rollback_manifest(
        manifest_path,
        allow_stale=allow_stale,
        pin_artifacts=pin_artifacts,
        expected_sha256=expected_sha256,
        schema_version=BACKUP_MANIFEST_SCHEMA_VERSION,
        migration_name=DEFAULT_DESTRUCTIVE_MIGRATION,
        max_age_seconds=BACKUP_MAX_AGE_SECONDS,
        now=lambda: datetime.now(UTC),
        pin_json_file=_pin_json_file,
        pin_artifact=_pin_artifact,
        canonical_path=_canonical_manifest_path,
        parse_timestamp=_parse_created_at,
    )

def _stage_pinned_restore(pinned: PinnedArtifact, destination: Path) -> Path:
    return database_backup_restore.stage_pinned_restore(
        pinned,
        destination,
        named_temporary_file=tempfile.NamedTemporaryFile,
        seek=os.lseek,
        read=os.read,
        fsync=os.fsync,
        sha256=_sha256,
    )

def _replace_staged_restore(
    stage: Path,
    destination: Path,
    expected_identity: tuple[int, int] | None = None,
) -> None:
    database_backup_restore.replace_staged_restore(
        stage,
        destination,
        replace=os.replace,
        fsync_parent=_fsync_parent,
        expected_identity=expected_identity,
    )

def _restore_path_matches(path: Path, metadata: dict[str, Any]) -> bool:
    return database_backup_restore.restore_path_matches(path, metadata, pin_artifact=_pin_artifact)

def recover_rollback_restore(
    journal_path: Path,
    *,
    expected_manifest_path: Path | None = None,
    expected_manifest_sha256: str | None = None,
) -> dict[str, Path]:
    """Recover swaps during this function's execution.

    Same-user mutation after this function returns is outside scope.
    """
    return _recover_rollback_restore(
        journal_path,
        expected_manifest_path=expected_manifest_path,
        expected_manifest_sha256=expected_manifest_sha256,
    )

def _recover_rollback_restore(
    journal_path: Path,
    *,
    expected_manifest_path: Path | None = None,
    expected_manifest_sha256: str | None = None,
    _owned_stages: database_backup_restore.OwnedStages | None = None,
) -> dict[str, Path]:
    return database_backup_restore.recover_rollback_restore(
        journal_path,
        expected_manifest_path=expected_manifest_path,
        expected_manifest_sha256=expected_manifest_sha256,
        canonical_path=_canonical_manifest_path,
        load_json_regular=_load_json_regular,
        validate_rollback_manifest=_validate_rollback_manifest,
        pin_artifact=_pin_artifact,
        restore_path_matches=_restore_path_matches,
        stage_pinned_restore=_stage_pinned_restore,
        replace_staged_restore=_replace_staged_restore,
        unlink_if_identity=_unlink_if_identity,
        fsync_parent=_fsync_parent,
        journal_schema_version=RESTORE_JOURNAL_SCHEMA_VERSION,
        _owned_stages=_owned_stages,
        write_json_exclusive=_write_json_exclusive,
    )

def restore_rollback_backup(manifest_path: Path) -> dict[str, Path]:
    """Stage and journal both rollback artifacts before replacing either target."""
    return database_backup_restore.restore_rollback_backup(
        manifest_path,
        validate_rollback_manifest=_validate_rollback_manifest,
        restore_journal_path_for=restore_journal_path,
        recover_rollback_restore=_recover_rollback_restore,
        stage_pinned_restore=_stage_pinned_restore,
        unlink_if_identity=_unlink_if_identity,
        assert_pinned_artifact=_assert_pinned_artifact,
        write_json_exclusive=_write_json_exclusive,
        now=lambda: datetime.now(UTC),
        journal_schema_version=RESTORE_JOURNAL_SCHEMA_VERSION,
    )

def backup_database(source: Path, output_dir: Path) -> Path:
    """Create and verify a timestamped SQLite backup without overwriting files."""
    return database_backup_creation.backup_database(
        source,
        output_dir,
        canonical_regular_source=_canonical_regular_source,
        read_only_uri=_read_only_uri,
        require_source_identity=_require_source_identity,
        verify_backup=_verify_backup,
        regular_file_identity=_regular_file_identity,
        publish_backup=_publish_backup,
        unlink_if_identity=_unlink_if_identity,
        connect=sqlite3.connect,
        now=lambda: datetime.now(),
        mkdtemp=tempfile.mkdtemp,
        remove_tree=shutil.rmtree,
        temp_prefix=BACKUP_TEMP_PREFIX,
    )
