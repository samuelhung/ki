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
    database_backup_manifest,
    database_backup_prerequisite,
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
        path,
        label,
        regular_non_symlink_identity=_regular_non_symlink_identity,
    )


def _require_source_identity(path: Path, expected: tuple[int, int]) -> None:
    database_backup_artifacts.require_source_identity(
        path,
        expected,
        regular_non_symlink_identity=_regular_non_symlink_identity,
    )


def _verify_backup(target: Path) -> None:
    database_backup_artifacts.verify_backup(
        target,
        regular_file_identity=_regular_file_identity,
        read_only_uri=_read_only_uri,
    )


def _publish_backup(
    staged_backup: Path, target: Path, identity: tuple[int, int]
) -> None:
    database_backup_artifacts.publish_backup(
        staged_backup,
        target,
        identity,
        regular_file_identity=_regular_file_identity,
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
    path: Path,
    label: str,
    *,
    expected_sha256: object = _EXPECTED_SHA256_UNSET,
) -> tuple[PinnedArtifact, dict[str, Any]]:
    return database_backup_artifacts.pin_json_file(
        path,
        label,
        canonical_path=_canonical_manifest_path,
        stat_signature=_stat_signature,
        read_fd_bytes=_read_fd_bytes,
        expected_sha256=expected_sha256,
    )


def _pin_artifact(
    metadata: object, label: str, *, sqlite_backup: bool = False
) -> PinnedArtifact:
    return database_backup_artifacts.pin_artifact(
        metadata,
        label,
        canonical_path=_canonical_manifest_path,
        stat_signature=_stat_signature,
        hash_fd=_hash_fd,
        read_only_uri=_read_only_uri,
        sqlite_backup=sqlite_backup,
    )


def _assert_pinned_artifact(pinned: PinnedArtifact, label: str) -> None:
    database_backup_artifacts.assert_pinned_artifact(
        pinned,
        label,
        stat_signature=_stat_signature,
        hash_fd=_hash_fd,
    )


def _sqlite_snapshot_sha256(path: Path) -> str:
    return database_backup_artifacts.sqlite_snapshot_sha256(
        path, read_only_uri=_read_only_uri
    )


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
    database_backup_artifacts.write_json_atomic(
        path, payload, fsync_parent=_fsync_parent
    )


def _copy_regular_file(source: Path, target: Path) -> None:
    database_backup_artifacts.copy_regular_file(
        source,
        target,
        canonical_regular_source=lambda path, label, **_kwargs: (
            _canonical_regular_source(path, label)
        ),
        require_source_identity=lambda path, identity, **_kwargs: (
            _require_source_identity(path, identity)
        ),
        regular_non_symlink_identity=_regular_non_symlink_identity,
        regular_file_identity=_regular_file_identity,
        publish_backup=_publish_backup,
        fsync_parent=_fsync_parent,
        unlink_if_identity=_unlink_if_identity,
    )


def backup_marker_path(source: Path, migration_name: str) -> Path:
    return database_backup_prerequisite.backup_marker_path(source, migration_name)


def consumed_backup_marker_path(source: Path, migration_name: str) -> Path:
    return database_backup_prerequisite.consumed_backup_marker_path(
        source, migration_name
    )


def _migration_is_pending(source: Path, migration_name: str) -> bool:
    with sqlite3.connect(_read_only_uri(source), uri=True) as conn:
        migrations_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = '_migrations'"
        ).fetchone()
        if migrations_table is None:
            return True
        return conn.execute(
            "SELECT 1 FROM _migrations WHERE name = ?", (migration_name,)
        ).fetchone() is None


