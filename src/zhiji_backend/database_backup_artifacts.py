from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import _database_backup_publication
from ._database_backup_identity_cleanup import isolate_and_unlink

BACKUP_TEMP_PREFIX = ".intelligence-backup-"
EXPECTED_SHA256_UNSET = object()

Identity = tuple[int, int]
Signature = tuple[int, int, int, int, int, int]
IdentityFn = Callable[[Path], Identity]
SignatureFn = Callable[[os.stat_result], Signature]


@dataclass(frozen=True)
class PinnedArtifact:
    __hash__ = None

    path: Path
    fd: int
    signature: Signature
    sha256: str
    size: int

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            object.__setattr__(self, "fd", -1)


def canonical_regular_source(
    path: Path,
    label: str,
    *,
    regular_non_symlink_identity: IdentityFn,
) -> tuple[Path, Identity]:
    requested = Path(path).expanduser().absolute()
    try:
        requested_identity = regular_non_symlink_identity(requested)
        canonical = requested.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{label} does not exist: {requested}") from exc
    canonical_identity = regular_non_symlink_identity(canonical)
    if canonical_identity != requested_identity:
        raise RuntimeError(f"{label} identity changed during path resolution")
    return canonical, canonical_identity


def require_source_identity(
    path: Path,
    expected: Identity,
    *,
    regular_non_symlink_identity: IdentityFn,
) -> None:
    try:
        current = regular_non_symlink_identity(path)
    except (FileNotFoundError, RuntimeError) as exc:
        raise RuntimeError("database source identity changed") from exc
    if current != expected:
        raise RuntimeError("database source identity changed")


def verify_backup(
    target: Path,
    *,
    regular_file_identity: IdentityFn,
    read_only_uri: Callable[[Path], str],
) -> None:
    identity = regular_file_identity(target)
    try:
        with sqlite3.connect(read_only_uri(target), uri=True) as conn:
            result = [row[0] for row in conn.execute("PRAGMA integrity_check")]
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("backup integrity check failed") from exc
    if result != ["ok"]:
        raise RuntimeError("backup integrity check failed")
    if regular_file_identity(target) != identity:
        raise RuntimeError("backup changed during integrity verification")


def publish_backup(
    staged_backup: Path,
    target: Path,
    identity: Identity,
    *,
    regular_file_identity: IdentityFn,
) -> None:
    if regular_file_identity(staged_backup) != identity:
        raise RuntimeError("staged backup changed before publication")
    os.link(staged_backup, target, follow_symlinks=False)
    if regular_file_identity(staged_backup) != identity:
        raise RuntimeError("staged backup changed during publication")
    if regular_file_identity(target) != identity:
        raise RuntimeError("published backup identity mismatch")


def unlink_if_identity(path: Path, identity: Identity) -> None:
    isolate_and_unlink(path, identity)


def pin_json_file(
    path: Path,
    label: str,
    *,
    canonical_path: Callable[[object, str], Path],
    stat_signature: SignatureFn,
    read_fd_bytes: Callable[[int], bytes],
    expected_sha256: object = EXPECTED_SHA256_UNSET,
) -> tuple[PinnedArtifact, dict[str, Any]]:
    path = canonical_path(str(path), label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"backup prerequisite {label} is invalid") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"backup prerequisite {label} is not a regular file")
        signature = stat_signature(before)
        raw = read_fd_bytes(fd)
        digest = hashlib.sha256(raw).hexdigest()
        after = os.fstat(fd)
        published = os.lstat(path)
        if (
            stat_signature(after) != signature
            or (published.st_dev, published.st_ino) != (after.st_dev, after.st_ino)
        ):
            raise RuntimeError(
                f"backup prerequisite {label} changed during verification"
            )
        if expected_sha256 is not EXPECTED_SHA256_UNSET and (
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


def pin_artifact(
    metadata: object,
    label: str,
    *,
    canonical_path: Callable[[object, str], Path],
    stat_signature: SignatureFn,
    hash_fd: Callable[[int], str],
    read_only_uri: Callable[[Path], str],
    sqlite_backup: bool = False,
) -> PinnedArtifact:
    if not isinstance(metadata, dict):
        raise RuntimeError(f"backup prerequisite {label} metadata is invalid")
    path = canonical_path(metadata.get("path"), label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"backup prerequisite {label} is invalid") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"backup prerequisite {label} is not a regular file")
        signature = stat_signature(before)
        digest = hash_fd(fd)
        after = os.fstat(fd)
        published = os.lstat(path)
        if (
            stat_signature(after) != signature
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
            _verify_pinned_sqlite(fd, metadata, read_only_uri)
        return PinnedArtifact(path, fd, signature, digest, after.st_size)
    except Exception:
        os.close(fd)
        raise


def _verify_pinned_sqlite(
    fd: int, metadata: dict[str, Any], read_only_uri: Callable[[Path], str]
) -> None:
    try:
        with tempfile.TemporaryDirectory(prefix=BACKUP_TEMP_PREFIX) as temp_dir:
            verification_copy = Path(temp_dir) / "verification.sqlite"
            with verification_copy.open("xb") as handle:
                os.lseek(fd, 0, os.SEEK_SET)
                while chunk := os.read(fd, 1024 * 1024):
                    handle.write(chunk)
                os.lseek(fd, 0, os.SEEK_SET)
                handle.flush()
                os.fsync(handle.fileno())
            with sqlite3.connect(read_only_uri(verification_copy), uri=True) as conn:
                result = [row[0] for row in conn.execute("PRAGMA integrity_check")]
    except sqlite3.DatabaseError as exc:
        raise RuntimeError(
            "backup prerequisite database backup failed integrity check"
        ) from exc
    if result != ["ok"] or metadata.get("integrity_check") != "ok":
        raise RuntimeError("backup prerequisite database backup failed integrity check")


def assert_pinned_artifact(
    pinned: PinnedArtifact,
    label: str,
    *,
    stat_signature: SignatureFn,
    hash_fd: Callable[[int], str],
) -> None:
    if pinned.fd < 0:
        raise RuntimeError(f"backup prerequisite {label} is no longer pinned")
    before = os.fstat(pinned.fd)
    try:
        published_before = os.lstat(pinned.path)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"backup prerequisite {label} changed during migration"
        ) from exc
    digest = hash_fd(pinned.fd)
    after = os.fstat(pinned.fd)
    try:
        published_after = os.lstat(pinned.path)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"backup prerequisite {label} changed during migration"
        ) from exc
    if (
        stat_signature(before) != pinned.signature
        or stat_signature(after) != pinned.signature
        or (published_before.st_dev, published_before.st_ino)
        != (before.st_dev, before.st_ino)
        or (published_after.st_dev, published_after.st_ino)
        != (after.st_dev, after.st_ino)
        or digest != pinned.sha256
    ):
        raise RuntimeError(f"backup prerequisite {label} changed during migration")


