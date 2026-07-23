from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from zhiji_backend import _database_backup_fs as backup_fs
from zhiji_backend import database_backup


def test_read_only_uri_encodes_path_and_sets_read_only_mode(tmp_path: Path) -> None:
    database_path = tmp_path / "database with spaces.sqlite"

    assert backup_fs.read_only_uri(database_path) == (
        f"{database_path.as_uri()}?mode=ro"
    )


def test_regular_file_identity_returns_lstat_device_and_inode(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text("{}", encoding="utf-8")

    file_stat = os.lstat(path)

    assert backup_fs.regular_file_identity(path) == (
        file_stat.st_dev,
        file_stat.st_ino,
    )


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_regular_file_identity_rejects_non_regular_paths(
    tmp_path: Path, kind: str
) -> None:
    path = tmp_path / kind
    if kind == "directory":
        path.mkdir()
    else:
        target = tmp_path / "target"
        target.write_text("payload", encoding="utf-8")
        path.symlink_to(target)

    with pytest.raises(
        RuntimeError,
        match=f"^backup path is not a regular file: {path}$",
    ):
        backup_fs.regular_file_identity(path)


def test_regular_non_symlink_identity_returns_file_identity(tmp_path: Path) -> None:
    path = tmp_path / "database.sqlite"
    path.write_bytes(b"database")

    file_stat = os.stat(path)

    assert backup_fs.regular_non_symlink_identity(path) == (
        file_stat.st_dev,
        file_stat.st_ino,
    )


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_regular_non_symlink_identity_rejects_invalid_paths(
    tmp_path: Path, kind: str
) -> None:
    path = tmp_path / kind
    if kind == "directory":
        path.mkdir()
    else:
        target = tmp_path / "target"
        target.write_bytes(b"database")
        path.symlink_to(target)

    with pytest.raises(
        RuntimeError,
        match="^database source must be a regular non-symlink file$",
    ):
        backup_fs.regular_non_symlink_identity(path)


def test_sha256_hashes_file_contents(tmp_path: Path) -> None:
    payload = b"database backup\x00contents"
    path = tmp_path / "artifact"
    path.write_bytes(payload)

    assert backup_fs.sha256(path) == hashlib.sha256(payload).hexdigest()


def test_stat_signature_preserves_security_relevant_fields(tmp_path: Path) -> None:
    path = tmp_path / "artifact"
    path.write_bytes(b"payload")
    file_stat = os.stat(path)

    assert backup_fs.stat_signature(file_stat) == (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def test_hash_fd_hashes_entire_file_and_resets_offset(tmp_path: Path) -> None:
    payload = b"0123456789"
    path = tmp_path / "artifact"
    path.write_bytes(payload)
    fd = os.open(path, os.O_RDONLY)
    try:
        os.lseek(fd, 4, os.SEEK_SET)

        assert backup_fs.hash_fd(fd) == hashlib.sha256(payload).hexdigest()
        assert os.lseek(fd, 0, os.SEEK_CUR) == 0
    finally:
        os.close(fd)


def test_read_fd_bytes_reads_entire_file_and_resets_offset(tmp_path: Path) -> None:
    payload = b"0123456789"
    path = tmp_path / "artifact"
    path.write_bytes(payload)
    fd = os.open(path, os.O_RDONLY)
    try:
        os.lseek(fd, 4, os.SEEK_SET)

        assert backup_fs.read_fd_bytes(fd) == payload
        assert os.lseek(fd, 0, os.SEEK_CUR) == 0
    finally:
        os.close(fd)


def test_source_metadata_has_exact_stat_shape(tmp_path: Path) -> None:
    path = tmp_path / "database.sqlite"
    path.write_bytes(b"database")
    file_stat = os.stat(path)

    assert backup_fs.source_metadata(path) == {
        "device": file_stat.st_dev,
        "inode": file_stat.st_ino,
        "size": file_stat.st_size,
        "mtime_ns": file_stat.st_mtime_ns,
    }


def test_database_backup_facades_delegate_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "artifact"
    path.write_bytes(b"payload")
    file_stat = os.stat(path)
    calls = [
        ("_read_only_uri", "read_only_uri", (path,)),
        ("_regular_file_identity", "regular_file_identity", (path,)),
        (
            "_regular_non_symlink_identity",
            "regular_non_symlink_identity",
            (path,),
        ),
        ("_sha256", "sha256", (path,)),
        ("_stat_signature", "stat_signature", (file_stat,)),
        ("_hash_fd", "hash_fd", (17,)),
        ("_read_fd_bytes", "read_fd_bytes", (17,)),
        ("_source_metadata", "source_metadata", (path,)),
    ]

    for facade_name, implementation_name, args in calls:
        sentinel = object()
        received: list[tuple[object, ...]] = []

        def replacement(*call_args: object) -> object:
            received.append(call_args)
            return sentinel

        monkeypatch.setattr(backup_fs, implementation_name, replacement)

        assert getattr(database_backup, facade_name)(*args) is sentinel
        assert received == [args]


def test_pin_artifact_resolves_hash_fd_through_facade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "artifact"
    path.write_bytes(b"payload")

    class InjectedFailure(Exception):
        pass

    def fail_hash(_fd: int) -> str:
        raise InjectedFailure

    monkeypatch.setattr(database_backup, "_hash_fd", fail_hash)

    with pytest.raises(InjectedFailure):
        database_backup._pin_artifact(
            {"path": str(path), "size": path.stat().st_size, "sha256": "unused"},
            "config backup",
        )


def test_pin_json_file_resolves_read_fd_bytes_through_facade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{}", encoding="utf-8")

    class InjectedFailure(Exception):
        pass

    def fail_read(_fd: int) -> bytes:
        raise InjectedFailure

    monkeypatch.setattr(database_backup, "_read_fd_bytes", fail_read)

    with pytest.raises(InjectedFailure):
        database_backup._pin_json_file(path, "manifest")
