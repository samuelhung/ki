from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import _database_backup_fs, database_backup_artifacts

PinnedArtifact = database_backup_artifacts.PinnedArtifact


@dataclass
class BackupPrerequisiteLease:
    marker_path: Path
    manifest_path: Path
    marker: dict[str, Any]
    manifest: dict[str, Any]
    pinned_files: list[tuple[PinnedArtifact, str]]

    def assert_published(self) -> None:
        for pinned, label in self.pinned_files:
            database_backup_artifacts.assert_pinned_artifact(
                pinned,
                label,
                stat_signature=_database_backup_fs.stat_signature,
                hash_fd=_database_backup_fs.hash_fd,
            )

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
    now: datetime,
    schema_version: int,
    max_age_seconds: int,
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
            now=now,
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
        receipt = load_json_regular(consumed, "consumed marker")
        if receipt.get("migration_name") != migration_name:
            raise RuntimeError("backup prerequisite migration mismatch")
        if receipt.get("schema_version") != schema_version:
            raise RuntimeError("backup prerequisite marker schema is invalid")
        if receipt.get("state") == "consumed":
            return consumed
        if receipt.get("state") != "ready":
            raise RuntimeError("backup prerequisite consumed marker state is invalid")
        validate_marker_for_consumption(source, migration_name, receipt)
        receipt = dict(receipt)
        receipt["state"] = "consumed"
        receipt["consumed_at"] = now().isoformat()
        write_json_atomic(consumed, receipt)
        return consumed
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
    receipt = dict(marker)
    receipt["state"] = "consumed"
    receipt["consumed_at"] = now().isoformat()
    try:
        replace(ready, consumed)
    except FileNotFoundError:
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
        raise
    write_json_atomic(consumed, receipt)
    return consumed