def create_rollback_backup(
    source: Path,
    config_path: Path,
    output_dir: Path,
    *,
    migration_name: str = DEFAULT_DESTRUCTIVE_MIGRATION,
) -> Path:
    """Archive the live database and config, then publish the migration marker."""
    source, _ = _canonical_regular_source(source, "database source")
    config_path, _ = _canonical_regular_source(
        config_path, "config source"
    )
    initial_source_metadata = _source_metadata(source)
    initial_config_metadata = _source_metadata(config_path)

    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve(strict=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    config_backup = output_dir / f"system_config-pre-cleanup-{timestamp}.json"
    manifest_path = output_dir / f"rollback-manifest-{timestamp}.json"
    marker_path = backup_marker_path(source, migration_name)
    database_backup: Path | None = None
    lock_conn = sqlite3.connect(str(source))

    try:
        lock_conn.execute("PRAGMA busy_timeout=5000")
        lock_conn.execute("BEGIN IMMEDIATE")
        if not _migration_is_pending(source, migration_name):
            raise RuntimeError(f"migration {migration_name} is not pending")
        sqlite_snapshot_sha256 = _sqlite_snapshot_sha256(source)
        database_backup = backup_database(source, output_dir)
        _copy_regular_file(config_path, config_backup)
        if (
            _source_metadata(source) != initial_source_metadata
            or _source_metadata(config_path) != initial_config_metadata
            or _sqlite_snapshot_sha256(source) != sqlite_snapshot_sha256
        ):
            raise RuntimeError("database or config source changed during rollback backup")
        created_at = datetime.now(UTC).isoformat()
        manifest = {
            "schema_version": BACKUP_MANIFEST_SCHEMA_VERSION,
            "migration_name": migration_name,
            "created_at": created_at,
            "marker_path": str(marker_path),
            "source": {
                "database_path": str(source),
                "config_path": str(config_path),
                "database_identity": initial_source_metadata,
                "config_identity": initial_config_metadata,
                "sqlite_snapshot_sha256": sqlite_snapshot_sha256,
            },
            "artifacts": {
                "database": _artifact_metadata(
                    database_backup, integrity_check="ok"
                ),
                "config": _artifact_metadata(config_backup),
                "digest_archive": None,
            },
        }
        _write_json_exclusive(manifest_path, manifest)
        manifest_path = manifest_path.resolve(strict=True)
        manifest_pin, published_manifest = _pin_json_file(
            manifest_path, "manifest"
        )
        try:
            if published_manifest != manifest:
                raise RuntimeError("backup prerequisite manifest publication mismatch")
            manifest_sha256 = manifest_pin.sha256
        finally:
            manifest_pin.close()
        marker = {
            "schema_version": BACKUP_MANIFEST_SCHEMA_VERSION,
            "state": "ready",
            "migration_name": migration_name,
            "created_at": created_at,
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "source": manifest["source"],
        }
        _write_json_atomic(marker_path, marker)
    except Exception:
        manifest_path.unlink(missing_ok=True)
        config_backup.unlink(missing_ok=True)
        if database_backup is not None:
            database_backup.unlink(missing_ok=True)
        raise
    finally:
        lock_conn.rollback()
        lock_conn.close()

    return manifest_path


def _load_json_regular(path: Path, label: str) -> dict[str, Any]:
    return database_backup_manifest.load_json_regular(
        path, label, pin_json_file=_pin_json_file
    )


def _canonical_manifest_path(value: object, label: str) -> Path:
    return database_backup_manifest.canonical_manifest_path(value, label)


def _parse_created_at(value: object) -> datetime:
    return database_backup_manifest.parse_created_at(value)


def _require_current_source(
    path: Path, expected_path: object, expected_identity: object, label: str
) -> None:
    database_backup_manifest.require_current_source(
        path,
        expected_path,
        expected_identity,
        label,
        canonical_regular_source=_canonical_regular_source,
        source_metadata=_source_metadata,
    )


def _verify_artifact(
    metadata: object, label: str, *, sqlite_backup: bool = False
) -> Path:
    return database_backup_manifest.verify_artifact(
        metadata,
        label,
        pin_artifact=_pin_artifact,
        sqlite_backup=sqlite_backup,
    )


def validate_backup_prerequisite(
    source: Path,
    config_path: Path,
    migration_name: str,
    *,
    allow_stale: bool = False,
    pin_artifacts: bool = False,
) -> BackupPrerequisiteLease:
    return database_backup_prerequisite.validate_backup_prerequisite(
        source,
        config_path,
        migration_name,
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
        now=datetime.now(UTC),
        schema_version=BACKUP_MANIFEST_SCHEMA_VERSION,
        max_age_seconds=BACKUP_MAX_AGE_SECONDS,
    )


def assert_backup_prerequisite_published(
    prerequisite: BackupPrerequisiteLease,
) -> None:
    database_backup_prerequisite.assert_backup_prerequisite_published(
        prerequisite, assert_pinned_artifact=_assert_pinned_artifact
    )


def release_backup_prerequisite(
    prerequisite: BackupPrerequisiteLease | None,
) -> None:
    database_backup_prerequisite.release_backup_prerequisite(prerequisite)


def consume_backup_prerequisite(
    source: Path,
    migration_name: str,
    prerequisite: BackupPrerequisiteLease | None = None,
) -> Path | None:
    return database_backup_prerequisite.consume_backup_prerequisite(
        source,
        migration_name,
        prerequisite,
        ready_marker_path=backup_marker_path,
        consumed_marker_path=consumed_backup_marker_path,
        load_json_regular=_load_json_regular,
        validate_marker_for_consumption=_validate_marker_for_consumption,
        validate_loaded_marker_for_consumption=(
            _validate_loaded_marker_for_consumption
        ),
        write_json_atomic=_write_json_atomic,
        now=lambda: datetime.now(UTC),
        schema_version=BACKUP_MANIFEST_SCHEMA_VERSION,
        replace=os.replace,
    )


def _validate_marker_for_consumption(
    source: Path, migration_name: str, marker: dict[str, Any]
) -> None:
    database_backup_manifest.validate_marker_for_consumption(
        source,
        migration_name,
        marker,
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
        source,
        migration_name,
        marker,
        manifest,
        marker_path_for=backup_marker_path,
        schema_version=BACKUP_MANIFEST_SCHEMA_VERSION,
    )


def restore_journal_path(database_path: Path) -> Path:
    database_path = Path(database_path).expanduser().absolute().resolve(strict=False)
    return database_path.parent / f".{database_path.name}.rollback-restore.json"


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
        now=datetime.now(UTC),
        pin_json_file=_pin_json_file,
        pin_artifact=_pin_artifact,
        canonical_path=_canonical_manifest_path,
        parse_timestamp=_parse_created_at,
    )


