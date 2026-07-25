from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from pathlib import Path

FileIdentity = tuple[int, int]


def identity(file_stat: os.stat_result) -> FileIdentity:
    return file_stat.st_dev, file_stat.st_ino


def hash_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, 1024 * 1024):
        digest.update(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def read_fd(fd: int) -> bytes:
    chunks: list[bytes] = []
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, 1024 * 1024):
        chunks.append(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return b"".join(chunks)


def copy_fd(fd: int, path: Path) -> FileIdentity:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    recovery_fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(read_fd(fd))
        while view:
            view = view[os.write(recovery_fd, view) :]
        os.fsync(recovery_fd)
        return identity(os.fstat(recovery_fd))
    finally:
        os.close(recovery_fd)


def create_recovery_copy(
    canonical: Path,
    fd: int,
    filename: str,
    directory: Path | None = None,
) -> tuple[Path, Path, FileIdentity]:
    if directory is None or not directory.exists():
        directory = Path(
            tempfile.mkdtemp(
                prefix=f".{canonical.name}.recovery-", dir=canonical.parent
            )
        )
        os.chmod(directory, 0o700)
    recovery_path = directory / filename
    return directory, recovery_path, copy_fd(fd, recovery_path)


def move_to_private(source: Path, destination: Path) -> None:
    os.rename(source, destination)


def path_absent(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    return False


def restore_displaced(source: Path, canonical: Path) -> bool:
    source_stat = source.lstat()
    if not stat.S_ISREG(source_stat.st_mode):
        return False
    source_identity = identity(source_stat)
    try:
        os.link(source, canonical, follow_symlinks=False)
    except OSError:
        return False
    try:
        canonical_stat = canonical.lstat()
    except FileNotFoundError:
        return False
    return (
        stat.S_ISREG(canonical_stat.st_mode)
        and identity(canonical_stat) == source_identity
    )
