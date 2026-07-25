from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database_backup_artifacts import PinnedArtifact

StageIdentity = tuple[int, int]


def _identity(file_stat: os.stat_result) -> StageIdentity:
    return file_stat.st_dev, file_stat.st_ino


def _unlink_identity_in_directory(
    directory_fd: int, identity: StageIdentity
) -> None:
    try:
        names = os.listdir(directory_fd)
    except OSError:
        return
    for name in names:
        try:
            file_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISREG(file_stat.st_mode) and _identity(file_stat) == identity:
                os.unlink(name, dir_fd=directory_fd)
        except OSError:
            pass


@dataclass
class PrivateRestoreClone:
    path: Path
    identity: StageIdentity
    directory: Path
    directory_identity: StageIdentity
    directory_fd: int
    pinned: PinnedArtifact

    def cleanup(self) -> None:
        try:
            _unlink_identity_in_directory(self.directory_fd, self.identity)
        finally:
            self.pinned.close()
            if self.directory_fd >= 0:
                os.close(self.directory_fd)
                self.directory_fd = -1
        try:
            directory_stat = self.directory.lstat()
            if (
                stat.S_ISDIR(directory_stat.st_mode)
                and _identity(directory_stat) == self.directory_identity
            ):
                self.directory.rmdir()
        except (FileNotFoundError, OSError):
            pass


def create_private_restore_clone(
    pinned: PinnedArtifact,
    destination: Path,
    metadata: dict[str, Any],
    *,
    sqlite_backup: bool,
    pin_artifact: Callable[..., PinnedArtifact],
) -> PrivateRestoreClone:
    destination.parent.mkdir(parents=True, exist_ok=True)
    directory = Path(
        tempfile.mkdtemp(
            dir=destination.parent,
            prefix=f".{destination.name}.restore-publish-",
        )
    )
    directory_stat = directory.lstat()
    directory_identity = _identity(directory_stat)
    directory_fd = -1
    clone_path = directory / "restore-clone"
    clone_identity: StageIdentity | None = None
    verified: PinnedArtifact | None = None
    try:
        if stat.S_IMODE(directory_stat.st_mode) != 0o700:
            raise RuntimeError("rollback restore private directory mode is invalid")
        directory_fd = os.open(
            directory,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        if _identity(os.fstat(directory_fd)) != directory_identity:
            raise RuntimeError("rollback restore private directory identity changed")
        clone_fd = os.open(
            clone_path.name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        try:
            clone_identity = _identity(os.fstat(clone_fd))
            os.lseek(pinned.fd, 0, os.SEEK_SET)
            while chunk := os.read(pinned.fd, 1024 * 1024):
                view = memoryview(chunk)
                while view:
                    written = os.write(clone_fd, view)
                    view = view[written:]
            os.lseek(pinned.fd, 0, os.SEEK_SET)
            os.fsync(clone_fd)
        finally:
            os.close(clone_fd)

        clone_metadata = dict(metadata)
        clone_metadata["path"] = str(clone_path)
        verified = pin_artifact(
            clone_metadata,
            "database private restore clone"
            if sqlite_backup
            else "config private restore clone",
            sqlite_backup=sqlite_backup,
        )
        verified_identity = verified.signature[0], verified.signature[1]
        if (
            verified_identity != clone_identity
            or verified.size != pinned.size
            or verified.sha256 != pinned.sha256
            or _identity(os.fstat(directory_fd)) != directory_identity
        ):
            raise RuntimeError("rollback restore private clone verification failed")
        return PrivateRestoreClone(
            clone_path,
            clone_identity,
            directory,
            directory_identity,
            directory_fd,
            verified,
        )
    except Exception:
        if verified is not None:
            verified.close()
        if clone_identity is not None and directory_fd >= 0:
            _unlink_identity_in_directory(directory_fd, clone_identity)
        if directory_fd >= 0:
            os.close(directory_fd)
        try:
            if _identity(directory.lstat()) == directory_identity:
                directory.rmdir()
        except (FileNotFoundError, OSError):
            pass
        raise


def replace_and_verify_private_restore(
    clone: PrivateRestoreClone,
    destination: Path,
    metadata: dict[str, Any],
    *,
    key: str,
    replace_staged_restore: Callable[[Path, Path], None],
    restore_path_matches: Callable[[Path, dict[str, Any]], bool],
) -> None:
    replace_staged_restore(clone.path, destination)
    try:
        destination_stat = destination.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"rollback restore {key} publication identity mismatch"
        ) from exc
    if (
        not stat.S_ISREG(destination_stat.st_mode)
        or _identity(destination_stat) != clone.identity
    ):
        raise RuntimeError(f"rollback restore {key} publication identity mismatch")
    if not restore_path_matches(destination, metadata):
        raise RuntimeError(f"rollback restore {key} verification failed")


def cleanup_owned_stage(
    key: str,
    stage: Path,
    pinned: PinnedArtifact | None,
    owned_stages: dict[str, tuple[Path, StageIdentity]] | None,
    unlink_if_identity: Callable[[Path, StageIdentity], None],
) -> None:
    owned = None if owned_stages is None else owned_stages.get(key)
    if owned is None or owned[0] != stage or pinned is None:
        return
    pinned_identity = pinned.signature[0], pinned.signature[1]
    if owned[1] == pinned_identity:
        unlink_if_identity(stage, owned[1])
