from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from zhiji_backend import database_backup, database_backup_restore_stages


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_private_restore_clone_cleanup_attempts_every_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    unlink_error = ValueError("clone unlink failed")

    class FailingPinned:
        def close(self) -> None:
            events.append("pinned")
            raise RuntimeError("pinned close failed")

    class FakeDirectory:
        def lstat(self):
            return SimpleNamespace(
                st_mode=stat.S_IFDIR | 0o700,
                st_dev=1,
                st_ino=2,
            )

        def rmdir(self) -> None:
            events.append("directory")

    def fail_unlink(_fd: int, _identity: tuple[int, int]) -> None:
        events.append("unlink")
        raise unlink_error

    def fail_close(fd: int) -> None:
        events.append(f"fd {fd}")
        raise OSError("directory fd close failed")

    monkeypatch.setattr(
        database_backup_restore_stages,
        "_unlink_identity_in_directory",
        fail_unlink,
    )
    monkeypatch.setattr(database_backup_restore_stages.os, "close", fail_close)
    clone = database_backup_restore_stages.PrivateRestoreClone(
        path=Path("/clone"),
        identity=(3, 4),
        directory=FakeDirectory(),
        directory_identity=(1, 2),
        directory_fd=17,
        pinned=FailingPinned(),
        expected_destination=None,
    )

    with pytest.raises(ValueError) as exc_info:
        clone.cleanup()

    assert exc_info.value is unlink_error
    assert events == ["unlink", "pinned", "fd 17", "directory"]
    assert exc_info.value.__notes__ == [
        "private clone pinned artifact cleanup failed: RuntimeError: "
        "pinned close failed",
        "private clone directory fd cleanup failed: OSError: "
        "directory fd close failed",
    ]


def test_private_restore_clone_copies_pinned_fd_and_uses_private_directory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    source.write_bytes(b'{"expected": true}')
    metadata = {
        "path": str(source),
        "sha256": _sha256(source),
        "size": source.stat().st_size,
    }
    pinned = database_backup._pin_artifact(metadata, "source")
    moved_source = tmp_path / "moved-source.json"
    os.replace(source, moved_source)
    source.write_bytes(b'{"attacker": true}')

    clone = database_backup_restore_stages.create_private_restore_clone(
        pinned,
        tmp_path / "destination.json",
        metadata,
        sqlite_backup=False,
        pin_artifact=database_backup._pin_artifact,
    )
    try:
        assert clone.path.read_bytes() == b'{"expected": true}'
        assert clone.identity == (clone.path.stat().st_dev, clone.path.stat().st_ino)
        assert clone.path.parent.parent == tmp_path
        assert clone.path.parent.stat().st_mode & 0o777 == 0o700
    finally:
        pinned.close()
        clone.cleanup()

    assert not clone.path.parent.exists()
    assert source.read_bytes() == b'{"attacker": true}'
    assert moved_source.read_bytes() == b'{"expected": true}'


def test_private_restore_publication_rejects_swapped_clone_inode(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    source.write_bytes(b'{"expected": true}')
    metadata = {
        "path": str(source),
        "sha256": _sha256(source),
        "size": source.stat().st_size,
    }
    pinned = database_backup._pin_artifact(metadata, "source")
    destination = tmp_path / "destination.json"
    destination.write_bytes(b'{"current": true}')
    clone = database_backup_restore_stages.create_private_restore_clone(
        pinned,
        destination,
        metadata,
        sqlite_backup=False,
        pin_artifact=database_backup._pin_artifact,
    )
    moved_expected = clone.path.with_name("moved-expected")
    replacement_identity: tuple[int, int] | None = None

    real_replace = database_backup._replace_staged_restore

    def swap_then_replace(stage: Path, target: Path) -> None:
        nonlocal replacement_identity
        os.replace(stage, moved_expected)
        stage.write_bytes(b'{"unrelated": true}')
        replacement_identity = (stage.stat().st_dev, stage.stat().st_ino)
        real_replace(stage, target)

    try:
        with pytest.raises(
            RuntimeError,
            match="rollback restore config publication identity mismatch",
        ):
            database_backup_restore_stages.replace_and_verify_private_restore(
                clone,
                destination,
                metadata,
                key="config",
                replace_staged_restore=swap_then_replace,
                restore_path_matches=database_backup._restore_path_matches,
            )
    finally:
        pinned.close()
        clone.cleanup()

    assert replacement_identity is not None
    assert destination.read_bytes() == b'{"current": true}'
    assert clone.path.read_bytes() == b'{"unrelated": true}'
    assert (clone.path.stat().st_dev, clone.path.stat().st_ino) == (
        replacement_identity
    )
    assert not moved_expected.exists()
    assert clone.directory.exists()


@pytest.mark.parametrize("destination_state", ["absent", "replaced"])
def test_restore_publication_never_overwrites_boundary_collision(
    tmp_path: Path,
    destination_state: str,
) -> None:
    stage = tmp_path / "stage"
    stage.write_bytes(b"restored")
    destination = tmp_path / "destination"
    if destination_state == "replaced":
        destination.write_bytes(b"expected current")
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"foreign")
    foreign_identity = (foreign.stat().st_dev, foreign.stat().st_ino)
    calls: list[tuple[Path, Path]] = []

    def collide_then_replace(source: Path, target: Path) -> None:
        calls.append((source, target))
        os.replace(foreign, destination)
        os.replace(source, target)

    with pytest.raises(RuntimeError, match="publication path collision"):
        database_backup_restore_stages.replace_staged_restore(
            stage,
            destination,
            replace=collide_then_replace,
            fsync_parent=lambda _path: None,
        )

    assert len(calls) == 1
    assert destination.read_bytes() == b"foreign"
    assert (destination.stat().st_dev, destination.stat().st_ino) == foreign_identity
    evidence = list(tmp_path.glob(".destination.publication-*"))
    if destination_state == "replaced":
        assert any(
            path.read_bytes() == b"expected current"
            for directory in evidence
            for path in directory.iterdir()
            if path.is_file()
        )


