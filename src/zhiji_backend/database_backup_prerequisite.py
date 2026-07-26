from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from . import _database_backup_fs, database_backup_artifacts
from ._database_backup_marker_consumption import (
    consume_existing_marker,
    matching_consumed_receipt,
    read_locked_marker,
    validate_consumed_receipt,
)
from ._database_backup_path_publication import (
    expected_destination_publication,
    fsync_marker_parent,
    remove_marker_identity,
    transition_marker_exclusive,
)

PinnedArtifact = database_backup_artifacts.PinnedArtifact


def _default_assert_pinned_artifact(pinned: PinnedArtifact, label: str) -> None:
    database_backup_artifacts.assert_pinned_artifact(
        pinned,
        label,
        stat_signature=_database_backup_fs.stat_signature,
        hash_fd=_database_backup_fs.hash_fd,
    )


@dataclass
class BackupPrerequisiteLease:
    marker_path: Path
    manifest_path: Path
    marker: dict[str, Any]
    manifest: dict[str, Any]
    pinned_files: list[tuple[PinnedArtifact, str]]
    _assert_pinned_artifact: ClassVar[Callable[[PinnedArtifact, str], None]] = (
        _default_assert_pinned_artifact
    )

    def assert_published(self) -> None:
        for pinned, label in self.pinned_files:
            self._assert_pinned_artifact(pinned, label)

    def close(self) -> None:
        for pinned, _label in self.pinned_files:
            pinned.close()
        self.pinned_files = []


def backup_marker_path(source: Path, migration_name: str) -> Path:
    source = Path(source).expanduser().absolute().resolve(strict=False)
    return source.parent / f".{source.name}.{migration_name}.backup-ready.json"


def consumed_backup_marker_path(source: Path, migration_name: str) -> Path:
    source = Path(source).expanduser().absolute().resolve(strict=False)
    return source.parent / f".{source.name}.{migration_name}.backup-consumed.json"


def validate_backup_prerequisite(
    source: Path,
    config_path: Path,
    migration_name: str,
    *,
    allow_stale: bool,
    pin_artifacts: bool,
    marker_path_for: Callable[[Path, str], Path],
    canonical_manifest_path: Callable[[object, str], Path],
    pin_json_file: Callable[..., tuple[PinnedArtifact, dict[str, Any]]],
    parse_created_at: Callable[[object], datetime],
    require_fresh: Callable[..., None],
    require_current_source: Callable[[Path, object, object, str], None],
    sqlite_snapshot_sha256: Callable[[Path], str],
    pin_artifact: Callable[..., PinnedArtifact],
    now: Callable[[], datetime],
    schema_version: int,
    max_age_seconds: int,
    assert_pinned_artifact: Callable[[PinnedArtifact, str], None] | None = None,
) -> BackupPrerequisiteLease:
    marker_path = marker_path_for(source, migration_name)
    if not marker_path.exists():
        raise RuntimeError(
            f"backup prerequisite marker is missing for migration {migration_name}"
        )
    pinned: list[tuple[PinnedArtifact, str]] = []
    try:
        marker_pin, marker = pin_json_file(marker_path, "marker")
        pinned.append((marker_pin, "marker"))
        if (
            marker.get("state") != "ready"
            or marker.get("migration_name") != migration_name
        ):
            raise RuntimeError("backup prerequisite migration mismatch")
        if marker.get("schema_version") != schema_version:
            raise RuntimeError("backup prerequisite marker schema is invalid")

        manifest_path = canonical_manifest_path(marker.get("manifest_path"), "manifest")
        manifest_pin, manifest = pin_json_file(
            manifest_path,
            "manifest",
            expected_sha256=marker.get("manifest_sha256"),
        )
        pinned.append((manifest_pin, "manifest"))
        if manifest.get("migration_name") != migration_name:
            raise RuntimeError("backup prerequisite migration mismatch")
        if manifest.get("schema_version") != schema_version:
            raise RuntimeError("backup prerequisite manifest schema is invalid")
        if manifest.get("marker_path") != str(marker_path):
            raise RuntimeError("backup prerequisite marker path mismatch")

        created_at = parse_created_at(manifest.get("created_at"))
        require_fresh(
            created_at,
            allow_stale=allow_stale,
            now=now(),
            max_age_seconds=max_age_seconds,
        )
        source_metadata = manifest.get("source")
        if not isinstance(source_metadata, dict):
            raise RuntimeError("backup prerequisite source metadata is invalid")
        if marker.get("source") != source_metadata:
            raise RuntimeError("backup prerequisite marker source identity mismatch")
        require_current_source(
            source,
            source_metadata.get("database_path"),
            source_metadata.get("database_identity"),
            "database",
        )
        require_current_source(
            config_path,
            source_metadata.get("config_path"),
            source_metadata.get("config_identity"),
            "config",
        )
        expected_snapshot = source_metadata.get("sqlite_snapshot_sha256")
        if (
            not isinstance(expected_snapshot, str)
            or sqlite_snapshot_sha256(Path(str(source_metadata.get("database_path"))))
            != expected_snapshot
        ):
            raise RuntimeError("backup prerequisite live SQLite snapshot mismatch")
        artifact_metadata = manifest.get("artifacts")
        if not isinstance(artifact_metadata, dict):
            raise RuntimeError("backup prerequisite artifact metadata is invalid")
        pinned.append(
            (
                pin_artifact(
                    artifact_metadata.get("database"),
                    "database backup",
                    sqlite_backup=True,
                ),
                "database backup",
            )
        )
        pinned.append(
            (
                pin_artifact(artifact_metadata.get("config"), "config backup"),
                "config backup",
            )
        )
        lease = BackupPrerequisiteLease(
            marker_path=marker_path,
            manifest_path=manifest_path,
            marker=marker,
            manifest=manifest,
            pinned_files=pinned,
        )
        if assert_pinned_artifact is not None:
            lease._assert_pinned_artifact = assert_pinned_artifact
    except Exception:
        for pinned_file, _label in pinned:
            pinned_file.close()
        raise
    if not pin_artifacts:
        lease.close()
    return lease