def sqlite_snapshot_sha256(path: Path, *, read_only_uri: Callable[[Path], str]) -> str:
    with sqlite3.connect(read_only_uri(path), uri=True) as conn:
        return hashlib.sha256(conn.serialize()).hexdigest()


def artifact_metadata(
    path: Path,
    *,
    sha256: Callable[[Path], str],
    integrity_check: str | None = None,
) -> dict[str, Any]:
    canonical = path.resolve(strict=True)
    metadata: dict[str, Any] = {
        "path": str(canonical),
        "sha256": sha256(canonical),
        "size": canonical.stat().st_size,
    }
    if integrity_check is not None:
        metadata["integrity_check"] = integrity_check
    return metadata


def fsync_parent(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(path.parent, flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def write_json_exclusive(
    path: Path,
    payload: dict[str, Any],
    *,
    regular_file_identity: IdentityFn,
    publish_backup: Callable[..., None],
    fsync_parent: Callable[[Path], None],
    unlink_if_identity: Callable[[Path, Identity], None],
) -> Identity:
    temp_dir = Path(tempfile.mkdtemp(prefix=BACKUP_TEMP_PREFIX, dir=path.parent))
    staged = temp_dir / "payload.json"
    staged_identity: Identity | None = None
    try:
        with staged.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        staged_identity = regular_file_identity(staged)
        publish_backup(staged, path, staged_identity)
        published_identity = regular_file_identity(path)
        if published_identity != staged_identity:
            raise RuntimeError("published JSON identity mismatch")
        fsync_parent(path)
        return published_identity
    except Exception:
        if staged_identity is not None:
            unlink_if_identity(path, staged_identity)
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
    *,
    fsync_parent: Callable[[Path], None],
    replace: Callable[[Path, Path], None] | None = None,
    on_published: Callable[[], None] | None = None,
) -> None:
    replace = os.replace if replace is None else replace
    _database_backup_publication.write_json_atomic(
        path,
        payload,
        fsync_parent=fsync_parent,
        replace=replace,
        on_published=on_published,
    )


def copy_regular_file(
    source: Path,
    target: Path,
    *,
    canonical_regular_source: Callable[..., tuple[Path, Identity]],
    require_source_identity: Callable[..., None],
    regular_non_symlink_identity: IdentityFn,
    regular_file_identity: IdentityFn,
    publish_backup: Callable[..., None],
    fsync_parent: Callable[[Path], None],
    unlink_if_identity: Callable[[Path, Identity], None],
) -> Identity:
    source, source_identity = canonical_regular_source(
        source,
        "config source",
        regular_non_symlink_identity=regular_non_symlink_identity,
    )
    temp_dir = Path(tempfile.mkdtemp(prefix=BACKUP_TEMP_PREFIX, dir=target.parent))
    staged = temp_dir / "config.backup"
    staged_identity: Identity | None = None
    try:
        with source.open("rb") as source_handle, staged.open("xb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        require_source_identity(
            source,
            source_identity,
            regular_non_symlink_identity=regular_non_symlink_identity,
        )
        staged_identity = regular_file_identity(staged)
        publish_backup(staged, target, staged_identity)
        published_identity = regular_file_identity(target)
        if published_identity != staged_identity:
            raise RuntimeError("published config backup identity mismatch")
        fsync_parent(target)
        return published_identity
    except Exception:
        if staged_identity is not None:
            unlink_if_identity(target, staged_identity)
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