def test_private_restore_clone_failure_cleans_only_owned_inode(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    source.write_bytes(b'{"expected": true}')
    metadata = {
        "path": str(source),
        "sha256": _sha256(source),
        "size": source.stat().st_size,
    }
    pinned = database_backup._pin_artifact(metadata, "source")
    real_pin = database_backup._pin_artifact
    clone_path: Path | None = None
    moved_expected: Path | None = None

    def swap_before_clone_pin(
        clone_metadata: object, label: str, **kwargs: object
    ):
        nonlocal clone_path, moved_expected
        assert isinstance(clone_metadata, dict)
        clone_path = Path(str(clone_metadata["path"]))
        moved_expected = clone_path.with_name("moved-expected")
        payload = clone_path.read_bytes()
        os.replace(clone_path, moved_expected)
        clone_path.write_bytes(payload)
        return real_pin(clone_metadata, label, **kwargs)

    try:
        with pytest.raises(
            RuntimeError, match="rollback restore private clone verification failed"
        ):
            database_backup_restore_stages.create_private_restore_clone(
                pinned,
                tmp_path / "destination.json",
                metadata,
                sqlite_backup=False,
                pin_artifact=swap_before_clone_pin,
            )
    finally:
        pinned.close()

    assert clone_path is not None
    assert moved_expected is not None
    assert not moved_expected.exists()
    assert clone_path.exists()
    assert clone_path.read_bytes() == b'{"expected": true}'


def test_private_restore_publication_rejects_swapped_private_directory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    source.write_bytes(b'{"expected": true}')
    metadata = {
        "path": str(source),
        "sha256": _sha256(source),
        "size": source.stat().st_size,
    }
    pinned = database_backup._pin_artifact(metadata, "source")
    destination = tmp_path / "destination.json"
    destination.write_bytes(b'{"current": true}')
    clone = database_backup_restore_stages.create_private_restore_clone(
        pinned,
        destination,
        metadata,
        sqlite_backup=False,
        pin_artifact=database_backup._pin_artifact,
    )
    moved_directory = clone.directory.with_name(f"{clone.directory.name}.expected")
    real_replace = database_backup._replace_staged_restore

    def swap_directory_then_replace(stage: Path, target: Path) -> None:
        os.replace(clone.directory, moved_directory)
        clone.directory.mkdir(mode=0o700)
        stage.write_bytes(b'{"unrelated": true}')
        real_replace(stage, target)

    try:
        with pytest.raises(
            RuntimeError,
            match="rollback restore config publication identity mismatch",
        ):
            database_backup_restore_stages.replace_and_verify_private_restore(
                clone,
                destination,
                metadata,
                key="config",
                replace_staged_restore=swap_directory_then_replace,
                restore_path_matches=database_backup._restore_path_matches,
            )
    finally:
        pinned.close()
        clone.cleanup()

    assert destination.read_bytes() == b'{"current": true}'
    assert clone.path.read_bytes() == b'{"unrelated": true}'