def assert_backup_prerequisite_published(
    prerequisite: BackupPrerequisiteLease,
    *,
    assert_pinned_artifact: Callable[[PinnedArtifact, str], None],
) -> None:
    if len(prerequisite.pinned_files) != 4:
        raise RuntimeError("backup prerequisite lease is not pinned")
    for pinned, label in prerequisite.pinned_files:
        assert_pinned_artifact(pinned, label)


def release_backup_prerequisite(prerequisite: BackupPrerequisiteLease | None) -> None:
    if prerequisite is None:
        return
    prerequisite.close()


def consume_backup_prerequisite(
    source: Path,
    migration_name: str,
    prerequisite: BackupPrerequisiteLease | None = None,
    *,
    ready_marker_path: Callable[[Path, str], Path],
    consumed_marker_path: Callable[[Path, str], Path],
    load_json_regular: Callable[[Path, str], dict[str, Any]],
    validate_marker_for_consumption: Callable[..., None],
    validate_loaded_marker_for_consumption: Callable[..., None],
    write_json_atomic: Callable[[Path, dict[str, Any]], None],
    now: Callable[[], datetime],
    schema_version: int,
    replace: Callable[[Path, Path], None] | None = None,
) -> Path | None:
    replace = os.replace if replace is None else replace
    ready = ready_marker_path(source, migration_name)
    consumed = consumed_marker_path(source, migration_name)
    if not ready.exists():
        if not consumed.exists():
            return None
        load_json_regular(consumed, "consumed marker")
        return consume_existing_marker(
            consumed,
            ready,
            source,
            migration_name,
            validate_marker_for_consumption=validate_marker_for_consumption,
            write_json_atomic=write_json_atomic,
            now=now,
            schema_version=schema_version,
            replace=replace,
        )
    try:
        marker = (
            prerequisite.marker
            if prerequisite is not None
            else load_json_regular(ready, "marker")
        )
    except RuntimeError:
        if consumed.exists() and not ready.exists():
            return consume_backup_prerequisite(
                source,
                migration_name,
                ready_marker_path=ready_marker_path,
                consumed_marker_path=consumed_marker_path,
                load_json_regular=load_json_regular,
                validate_marker_for_consumption=validate_marker_for_consumption,
                validate_loaded_marker_for_consumption=(
                    validate_loaded_marker_for_consumption
                ),
                write_json_atomic=write_json_atomic,
                now=now,
                schema_version=schema_version,
                replace=replace,
            )
        raise
    if prerequisite is None:
        validate_marker_for_consumption(source, migration_name, marker)
    else:
        validate_loaded_marker_for_consumption(
            source, migration_name, marker, prerequisite.manifest
        )
    lock_fd = -1
    replay = False
    try:
        lock_fd = os.open(
            ready,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        locked_stat = os.fstat(lock_fd)
        try:
            published_stat = ready.lstat()
        except FileNotFoundError:
            replay = True
        if not replay and (
            not stat.S_ISREG(locked_stat.st_mode)
            or (locked_stat.st_dev, locked_stat.st_ino)
            != (published_stat.st_dev, published_stat.st_ino)
        ):
            raise RuntimeError("marker path collision")
        if not replay:
            locked_marker = read_locked_marker(lock_fd)
            locked_after = os.fstat(lock_fd)
            published_after = ready.lstat()
            if (
                locked_marker != marker
                or (locked_after.st_dev, locked_after.st_ino)
                != (locked_stat.st_dev, locked_stat.st_ino)
                or locked_after.st_size != locked_stat.st_size
                or locked_after.st_mtime_ns != locked_stat.st_mtime_ns
                or locked_after.st_ctime_ns != locked_stat.st_ctime_ns
                or (published_after.st_dev, published_after.st_ino)
                != (locked_stat.st_dev, locked_stat.st_ino)
            ):
                raise RuntimeError("marker path collision")
            receipt = dict(locked_marker)
            receipt["state"] = "consumed"
            receipt["consumed_at"] = now().isoformat()
            try:
                consumed_stat = consumed.lstat()
            except FileNotFoundError:
                consumed_stat = None
            if consumed_stat is not None and (
                consumed_stat.st_dev,
                consumed_stat.st_ino,
            ) != (locked_stat.st_dev, locked_stat.st_ino):
                matching_consumed_receipt(
                    consumed, locked_marker, migration_name, schema_version
                )
                fsync_marker_parent(consumed)
                remove_marker_identity(
                    ready, (locked_stat.st_dev, locked_stat.st_ino)
                )
                return consumed
            transition_marker_exclusive(
                ready,
                consumed,
                source_identity=(locked_stat.st_dev, locked_stat.st_ino),
                replace=replace,
            )
            with expected_destination_publication(
                consumed,
                (locked_stat.st_dev, locked_stat.st_ino, locked_stat.st_mode),
            ):
                write_json_atomic(consumed, receipt)
            consumed_after = consumed.lstat()
            if (consumed_after.st_dev, consumed_after.st_ino) == (
                locked_stat.st_dev,
                locked_stat.st_ino,
            ):
                validate_consumed_receipt(
                    read_locked_marker(lock_fd),
                    locked_marker,
                    migration_name,
                    schema_version,
                )
                os.fsync(lock_fd)
            else:
                matching_consumed_receipt(
                    consumed, locked_marker, migration_name, schema_version
                )
            fsync_marker_parent(consumed)
            remove_marker_identity(ready, (locked_stat.st_dev, locked_stat.st_ino))
    except FileNotFoundError:
        replay = True
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
    if replay:
        if consumed.exists():
            return consume_backup_prerequisite(
                source,
                migration_name,
                ready_marker_path=ready_marker_path,
                consumed_marker_path=consumed_marker_path,
                load_json_regular=load_json_regular,
                validate_marker_for_consumption=validate_marker_for_consumption,
                validate_loaded_marker_for_consumption=(
                    validate_loaded_marker_for_consumption
                ),
                write_json_atomic=write_json_atomic,
                now=now,
                schema_version=schema_version,
                replace=replace,
            )
        raise FileNotFoundError(ready)
    return consumed