def _stage_pinned_restore(pinned: PinnedArtifact, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".restore-stage",
            delete=False,
        ) as handle:
            stage = Path(handle.name)
            os.lseek(pinned.fd, 0, os.SEEK_SET)
            while chunk := os.read(pinned.fd, 1024 * 1024):
                handle.write(chunk)
            os.lseek(pinned.fd, 0, os.SEEK_SET)
            handle.flush()
            os.fsync(handle.fileno())
        if stage.stat().st_size != pinned.size or _sha256(stage) != pinned.sha256:
            raise RuntimeError("rollback restore staging verification failed")
        return stage.resolve(strict=True)
    except Exception:
        if stage is not None:
            stage.unlink(missing_ok=True)
        raise


def _replace_staged_restore(stage: Path, destination: Path) -> None:
    os.replace(stage, destination)
    _fsync_parent(destination)


def _restore_path_matches(path: Path, metadata: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    candidate = dict(metadata)
    candidate["path"] = str(path)
    try:
        pinned = _pin_artifact(candidate, "restore destination")
    except RuntimeError:
        return False
    pinned.close()
    return True


def recover_rollback_restore(
    journal_path: Path,
    *,
    expected_manifest_path: Path | None = None,
    expected_manifest_sha256: str | None = None,
) -> dict[str, Path]:
    journal_path = _canonical_manifest_path(
        str(Path(journal_path).expanduser().absolute().resolve(strict=True)),
        "restore journal",
    )
    journal = _load_json_regular(journal_path, "restore journal")
    if (
        journal.get("schema_version") != RESTORE_JOURNAL_SCHEMA_VERSION
        or journal.get("state") != "staged"
    ):
        raise RuntimeError("rollback restore journal is invalid")
    manifest_path = _canonical_manifest_path(
        journal.get("manifest_path"), "rollback manifest"
    )
    if expected_manifest_path is not None:
        expected_manifest_path = Path(expected_manifest_path).resolve(strict=True)
        if (
            manifest_path != expected_manifest_path
            or journal.get("manifest_sha256") != expected_manifest_sha256
        ):
            raise RuntimeError(
                "rollback restore journal belongs to a different rollback manifest"
            )
    manifest, pinned, destinations, _manifest_sha256 = _validate_rollback_manifest(
        manifest_path,
        allow_stale=True,
        pin_artifacts=False,
        expected_sha256=journal.get("manifest_sha256"),
    )
    for artifact in pinned:
        artifact.close()
    artifacts = manifest["artifacts"]
    entries = journal.get("entries")
    if not isinstance(entries, dict):
        raise RuntimeError("rollback restore journal entries are invalid")

    expected_entries = {
        "config": (destinations["config"], artifacts["config"]),
        "database": (destinations["database"], artifacts["database"]),
    }
    try:
        for key in ("config", "database"):
            destination, metadata = expected_entries[key]
            entry = entries.get(key)
            if (
                not isinstance(entry, dict)
                or entry.get("destination") != str(destination)
                or entry.get("sha256") != metadata.get("sha256")
                or entry.get("size") != metadata.get("size")
            ):
                raise RuntimeError("rollback restore journal entry mismatch")
            stage = Path(str(entry.get("stage_path")))
            if _restore_path_matches(destination, metadata):
                stage.unlink(missing_ok=True)
                continue
            stage_metadata = dict(metadata)
            stage_metadata["path"] = str(stage)
            staged = _pin_artifact(
                stage_metadata,
                f"{key} restore stage",
                sqlite_backup=key == "database",
            )
            staged.close()
            _replace_staged_restore(stage, destination)
            if key == "database":
                for suffix in ("-wal", "-shm"):
                    Path(f"{destination}{suffix}").unlink(missing_ok=True)
            if not _restore_path_matches(destination, metadata):
                raise RuntimeError(f"rollback restore {key} verification failed")
        for suffix in ("-wal", "-shm"):
            Path(f"{destinations['database']}{suffix}").unlink(missing_ok=True)
        journal_path.unlink()
        _fsync_parent(journal_path)
    except Exception as exc:
        raise RuntimeError(
            f"rollback restore is incomplete; recover from {journal_path}"
        ) from exc
    return {
        "database": destinations["database"].resolve(strict=True),
        "config": destinations["config"].resolve(strict=True),
    }


def restore_rollback_backup(manifest_path: Path) -> dict[str, Path]:
    """Stage and journal both rollback artifacts before replacing either target."""
    manifest_path = Path(manifest_path).expanduser().absolute().resolve(strict=True)
    (
        _,
        _,
        candidate_destinations,
        candidate_manifest_sha256,
    ) = _validate_rollback_manifest(
        manifest_path, allow_stale=True, pin_artifacts=False
    )
    journal_path = restore_journal_path(candidate_destinations["database"])
    if journal_path.exists():
        return recover_rollback_restore(
            journal_path,
            expected_manifest_path=manifest_path,
            expected_manifest_sha256=candidate_manifest_sha256,
        )

    manifest, pinned, destinations, manifest_sha256 = _validate_rollback_manifest(
        manifest_path
    )
    stages: dict[str, Path] = {}
    journal_written = False
    try:
        stages["database"] = _stage_pinned_restore(
            pinned[0], destinations["database"]
        )
        stages["config"] = _stage_pinned_restore(pinned[1], destinations["config"])
        _assert_pinned_artifact(pinned[2], "rollback manifest")
        journal = {
            "schema_version": RESTORE_JOURNAL_SCHEMA_VERSION,
            "state": "staged",
            "created_at": datetime.now(UTC).isoformat(),
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "entries": {
                key: {
                    "destination": str(destinations[key]),
                    "stage_path": str(stages[key]),
                    "sha256": manifest["artifacts"][key]["sha256"],
                    "size": manifest["artifacts"][key]["size"],
                }
                for key in ("database", "config")
            },
        }
        _write_json_exclusive(journal_path, journal)
        journal_written = True
    finally:
        for artifact in pinned:
            artifact.close()
        if not journal_written:
            for stage in stages.values():
                stage.unlink(missing_ok=True)

    return recover_rollback_restore(journal_path)


def backup_database(source: Path, output_dir: Path) -> Path:
    """Create and verify a timestamped SQLite backup without overwriting files."""
    source, source_identity = _canonical_regular_source(source, "database source")

    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve(strict=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = output_dir / f"intelligence-pre-cleanup-{timestamp}.sqlite"
    temp_dir = Path(tempfile.mkdtemp(prefix=BACKUP_TEMP_PREFIX, dir=output_dir))
    staged_backup = temp_dir / "backup.sqlite"
    staged_identity: tuple[int, int] | None = None

    try:
        with sqlite3.connect(_read_only_uri(source), uri=True) as src:
            _require_source_identity(source, source_identity)
            with sqlite3.connect(staged_backup) as dst:
                src.backup(dst)
            _require_source_identity(source, source_identity)
        _verify_backup(staged_backup)
        _require_source_identity(source, source_identity)
        staged_identity = _regular_file_identity(staged_backup)
        _publish_backup(staged_backup, target, staged_identity)
    except Exception:
        if staged_identity is not None:
            _unlink_if_identity(target, staged_identity)
        raise
    finally:
        try:
            shutil.rmtree(temp_dir)
        except FileNotFoundError:
            pass

    return target
