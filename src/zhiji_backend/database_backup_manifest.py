from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .database_backup_artifacts import PinnedArtifact

PinJsonFile = Callable[..., tuple[PinnedArtifact, dict[str, Any]]]
PinArtifact = Callable[..., PinnedArtifact]


def canonical_manifest_path(value: object, label: str) -> Path:
    if not isinstance(value, str):
        raise RuntimeError(f"backup prerequisite {label} path is invalid")
    path = Path(value)
    if not path.is_absolute():
        raise RuntimeError(f"backup prerequisite {label} path is not absolute")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"backup prerequisite {label} is missing") from exc
    if resolved != path:
        raise RuntimeError(f"backup prerequisite {label} path is not canonical")
    return resolved


def load_json_regular(
    path: Path,
    label: str,
    *,
    pin_json_file: PinJsonFile,
) -> dict[str, Any]:
    for attempt in range(2):
        try:
            pinned, payload = pin_json_file(path, label)
        except RuntimeError as exc:
            if attempt == 0 and "changed during verification" in str(exc):
                continue
            raise
        pinned.close()
        return payload
    raise RuntimeError(f"backup prerequisite {label} is invalid")


def parse_created_at(value: object) -> datetime:
    if not isinstance(value, str):
        raise RuntimeError("backup prerequisite timestamp is invalid")
    try:
        created_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("backup prerequisite timestamp is invalid") from exc
    if created_at.tzinfo is None:
        raise RuntimeError("backup prerequisite timestamp is invalid")
    return created_at.astimezone(UTC)


def require_fresh(
    created_at: datetime,
    *,
    allow_stale: bool,
    now: datetime,
    max_age_seconds: int,
    stale_message: str = "backup prerequisite is stale",
) -> None:
    age = (now - created_at).total_seconds()
    if not allow_stale and (age < -300 or age > max_age_seconds):
        raise RuntimeError(stale_message)


def require_current_source(
    path: Path,
    expected_path: object,
    expected_identity: object,
    label: str,
    *,
    canonical_regular_source: Callable[[Path, str], tuple[Path, tuple[int, int]]],
    source_metadata: Callable[[Path], dict[str, int]],
) -> None:
    canonical, _identity = canonical_regular_source(path, f"{label} source")
    if str(canonical) != expected_path or not isinstance(expected_identity, dict):
        raise RuntimeError(f"backup prerequisite {label} source identity mismatch")
    current = source_metadata(canonical)
    expected = {
        key: expected_identity.get(key)
        for key in ("device", "inode", "size", "mtime_ns")
    }
    if current != expected:
        raise RuntimeError(f"backup prerequisite {label} source identity mismatch")


def verify_artifact(
    metadata: object,
    label: str,
    *,
    pin_artifact: PinArtifact,
    sqlite_backup: bool = False,
) -> Path:
    pinned = pin_artifact(metadata, label, sqlite_backup=sqlite_backup)
    try:
        return pinned.path
    finally:
        pinned.close()


def validate_loaded_marker_for_consumption(
    source: Path,
    migration_name: str,
    marker: dict[str, Any],
    manifest: dict[str, Any],
    *,
    marker_path_for: Callable[[Path, str], Path],
    schema_version: int,
) -> None:
    if marker.get("state") != "ready" or marker.get("migration_name") != migration_name:
        raise RuntimeError("backup prerequisite migration mismatch")
    if marker.get("schema_version") != schema_version:
        raise RuntimeError("backup prerequisite marker schema is invalid")
    if manifest.get("migration_name") != migration_name:
        raise RuntimeError("backup prerequisite migration mismatch")
    if manifest.get("schema_version") != schema_version:
        raise RuntimeError("backup prerequisite manifest schema is invalid")
    if manifest.get("marker_path") != str(marker_path_for(source, migration_name)):
        raise RuntimeError("backup prerequisite marker path mismatch")
    source_metadata = manifest.get("source")
    if not isinstance(source_metadata, dict) or marker.get("source") != source_metadata:
        raise RuntimeError("backup prerequisite marker source identity mismatch")
    canonical_source = Path(source).expanduser().absolute().resolve(strict=True)
    if source_metadata.get("database_path") != str(canonical_source):
        raise RuntimeError("backup prerequisite database source identity mismatch")


