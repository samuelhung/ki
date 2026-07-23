from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path


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


def read_fd_bytes(fd: int) -> bytes:
    chunks: list[bytes] = []
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, 1024 * 1024):
        chunks.append(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return b"".join(chunks)


def source_metadata(path: Path) -> dict[str, int]:
    file_stat = os.stat(path)
    return {
        "device": file_stat.st_dev,
        "inode": file_stat.st_ino,
        "size": file_stat.st_size,
        "mtime_ns": file_stat.st_mtime_ns,
    }
