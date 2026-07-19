from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKUP_TEMP_PREFIX = ".intelligence-backup-"
DEFAULT_DESTRUCTIVE_MIGRATION = "20260719_remove_retired_features"
BACKUP_MANIFEST_SCHEMA_VERSION = 1
BACKUP_MAX_AGE_SECONDS = 24 * 60 * 60


def _read_only_uri(path: Path) -> str:
    return f"{path.as_uri()}?mode=ro"


def _regular_file_identity(path: Path) -> tuple[int, int]:
    file_stat = os.lstat(path)
    if not stat.S_ISREG(file_stat.st_mode):
        raise RuntimeError(f"backup path is not a regular file: {path}")
    return file_stat.st_dev, file_stat.st_ino


def _regular_non_symlink_identity(path: Path) -> tuple[int, int]:
    link_stat = os.lstat(path)
    file_stat = os.stat(path)
    link_identity = link_stat.st_dev, link_stat.st_ino
    file_identity = file_stat.st_dev, file_stat.st_ino
    if (
        not stat.S_ISREG(link_stat.st_mode)
        or not stat.S_ISREG(file_stat.st_mode)
        or link_identity != file_identity
    ):
        raise RuntimeError("database source must be a regular non-symlink file")
    return file_identity


def _canonical_regular_source(path: Path, label: str) -> tuple[Path, tuple[int, int]]:
    requested = Path(path).expanduser().absolute()
    try:
        requested_identity = _regular_non_symlink_identity(requested)
        canonical = requested.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{label} does not exist: {requested}") from exc
    canonical_identity = _regular_non_symlink_identity(canonical)
    if canonical_identity != requested_identity:
        raise RuntimeError(f"{label} identity changed during path resolution")
    return canonical, canonical_identity


def _require_source_identity(path: Path, expected: tuple[int, int]) -> None:
    try:
        current = _regular_non_symlink_identity(path)
    except (FileNotFoundError, RuntimeError) as exc:
        raise RuntimeError("database source identity changed") from exc
    if current != expected:
        raise RuntimeError("database source identity changed")


def _verify_backup(target: Path) -> None:
    identity = _regular_file_identity(target)
    try:
        with sqlite3.connect(_read_only_uri(target), uri=True) as conn:
            result = [row[0] for row in conn.execute("PRAGMA integrity_check")]
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("backup integrity check failed") from exc

    if result != ["ok"]:
        raise RuntimeError("backup integrity check failed")
    if _regular_file_identity(target) != identity:
        raise RuntimeError("backup changed during integrity verification")


def _publish_backup(
    staged_backup: Path, target: Path, identity: tuple[int, int]
) -> None:
    if _regular_file_identity(staged_backup) != identity:
        raise RuntimeError("staged backup changed before publication")
    os.link(staged_backup, target, follow_symlinks=False)

    if _regular_file_identity(staged_backup) != identity:
        raise RuntimeError("staged backup changed during publication")
    if _regular_file_identity(target) != identity:
        raise RuntimeError("published backup identity mismatch")