def validate_marker_for_consumption(
    source: Path,
    migration_name: str,
    marker: dict[str, Any],
    *,
    canonical_path: Callable[[object, str], Path],
    pin_json_file: PinJsonFile,
    validate_loaded_marker: Callable[..., None],
    verify_artifact_metadata: Callable[..., Path],
) -> None:
    manifest_path = canonical_path(marker.get("manifest_path"), "manifest")
    manifest_pin, manifest = pin_json_file(
        manifest_path,
        "manifest",
        expected_sha256=marker.get("manifest_sha256"),
    )
    try:
        validate_loaded_marker(source, migration_name, marker, manifest)
        artifact_metadata = manifest.get("artifacts")
        if not isinstance(artifact_metadata, dict):
            raise RuntimeError("backup prerequisite artifact metadata is invalid")
        verify_artifact_metadata(
            artifact_metadata.get("database"),
            "database backup",
            sqlite_backup=True,
        )
        verify_artifact_metadata(artifact_metadata.get("config"), "config backup")
    finally:
        manifest_pin.close()


def validate_rollback_manifest(
    manifest_path: Path,
    *,
    allow_stale: bool,
    pin_artifacts: bool,
    expected_sha256: object,
    schema_version: int,
    migration_name: str,
    max_age_seconds: int,
    now: Callable[[], datetime],
    pin_json_file: PinJsonFile,
    pin_artifact: PinArtifact,
    canonical_path: Callable[[object, str], Path],
    parse_timestamp: Callable[[object], datetime],
) -> tuple[dict[str, Any], list[PinnedArtifact], dict[str, Path], str]:
    manifest_path = canonical_path(
        str(Path(manifest_path).expanduser().absolute().resolve(strict=True)),
        "rollback manifest",
    )
    pinned: list[PinnedArtifact] = []
    manifest_pin, manifest = pin_json_file(
        manifest_path,
        "rollback manifest",
        expected_sha256=expected_sha256,
    )
    try:
        if manifest.get("schema_version") != schema_version:
            raise RuntimeError("rollback manifest schema is invalid")
        if manifest.get("migration_name") != migration_name:
            raise RuntimeError("rollback manifest migration is invalid")
        try:
            created_at = parse_timestamp(manifest.get("created_at"))
        except RuntimeError as exc:
            raise RuntimeError("rollback manifest timestamp is invalid") from exc
        require_fresh(
            created_at,
            allow_stale=allow_stale,
            now=now(),
            max_age_seconds=max_age_seconds,
            stale_message="rollback manifest is stale",
        )
        source = manifest.get("source")
        artifact_metadata = manifest.get("artifacts")
        if not isinstance(source, dict) or not isinstance(artifact_metadata, dict):
            raise RuntimeError("rollback manifest structure is invalid")
        database_destination = Path(str(source.get("database_path")))
        config_destination = Path(str(source.get("config_path")))
        if (
            not database_destination.is_absolute()
            or not config_destination.is_absolute()
        ):
            raise RuntimeError("rollback manifest restore destination is invalid")
        if (
            database_destination.resolve(strict=False) != database_destination
            or config_destination.resolve(strict=False) != config_destination
        ):
            raise RuntimeError("rollback manifest restore destination is not canonical")
        if pin_artifacts:
            pinned.append(
                pin_artifact(
                    artifact_metadata.get("database"),
                    "database backup",
                    sqlite_backup=True,
                )
            )
            pinned.append(
                pin_artifact(artifact_metadata.get("config"), "config backup")
            )
            pinned.append(manifest_pin)
        else:
            manifest_pin.close()
        return (
            manifest,
            pinned,
            {
                "database": database_destination,
                "config": config_destination,
            },
            manifest_pin.sha256,
        )
    except Exception:
        for artifact in pinned:
            artifact.close()
        manifest_pin.close()
        raise
