from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from zhiji_backend import database_backup, database_backup_restore_stages


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
