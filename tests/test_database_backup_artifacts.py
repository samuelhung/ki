from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from zhiji_backend import _database_backup_fs as backup_fs
from zhiji_backend import database_backup
from zhiji_backend import database_backup_artifacts as artifacts


def _metadata(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
    }


def _publication_hooks() -> dict[str, object]:
    def publish(staged: Path, target: Path, identity: tuple[int, int]) -> None:
        artifacts.publish_backup(
            staged,
            target,
            identity,
            regular_file_identity=backup_fs.regular_file_identity,
        )

    return {
        "publish_backup": publish,
        "fsync_parent": artifacts.fsync_parent,
        "unlink_if_identity": artifacts.unlink_if_identity,
    }


def test_pinned_artifact_is_immutable_and_close_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "artifact"
    path.write_bytes(b"payload")
    fd = os.open(path, os.O_RDONLY)
    pinned = artifacts.PinnedArtifact(path, fd, (1, 2, 3, 4, 5, 6), "digest", 7)

    with pytest.raises(TypeError):
        hash(pinned)
    with pytest.raises(FrozenInstanceError):
        pinned.path = tmp_path / "replacement"

    pinned.close()
    pinned.close()

    assert pinned.fd == -1
    with pytest.raises(TypeError):
        hash(pinned)
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


def test_unlink_if_identity_preserves_replacement_racing_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"owned")
    expected_identity = (target.stat().st_dev, target.stat().st_ino)
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"foreign")
    foreign_identity = (foreign.stat().st_dev, foreign.stat().st_ino)
    real_rename = artifacts.os.rename
    raced = False

    def replace_before_isolation(source: Path, destination: Path) -> None:
        nonlocal raced
        if source == target and not raced:
            os.replace(foreign, target)
            raced = True
        real_rename(source, destination)

    monkeypatch.setattr(artifacts.os, "rename", replace_before_isolation)

    artifacts.unlink_if_identity(target, expected_identity)

    assert raced
    assert target.read_bytes() == b"foreign"
    assert (target.stat().st_dev, target.stat().st_ino) == foreign_identity
    evidence_dirs = list(tmp_path.glob(".target.unlink-*"))
    assert len(evidence_dirs) == 1
    assert stat.S_IMODE(evidence_dirs[0].stat().st_mode) == 0o700
    assert any(path.read_bytes() == b"foreign" for path in evidence_dirs[0].iterdir())


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
            **_publication_hooks(),
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
            **_publication_hooks(),
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
            **_publication_hooks(),
        )
        artifacts.write_json_atomic(
            atomic, payload, fsync_parent=artifacts.fsync_parent
        )
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

    artifacts.write_json_atomic(
        target, {"state": "ready"}, fsync_parent=artifacts.fsync_parent
    )

    assert events == ["fsync-file", "replace", "fsync-directory"]


def test_write_json_atomic_cleans_temp_file_when_replace_fails(
    tmp_path: Path,
) -> None:
    target = tmp_path / "marker.json"

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("injected replace failure")

    with pytest.raises(OSError, match="injected replace failure"):
        artifacts.write_json_atomic(
            target,
            {"state": "ready"},
            fsync_parent=artifacts.fsync_parent,
            replace=fail_replace,
        )

    assert not target.exists()
    assert not list(tmp_path.iterdir())


def test_write_json_atomic_cleanup_preserves_temp_path_replacement(
    tmp_path: Path,
) -> None:
    target = tmp_path / "marker.json"
    moved_temp = tmp_path / "owned-temp"
    foreign_identity: tuple[int, int] | None = None
    temp_path: Path | None = None

    def replace_temp_then_fail(source: Path, _target: Path) -> None:
        nonlocal foreign_identity, temp_path
        temp_path = source
        os.replace(source, moved_temp)
        source.write_bytes(b"foreign temp")
        foreign_identity = (source.stat().st_dev, source.stat().st_ino)
        raise OSError("injected publication failure")

    with pytest.raises(OSError, match="injected publication failure"):
        artifacts.write_json_atomic(
            target,
            {"state": "ready"},
            fsync_parent=lambda _path: None,
            replace=replace_temp_then_fail,
        )

    assert temp_path is not None
    assert temp_path.read_bytes() == b"foreign temp"
    assert (temp_path.stat().st_dev, temp_path.stat().st_ino) == foreign_identity
    assert moved_temp.exists()


@pytest.mark.parametrize("operation", ["exclusive", "atomic", "copy"])
def test_database_backup_composites_resolve_fsync_parent_through_facade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    source.write_text("{}", encoding="utf-8")

    class InjectedFailure(Exception):
        pass

    def fail_fsync(path: Path) -> None:
        assert path == target
        raise InjectedFailure("injected parent fsync failure")

    monkeypatch.setattr(database_backup, "_fsync_parent", fail_fsync)

    with pytest.raises(InjectedFailure, match="injected parent fsync failure"):
        if operation == "exclusive":
            database_backup._write_json_exclusive(target, {"state": "ready"})
        elif operation == "atomic":
            database_backup._write_json_atomic(target, {"state": "ready"})
        else:
            database_backup._copy_regular_file(source, target)

    assert target.exists() is (operation == "atomic")
    assert not list(tmp_path.glob(".intelligence-backup-*"))
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("operation", ["exclusive", "copy"])
def test_database_backup_publication_resolves_through_facade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    source.write_text("{}", encoding="utf-8")

    class InjectedFailure(Exception):
        pass

    def fail_publish(_staged: Path, _target: Path, _identity: tuple[int, int]) -> None:
        raise InjectedFailure("injected publication failure")

    monkeypatch.setattr(database_backup, "_publish_backup", fail_publish)

    with pytest.raises(InjectedFailure, match="injected publication failure"):
        if operation == "exclusive":
            database_backup._write_json_exclusive(target, {"state": "ready"})
        else:
            database_backup._copy_regular_file(source, target)

    assert not target.exists()
    assert not list(tmp_path.glob(".intelligence-backup-*"))


@pytest.mark.parametrize("operation", ["exclusive", "copy"])
def test_database_backup_failure_cleanup_resolves_through_facade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    source.write_text("{}", encoding="utf-8")
    real_publish = database_backup._publish_backup
    real_unlink = database_backup._unlink_if_identity
    cleanup_calls: list[tuple[Path, tuple[int, int]]] = []

    def publish_then_fail(staged: Path, target: Path, identity: tuple[int, int]) -> None:
        real_publish(staged, target, identity)
        raise OSError("injected post-publication failure")

    def tracked_unlink(path: Path, identity: tuple[int, int]) -> None:
        cleanup_calls.append((path, identity))
        real_unlink(path, identity)

    monkeypatch.setattr(database_backup, "_publish_backup", publish_then_fail)
    monkeypatch.setattr(database_backup, "_unlink_if_identity", tracked_unlink)

    with pytest.raises(OSError, match="injected post-publication failure"):
        if operation == "exclusive":
            database_backup._write_json_exclusive(target, {"state": "ready"})
        else:
            database_backup._copy_regular_file(source, target)

    assert [path for path, _identity in cleanup_calls] == [target]
    assert not target.exists()
    assert not list(tmp_path.glob(".intelligence-backup-*"))
