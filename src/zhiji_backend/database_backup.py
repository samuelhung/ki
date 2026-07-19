from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKUP_TEMP_PREFIX = ".intelligence-backup-"
DEFAULT_DESTRUCTIVE_MIGRATION = "20260719_remove_retired_features"
BACKUP_MANIFEST_SCHEMA_VERSION = 1
BACKUP_MAX_AGE_SECONDS = 24 * 60 * 60
RESTORE_JOURNAL_SCHEMA_VERSION = 1
_EXPECTED_SHA256_UNSET = object()


@dataclass
class PinnedArtifact:
    path: Path
    fd: int
    signature: tuple[int, int, int, int, int, int]
    sha256: str
    size: int

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


@dataclass
class BackupPrerequisiteLease:
    marker_path: Path
    manifest_path: Path
    marker: dict[str, Any]
    manifest: dict[str, Any]
    pinned_files: list[tuple[PinnedArtifact, str]]

    def assert_published(self) -> None:
        for pinned, label in self.pinned_files:
            _assert_pinned_artifact(pinned, label)

    def close(self) -> None:
        for pinned, _label in self.pinned_files:
            pinned.close()
        self.pinned_files = []


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


def _stat_signature(file_stat: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def _hash_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, 1024 * 1024):
        digest.update(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def _read_fd_bytes(fd: int) -> bytes:
    chunks: list[bytes] = []
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, 1024 * 1024):
        chunks.append(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return b"".join(chunks)


def _pin_json_file(
    path: Path,
    label: str,
    *,
    expected_sha256: object = _EXPECTED_SHA256_UNSET,
) -> tuple[PinnedArtifact, dict[str, Any]]:
    path = _canonical_manifest_path(str(path), label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"backup prerequisite {label} is invalid") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"backup prerequisite {label} is not a regular file")
        signature = _stat_signature(before)
        raw = _read_fd_bytes(fd)
        digest = hashlib.sha256(raw).hexdigest()
        after = os.fstat(fd)
        published = os.lstat(path)
        if (
            _stat_signature(after) != signature
            or (published.st_dev, published.st_ino) != (after.st_dev, after.st_ino)
        ):
            raise RuntimeError(
                f"backup prerequisite {label} changed during verification"
            )
        if expected_sha256 is not _EXPECTED_SHA256_UNSET and (
            not isinstance(expected_sha256, str) or digest != expected_sha256
        ):
            raise RuntimeError(f"backup prerequisite {label} checksum mismatch")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"backup prerequisite {label} is invalid") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"backup prerequisite {label} is invalid")
        return PinnedArtifact(path, fd, signature, digest, after.st_size), payload
    except Exception:
        os.close(fd)
        raise


def _pin_artifact(
    metadata: object, label: str, *, sqlite_backup: bool = False
) -> PinnedArtifact:
    if not isinstance(metadata, dict):
        raise RuntimeError(f"backup prerequisite {label} metadata is invalid")
    path = _canonical_manifest_path(metadata.get("path"), label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"backup prerequisite {label} is invalid") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"backup prerequisite {label} is not a regular file")
        signature = _stat_signature(before)
        digest = _hash_fd(fd)
        after = os.fstat(fd)
        published = os.lstat(path)
        if (
            _stat_signature(after) != signature
            or (published.st_dev, published.st_ino) != (after.st_dev, after.st_ino)
        ):
            raise RuntimeError(
                f"backup prerequisite {label} changed during verification"
            )
        if metadata.get("size") != after.st_size:
            raise RuntimeError(f"backup prerequisite {label} size mismatch")
        expected_checksum = metadata.get("sha256")
        if not isinstance(expected_checksum, str) or digest != expected_checksum:
            raise RuntimeError(f"backup prerequisite {label} checksum mismatch")
        if sqlite_backup:
            try:
                with tempfile.TemporaryDirectory(
                    prefix=BACKUP_TEMP_PREFIX
                ) as temp_dir:
                    verification_copy = Path(temp_dir) / "verification.sqlite"
                    with verification_copy.open("xb") as handle:
                        os.lseek(fd, 0, os.SEEK_SET)
                        while chunk := os.read(fd, 1024 * 1024):
                            handle.write(chunk)
                        os.lseek(fd, 0, os.SEEK_SET)
                        handle.flush()
                        os.fsync(handle.fileno())
                    with sqlite3.connect(
                        _read_only_uri(verification_copy), uri=True
                    ) as conn:
                        result = [
                            row[0] for row in conn.execute("PRAGMA integrity_check")
                        ]
            except sqlite3.DatabaseError as exc:
                raise RuntimeError(
                    "backup prerequisite database backup failed integrity check"
                ) from exc
            if result != ["ok"] or metadata.get("integrity_check") != "ok":
                raise RuntimeError(
                    "backup prerequisite database backup failed integrity check"
                )
        return PinnedArtifact(path, fd, signature, digest, after.st_size)
    except Exception:
        os.close(fd)
        raise