def _unlink_if_identity(path: Path, identity: tuple[int, int]) -> None:
    try:
        file_stat = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISREG(file_stat.st_mode) and (
        file_stat.st_dev,
        file_stat.st_ino,
    ) == identity:
        os.unlink(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_metadata(path: Path) -> dict[str, int]:
    file_stat = os.stat(path)
    return {
        "device": file_stat.st_dev,
        "inode": file_stat.st_ino,
        "size": file_stat.st_size,
        "mtime_ns": file_stat.st_mtime_ns,
    }


def _artifact_metadata(path: Path, *, integrity_check: str | None = None) -> dict[str, Any]:
    canonical = path.resolve(strict=True)
    metadata: dict[str, Any] = {
        "path": str(canonical),
        "sha256": _sha256(canonical),
        "size": canonical.stat().st_size,
    }
    if integrity_check is not None:
        metadata["integrity_check"] = integrity_check
    return metadata


def _fsync_parent(path: Path) -> None:
    directory_fd: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_fd = os.open(path.parent, flags)
        os.fsync(directory_fd)
    except OSError:
        pass
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


def _write_json_exclusive(path: Path, payload: dict[str, Any]) -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix=BACKUP_TEMP_PREFIX, dir=path.parent))
    staged = temp_dir / "payload.json"
    staged_identity: tuple[int, int] | None = None
    try:
        with staged.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        staged_identity = _regular_file_identity(staged)
        _publish_backup(staged, path, staged_identity)
        _fsync_parent(path)
    except Exception:
        if staged_identity is not None:
            _unlink_if_identity(path, staged_identity)
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
        _fsync_parent(path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _copy_regular_file(source: Path, target: Path) -> None:
    source, source_identity = _canonical_regular_source(source, "config source")
    temp_dir = Path(tempfile.mkdtemp(prefix=BACKUP_TEMP_PREFIX, dir=target.parent))
    staged = temp_dir / "config.backup"
    staged_identity: tuple[int, int] | None = None
    try:
        with source.open("rb") as source_handle, staged.open("xb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        _require_source_identity(source, source_identity)
        staged_identity = _regular_file_identity(staged)
        _publish_backup(staged, target, staged_identity)
        _fsync_parent(target)
    except Exception:
        if staged_identity is not None:
            _unlink_if_identity(target, staged_identity)
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def backup_marker_path(source: Path, migration_name: str) -> Path:
    source = Path(source).expanduser().absolute().resolve(strict=False)
    return source.parent / f".{source.name}.{migration_name}.backup-ready.json"


def consumed_backup_marker_path(source: Path, migration_name: str) -> Path:
    source = Path(source).expanduser().absolute().resolve(strict=False)
    return source.parent / f".{source.name}.{migration_name}.backup-consumed.json"


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
    if not _migration_is_pending(source, migration_name):
        raise RuntimeError(f"migration {migration_name} is not pending")

    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve(strict=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    config_backup = output_dir / f"system_config-pre-cleanup-{timestamp}.json"
    manifest_path = output_dir / f"rollback-manifest-{timestamp}.json"
    marker_path = backup_marker_path(source, migration_name)
    database_backup: Path | None = None

    try:
        database_backup = backup_database(source, output_dir)
        _copy_regular_file(config_path, config_backup)
        if (
            _source_metadata(source) != initial_source_metadata
            or _source_metadata(config_path) != initial_config_metadata
        ):
            raise RuntimeError("database or config source changed during rollback backup")
        created_at = datetime.now(timezone.utc).isoformat()
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
        marker = {
            "schema_version": BACKUP_MANIFEST_SCHEMA_VERSION,
            "state": "ready",
            "migration_name": migration_name,
            "created_at": created_at,
            "manifest_path": str(manifest_path),
            "manifest_sha256": _sha256(manifest_path),
            "source": manifest["source"],
        }
        _write_json_atomic(marker_path, marker)
    except Exception:
        manifest_path.unlink(missing_ok=True)
        config_backup.unlink(missing_ok=True)
        if database_backup is not None:
            database_backup.unlink(missing_ok=True)
        raise

    return manifest_path


def _load_json_regular(path: Path, label: str) -> dict[str, Any]:
    try:
        _regular_file_identity(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, RuntimeError) as exc:
        raise RuntimeError(f"backup prerequisite {label} is invalid") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"backup prerequisite {label} is invalid")
    return payload


def _canonical_manifest_path(value: object, label: str) -> Path:
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


def _parse_created_at(value: object) -> datetime:
    if not isinstance(value, str):
        raise RuntimeError("backup prerequisite timestamp is invalid")
    try:
        created_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("backup prerequisite timestamp is invalid") from exc
    if created_at.tzinfo is None:
        raise RuntimeError("backup prerequisite timestamp is invalid")
    return created_at.astimezone(timezone.utc)


def _require_current_source(
    path: Path, expected_path: object, expected_identity: object, label: str
) -> None:
    canonical, _identity = _canonical_regular_source(path, f"{label} source")
    if str(canonical) != expected_path or not isinstance(expected_identity, dict):
        raise RuntimeError(f"backup prerequisite {label} source identity mismatch")
    current = _source_metadata(canonical)
    expected = {
        key: expected_identity.get(key)
        for key in ("device", "inode", "size", "mtime_ns")
    }
    if current != expected:
        raise RuntimeError(f"backup prerequisite {label} source identity mismatch")


def _verify_artifact(metadata: object, label: str, *, sqlite_backup: bool = False) -> Path:
    if not isinstance(metadata, dict):
        raise RuntimeError(f"backup prerequisite {label} metadata is invalid")
    path = _canonical_manifest_path(metadata.get("path"), label)
    expected_checksum = metadata.get("sha256")
    if not isinstance(expected_checksum, str) or _sha256(path) != expected_checksum:
        raise RuntimeError(f"backup prerequisite {label} checksum mismatch")
    if metadata.get("size") != path.stat().st_size:
        raise RuntimeError(f"backup prerequisite {label} size mismatch")
    if sqlite_backup:
        try:
            _verify_backup(path)
        except RuntimeError as exc:
            raise RuntimeError("backup prerequisite database backup failed integrity check") from exc
        if metadata.get("integrity_check") != "ok":
            raise RuntimeError("backup prerequisite database integrity metadata is invalid")
    return path


def validate_backup_prerequisite(
    source: Path,
    config_path: Path,
    migration_name: str,
    *,
    allow_stale: bool = False,
) -> dict[str, Any]:
    marker_path = backup_marker_path(source, migration_name)
    if not marker_path.exists():
        raise RuntimeError(
            f"backup prerequisite marker is missing for migration {migration_name}"
        )
    marker = _load_json_regular(marker_path, "marker")
    if marker.get("state") != "ready" or marker.get("migration_name") != migration_name:
        raise RuntimeError("backup prerequisite migration mismatch")
    if marker.get("schema_version") != BACKUP_MANIFEST_SCHEMA_VERSION:
        raise RuntimeError("backup prerequisite marker schema is invalid")

    manifest_path = _canonical_manifest_path(
        marker.get("manifest_path"), "manifest"
    )
    if marker.get("manifest_sha256") != _sha256(manifest_path):
        raise RuntimeError("backup prerequisite manifest checksum mismatch")
    manifest = _load_json_regular(manifest_path, "manifest")
    if manifest.get("migration_name") != migration_name:
        raise RuntimeError("backup prerequisite migration mismatch")
    if manifest.get("schema_version") != BACKUP_MANIFEST_SCHEMA_VERSION:
        raise RuntimeError("backup prerequisite manifest schema is invalid")
    if manifest.get("marker_path") != str(marker_path):
        raise RuntimeError("backup prerequisite marker path mismatch")

    created_at = _parse_created_at(manifest.get("created_at"))
    age = (datetime.now(timezone.utc) - created_at).total_seconds()
    if not allow_stale and (age < -300 or age > BACKUP_MAX_AGE_SECONDS):
        raise RuntimeError("backup prerequisite is stale")

    source_metadata = manifest.get("source")
    if not isinstance(source_metadata, dict):
        raise RuntimeError("backup prerequisite source metadata is invalid")
    if marker.get("source") != source_metadata:
        raise RuntimeError("backup prerequisite marker source identity mismatch")
    _require_current_source(
        source,
        source_metadata.get("database_path"),
        source_metadata.get("database_identity"),
        "database",
    )
    _require_current_source(
        config_path,
        source_metadata.get("config_path"),
        source_metadata.get("config_identity"),
        "config",
    )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimeError("backup prerequisite artifact metadata is invalid")
    _verify_artifact(artifacts.get("database"), "database backup", sqlite_backup=True)
    _verify_artifact(artifacts.get("config"), "config backup")
    return {
        "marker_path": marker_path,
        "manifest_path": manifest_path,
        "marker": marker,
        "manifest": manifest,
    }


def consume_backup_prerequisite(
    source: Path, migration_name: str, prerequisite: dict[str, Any] | None = None
) -> Path | None:
    ready = backup_marker_path(source, migration_name)
    consumed = consumed_backup_marker_path(source, migration_name)
    if not ready.exists():
        if not consumed.exists():
            return None
        receipt = _load_json_regular(consumed, "consumed marker")
        if receipt.get("migration_name") != migration_name:
            raise RuntimeError("backup prerequisite migration mismatch")
        if receipt.get("schema_version") != BACKUP_MANIFEST_SCHEMA_VERSION:
            raise RuntimeError("backup prerequisite marker schema is invalid")
        if receipt.get("state") == "consumed":
            return consumed
        if receipt.get("state") != "ready":
            raise RuntimeError("backup prerequisite consumed marker state is invalid")
        _validate_marker_for_consumption(source, migration_name, receipt)
        receipt = dict(receipt)
        receipt["state"] = "consumed"
        receipt["consumed_at"] = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(consumed, receipt)
        return consumed
    try:
        marker = (
            prerequisite["marker"]
            if prerequisite is not None
            else _load_json_regular(ready, "marker")
        )
    except RuntimeError:
        if consumed.exists() and not ready.exists():
            return consume_backup_prerequisite(source, migration_name)
        raise
    _validate_marker_for_consumption(source, migration_name, marker)
    receipt = dict(marker)
    receipt["state"] = "consumed"
    receipt["consumed_at"] = datetime.now(timezone.utc).isoformat()
    try:
        os.replace(ready, consumed)
    except FileNotFoundError:
        if consumed.exists():
            return consume_backup_prerequisite(source, migration_name)
        raise
    _write_json_atomic(consumed, receipt)
    return consumed


def _validate_marker_for_consumption(
    source: Path, migration_name: str, marker: dict[str, Any]
) -> None:
    if marker.get("state") != "ready" or marker.get("migration_name") != migration_name:
        raise RuntimeError("backup prerequisite migration mismatch")
    if marker.get("schema_version") != BACKUP_MANIFEST_SCHEMA_VERSION:
        raise RuntimeError("backup prerequisite marker schema is invalid")
    manifest_path = _canonical_manifest_path(
        marker.get("manifest_path"), "manifest"
    )
    if marker.get("manifest_sha256") != _sha256(manifest_path):
        raise RuntimeError("backup prerequisite manifest checksum mismatch")
    manifest = _load_json_regular(manifest_path, "manifest")
    if manifest.get("migration_name") != migration_name:
        raise RuntimeError("backup prerequisite migration mismatch")
    if manifest.get("schema_version") != BACKUP_MANIFEST_SCHEMA_VERSION:
        raise RuntimeError("backup prerequisite manifest schema is invalid")
    if manifest.get("marker_path") != str(backup_marker_path(source, migration_name)):
        raise RuntimeError("backup prerequisite marker path mismatch")
    source_metadata = manifest.get("source")
    if not isinstance(source_metadata, dict) or marker.get("source") != source_metadata:
        raise RuntimeError("backup prerequisite marker source identity mismatch")
    canonical_source = Path(source).expanduser().absolute().resolve(strict=True)
    if source_metadata.get("database_path") != str(canonical_source):
        raise RuntimeError("backup prerequisite database source identity mismatch")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimeError("backup prerequisite artifact metadata is invalid")
    _verify_artifact(artifacts.get("database"), "database backup", sqlite_backup=True)
    _verify_artifact(artifacts.get("config"), "config backup")


def _replace_from_artifact(artifact: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".restore",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            with artifact.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
        temp_path = None
        _fsync_parent(destination)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def restore_rollback_backup(manifest_path: Path) -> dict[str, Path]:
    """Restore the database and config artifacts recorded in a rollback manifest."""
    manifest_path = _canonical_manifest_path(
        str(Path(manifest_path).expanduser().absolute().resolve(strict=True)),
        "manifest",
    )
    manifest = _load_json_regular(manifest_path, "manifest")
    source = manifest.get("source")
    artifacts = manifest.get("artifacts")
    if not isinstance(source, dict) or not isinstance(artifacts, dict):
        raise RuntimeError("backup prerequisite manifest structure is invalid")
    database_artifact = _verify_artifact(
        artifacts.get("database"), "database backup", sqlite_backup=True
    )
    config_artifact = _verify_artifact(artifacts.get("config"), "config backup")
    database_destination = Path(str(source.get("database_path")))
    config_destination = Path(str(source.get("config_path")))
    if not database_destination.is_absolute() or not config_destination.is_absolute():
        raise RuntimeError("backup prerequisite restore destination is invalid")

    for suffix in ("-wal", "-shm"):
        Path(f"{database_destination}{suffix}").unlink(missing_ok=True)
    _replace_from_artifact(database_artifact, database_destination)
    _replace_from_artifact(config_artifact, config_destination)
    return {
        "database": database_destination.resolve(strict=True),
        "config": config_destination.resolve(strict=True),
    }


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
