from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

FileIdentity = tuple[int, int]


def identity(file_stat: os.stat_result) -> FileIdentity:
    return file_stat.st_dev, file_stat.st_ino


def read_only_uri(path: Path) -> str:
    return f"{path.as_uri()}?mode=ro"


def regular_file_identity(path: Path) -> tuple[int, int]:
    file_stat = os.lstat(path)
    if not stat.S_ISREG(file_stat.st_mode):
        raise RuntimeError(f"backup path is not a regular file: {path}")
    return file_stat.st_dev, file_stat.st_ino


def regular_non_symlink_identity(path: Path) -> tuple[int, int]:
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stat_signature(file_stat: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


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


def read_fd_bytes(fd: int) -> bytes:
    return read_fd(fd)


def copy_fd(fd: int, path: Path) -> FileIdentity:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    destination_fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(read_fd(fd))
        while view:
            view = view[os.write(destination_fd, view) :]
        os.fsync(destination_fd)
        return identity(os.fstat(destination_fd))
    finally:
        os.close(destination_fd)


def restore_displaced(source: Path, canonical: Path) -> bool:
    source_stat = source.lstat()
    if stat.S_ISDIR(source_stat.st_mode):
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
    return identity(canonical_stat) == source_identity


def source_metadata(path: Path) -> dict[str, int]:
    file_stat = os.stat(path)
    return {
        "device": file_stat.st_dev,
        "inode": file_stat.st_ino,
        "size": file_stat.st_size,
        "mtime_ns": file_stat.st_mtime_ns,
    }