def _assert_pinned_artifact(pinned: PinnedArtifact, label: str) -> None:
    if pinned.fd < 0:
        raise RuntimeError(f"backup prerequisite {label} is no longer pinned")
    before = os.fstat(pinned.fd)
    try:
        published_before = os.lstat(pinned.path)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"backup prerequisite {label} changed during migration"
        ) from exc
    digest = _hash_fd(pinned.fd)
    after = os.fstat(pinned.fd)
    try:
        published_after = os.lstat(pinned.path)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"backup prerequisite {label} changed during migration"
        ) from exc
    if (
        _stat_signature(before) != pinned.signature
        or _stat_signature(after) != pinned.signature
        or (published_before.st_dev, published_before.st_ino)
        != (before.st_dev, before.st_ino)
        or (published_after.st_dev, published_after.st_ino)
        != (after.st_dev, after.st_ino)
        or digest != pinned.sha256
    ):
        raise RuntimeError(f"backup prerequisite {label} changed during migration")


def _sqlite_snapshot_sha256(path: Path) -> str:
    with sqlite3.connect(_read_only_uri(path), uri=True) as conn:
        return hashlib.sha256(conn.serialize()).hexdigest()


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
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(path.parent, flags)
    try:
        os.fsync(directory_fd)
    finally:
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
    for attempt in range(2):
        try:
            pinned, payload = _pin_json_file(path, label)
        except RuntimeError as exc:
            if attempt == 0 and "changed during verification" in str(exc):
                continue
            raise
        pinned.close()
        return payload
    raise RuntimeError(f"backup prerequisite {label} is invalid")


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
    pinned = _pin_artifact(metadata, label, sqlite_backup=sqlite_backup)
    try:
        return pinned.path
    finally:
        pinned.close()


def validate_backup_prerequisite(
    source: Path,
    config_path: Path,
    migration_name: str,
    *,
    allow_stale: bool = False,
    pin_artifacts: bool = False,
) -> BackupPrerequisiteLease:
    marker_path = backup_marker_path(source, migration_name)
    if not marker_path.exists():
        raise RuntimeError(
            f"backup prerequisite marker is missing for migration {migration_name}"
        )
    pinned: list[tuple[PinnedArtifact, str]] = []
    try:
        marker_pin, marker = _pin_json_file(marker_path, "marker")
        pinned.append((marker_pin, "marker"))
        if (
            marker.get("state") != "ready"
            or marker.get("migration_name") != migration_name
        ):
            raise RuntimeError("backup prerequisite migration mismatch")
        if marker.get("schema_version") != BACKUP_MANIFEST_SCHEMA_VERSION:
            raise RuntimeError("backup prerequisite marker schema is invalid")

        manifest_path = _canonical_manifest_path(
            marker.get("manifest_path"), "manifest"
        )
        manifest_pin, manifest = _pin_json_file(
            manifest_path,
            "manifest",
            expected_sha256=marker.get("manifest_sha256"),
        )
        pinned.append((manifest_pin, "manifest"))
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
        expected_snapshot = source_metadata.get("sqlite_snapshot_sha256")
        if (
            not isinstance(expected_snapshot, str)
            or _sqlite_snapshot_sha256(
                Path(str(source_metadata.get("database_path")))
            )
            != expected_snapshot
        ):
            raise RuntimeError("backup prerequisite live SQLite snapshot mismatch")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict):
            raise RuntimeError("backup prerequisite artifact metadata is invalid")
        pinned.append(
            (
                _pin_artifact(
                    artifacts.get("database"),
                    "database backup",
                    sqlite_backup=True,
                ),
                "database backup",
            )
        )
        pinned.append(
            (_pin_artifact(artifacts.get("config"), "config backup"), "config backup")
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
) -> None:
    if len(prerequisite.pinned_files) != 4:
        raise RuntimeError("backup prerequisite lease is not pinned")
    prerequisite.assert_published()


