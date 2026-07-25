from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from zhiji_backend import _database_backup_fs as backup_fs
from zhiji_backend import database_backup_artifacts as artifacts


def _metadata(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
    }


def test_pinned_artifact_is_immutable_and_close_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "artifact"
    path.write_bytes(b"payload")
    fd = os.open(path, os.O_RDONLY)
    pinned = artifacts.PinnedArtifact(path, fd, (1, 2, 3, 4, 5, 6), "digest", 7)

    with pytest.raises(FrozenInstanceError):
        pinned.path = tmp_path / "replacement"

    pinned.close()
    pinned.close()

    assert pinned.fd == -1
    with pytest.raises(OSError):
        os.fstat(fd)


def test_canonical_regular_source_uses_injected_identity_at_call_time(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sqlite"
    source.write_bytes(b"database")
    calls: list[Path] = []

    def identity(path: Path) -> tuple[int, int]:
        calls.append(path)
        return backup_fs.regular_non_symlink_identity(path)

    canonical, source_identity = artifacts.canonical_regular_source(
        source, "database source", regular_non_symlink_identity=identity
    )

    assert canonical == source.resolve()
    assert source_identity == (source.stat().st_dev, source.stat().st_ino)
    assert calls == [source.absolute(), source.resolve()]


def test_pin_artifact_closes_fd_when_injected_hash_fails(tmp_path: Path) -> None:
    path = tmp_path / "artifact"
    path.write_bytes(b"payload")
    captured_fd = -1

    def fail_hash(fd: int) -> str:
        nonlocal captured_fd
        captured_fd = fd
        raise LookupError("injected hash failure")

    with pytest.raises(LookupError, match="injected hash failure"):
        artifacts.pin_artifact(
            _metadata(path),
            "config backup",
            canonical_path=lambda value, _label: Path(str(value)),
            stat_signature=backup_fs.stat_signature,
            hash_fd=fail_hash,
            read_only_uri=backup_fs.read_only_uri,
        )

    with pytest.raises(OSError):
        os.fstat(captured_fd)


def test_pin_assert_and_close_artifact_lifecycle(tmp_path: Path) -> None:
    path = tmp_path / "artifact"
    path.write_bytes(b"payload")
    pinned = artifacts.pin_artifact(
        _metadata(path),
        "config backup",
        canonical_path=lambda value, _label: Path(str(value)),
        stat_signature=backup_fs.stat_signature,
        hash_fd=backup_fs.hash_fd,
        read_only_uri=backup_fs.read_only_uri,
    )

    artifacts.assert_pinned_artifact(
        pinned,
        "config backup",
        stat_signature=backup_fs.stat_signature,
        hash_fd=backup_fs.hash_fd,
    )
    pinned.close()

    with pytest.raises(
        RuntimeError,
        match="^backup prerequisite config backup is no longer pinned$",
    ):
        artifacts.assert_pinned_artifact(
            pinned,
            "config backup",
            stat_signature=backup_fs.stat_signature,
            hash_fd=backup_fs.hash_fd,
        )


def test_pin_json_file_uses_injected_reader_and_preserves_payload(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text('{"state": "ready"}', encoding="utf-8")
    calls: list[int] = []

    def read_fd(fd: int) -> bytes:
        calls.append(fd)
        return backup_fs.read_fd_bytes(fd)

    pinned, payload = artifacts.pin_json_file(
        path,
        "manifest",
        canonical_path=lambda value, _label: Path(str(value)),
        stat_signature=backup_fs.stat_signature,
        read_fd_bytes=read_fd,
    )
    try:
        assert payload == {"state": "ready"}
        assert calls == [pinned.fd]
    finally:
        pinned.close()


def test_publish_backup_refuses_collision_without_replacing_destination(
    tmp_path: Path,
) -> None:
    staged = tmp_path / "staged"
    target = tmp_path / "target"
    staged.write_bytes(b"new")
    target.write_bytes(b"existing")
    identity = backup_fs.regular_file_identity(staged)

    with pytest.raises(FileExistsError):
        artifacts.publish_backup(
            staged,
            target,
            identity,
            regular_file_identity=backup_fs.regular_file_identity,
        )

    assert target.read_bytes() == b"existing"
    assert staged.read_bytes() == b"new"


def test_publish_backup_detects_published_identity_mismatch(tmp_path: Path) -> None:
    staged = tmp_path / "staged"
    target = tmp_path / "target"
    staged.write_bytes(b"payload")
    identity = backup_fs.regular_file_identity(staged)
    calls = 0

    def changing_identity(path: Path) -> tuple[int, int]:
        nonlocal calls
        calls += 1
        if calls == 3 and path == target:
            return (-1, -1)
        return backup_fs.regular_file_identity(path)

    with pytest.raises(RuntimeError, match="^published backup identity mismatch$"):
        artifacts.publish_backup(
            staged,
            target,
            identity,
            regular_file_identity=changing_identity,
        )


def test_copy_regular_file_is_exclusive_and_cleans_staging(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    source.write_text('{"new": true}', encoding="utf-8")
    target.write_text('{"existing": true}', encoding="utf-8")

    with pytest.raises(FileExistsError):
        artifacts.copy_regular_file(
            source,
            target,
            canonical_regular_source=artifacts.canonical_regular_source,
            require_source_identity=artifacts.require_source_identity,
            regular_non_symlink_identity=backup_fs.regular_non_symlink_identity,
            regular_file_identity=backup_fs.regular_file_identity,
        )

    assert target.read_text(encoding="utf-8") == '{"existing": true}'
    assert not list(tmp_path.glob(".intelligence-backup-*"))


def test_copy_regular_file_rejects_symlink_source(tmp_path: Path) -> None:
    real_source = tmp_path / "real.json"
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    real_source.write_text("{}", encoding="utf-8")
    source.symlink_to(real_source)

    with pytest.raises(
        RuntimeError, match="^database source must be a regular non-symlink file$"
    ):
        artifacts.copy_regular_file(
            source,
            target,
            canonical_regular_source=artifacts.canonical_regular_source,
            require_source_identity=artifacts.require_source_identity,
            regular_non_symlink_identity=backup_fs.regular_non_symlink_identity,
            regular_file_identity=backup_fs.regular_file_identity,
        )

    assert not target.exists()
    assert not list(tmp_path.glob(".intelligence-backup-*"))


def test_json_writes_are_durable_exclusive_or_atomic_and_preserve_modes(
    tmp_path: Path,
) -> None:
    exclusive = tmp_path / "manifest.json"
    atomic = tmp_path / "marker.json"
    payload = {"schema_version": 1, "state": "ready"}
    previous = os.umask(0o022)
    try:
        artifacts.write_json_exclusive(
            exclusive,
            payload,
            regular_file_identity=backup_fs.regular_file_identity,
        )
        artifacts.write_json_atomic(atomic, payload)
    finally:
        os.umask(previous)

    assert json.loads(exclusive.read_text(encoding="utf-8")) == payload
    assert json.loads(atomic.read_text(encoding="utf-8")) == payload
    assert stat.S_IMODE(exclusive.stat().st_mode) == 0o644
    assert stat.S_IMODE(atomic.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".intelligence-backup-*"))
    assert not list(tmp_path.glob(".*.tmp"))


def test_write_json_atomic_fsyncs_file_before_replace_and_parent_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "marker.json"
    events: list[str] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def tracked_fsync(fd: int) -> None:
        events.append("fsync-directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "fsync-file")
        real_fsync(fd)

    def tracked_replace(source: Path, destination: Path) -> None:
        events.append("replace")
        real_replace(source, destination)

    monkeypatch.setattr(artifacts.os, "fsync", tracked_fsync)
    monkeypatch.setattr(artifacts.os, "replace", tracked_replace)

    artifacts.write_json_atomic(target, {"state": "ready"})

    assert events == ["fsync-file", "replace", "fsync-directory"]


def test_write_json_atomic_cleans_temp_file_when_replace_fails(
    tmp_path: Path,
) -> None:
    target = tmp_path / "marker.json"

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("injected replace failure")

    with pytest.raises(OSError, match="injected replace failure"):
        artifacts.write_json_atomic(target, {"state": "ready"}, replace=fail_replace)

    assert not target.exists()
    assert not list(tmp_path.iterdir())
