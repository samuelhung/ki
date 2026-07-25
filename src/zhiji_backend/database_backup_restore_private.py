from __future__ import annotations

import hashlib
import os
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


def move_to_private(source: Path, destination: Path) -> None:
    os.rename(source, destination)