def release_backup_prerequisite(
    prerequisite: BackupPrerequisiteLease | None,
) -> None:
    if prerequisite is None:
        return
    prerequisite.close()


def consume_backup_prerequisite(
    source: Path,
    migration_name: str,
    prerequisite: BackupPrerequisiteLease | None = None,
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
            prerequisite.marker
            if prerequisite is not None
            else _load_json_regular(ready, "marker")
        )
    except RuntimeError:
        if consumed.exists() and not ready.exists():
            return consume_backup_prerequisite(source, migration_name)
        raise
    if prerequisite is None:
        _validate_marker_for_consumption(source, migration_name, marker)
    else:
        _validate_loaded_marker_for_consumption(
            source, migration_name, marker, prerequisite.manifest
        )
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
    manifest_path = _canonical_manifest_path(
        marker.get("manifest_path"), "manifest"
    )
    manifest_pin, manifest = _pin_json_file(
        manifest_path,
        "manifest",
        expected_sha256=marker.get("manifest_sha256"),
    )
    try:
        _validate_loaded_marker_for_consumption(
            source, migration_name, marker, manifest
        )
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict):
            raise RuntimeError("backup prerequisite artifact metadata is invalid")
        _verify_artifact(
            artifacts.get("database"), "database backup", sqlite_backup=True
        )
        _verify_artifact(artifacts.get("config"), "config backup")
    finally:
        manifest_pin.close()


def _validate_loaded_marker_for_consumption(
    source: Path,
    migration_name: str,
    marker: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    if marker.get("state") != "ready" or marker.get("migration_name") != migration_name:
        raise RuntimeError("backup prerequisite migration mismatch")
    if marker.get("schema_version") != BACKUP_MANIFEST_SCHEMA_VERSION:
        raise RuntimeError("backup prerequisite marker schema is invalid")
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
    manifest_path = _canonical_manifest_path(
        str(Path(manifest_path).expanduser().absolute().resolve(strict=True)),
        "rollback manifest",
    )
    pinned: list[PinnedArtifact] = []
    manifest_pin, manifest = _pin_json_file(
        manifest_path,
        "rollback manifest",
        expected_sha256=expected_sha256,
    )
    try:
        if manifest.get("schema_version") != BACKUP_MANIFEST_SCHEMA_VERSION:
            raise RuntimeError("rollback manifest schema is invalid")
        if manifest.get("migration_name") != DEFAULT_DESTRUCTIVE_MIGRATION:
            raise RuntimeError("rollback manifest migration is invalid")
        try:
            created_at = _parse_created_at(manifest.get("created_at"))
        except RuntimeError as exc:
            raise RuntimeError("rollback manifest timestamp is invalid") from exc
        age = (datetime.now(timezone.utc) - created_at).total_seconds()
        if not allow_stale and (age < -300 or age > BACKUP_MAX_AGE_SECONDS):
            raise RuntimeError("rollback manifest is stale")
        source = manifest.get("source")
        artifacts = manifest.get("artifacts")
        if not isinstance(source, dict) or not isinstance(artifacts, dict):
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
                _pin_artifact(
                    artifacts.get("database"),
                    "database backup",
                    sqlite_backup=True,
                )
            )
            pinned.append(_pin_artifact(artifacts.get("config"), "config backup"))
            pinned.append(manifest_pin)
        else:
            manifest_pin.close()
        return manifest, pinned, {
            "database": database_destination,
            "config": config_destination,
        }, manifest_pin.sha256
    except Exception:
        for artifact in pinned:
            artifact.close()
        manifest_pin.close()
        raise


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
            if key == "database":
                for suffix in ("-wal", "-shm"):
                    Path(f"{destination}{suffix}").unlink(missing_ok=True)
            _replace_staged_restore(stage, destination)
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
            "created_at": datetime.now(timezone.utc).isoformat(),
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
