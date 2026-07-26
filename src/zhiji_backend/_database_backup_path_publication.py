from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from ._database_backup_fs import identity, restore_displaced
from ._database_backup_identity_cleanup import isolate_and_unlink

PathIdentity = tuple[int, int]
PathSignature = tuple[int, int, int]

_EXPECTED_DESTINATION: ContextVar[tuple[Path, PathSignature] | None] = ContextVar(
    "database_backup_expected_publication_destination", default=None
)


@contextmanager
def expected_destination_publication(path: Path, signature: PathSignature):
    token = _EXPECTED_DESTINATION.set((path, signature))
    try:
        yield
    finally:
        _EXPECTED_DESTINATION.reset(token)


def bound_destination_signature(path: Path) -> PathSignature | None:
    expectation = _EXPECTED_DESTINATION.get()
    if expectation is None or expectation[0] != path:
        return None
    return expectation[1]


def path_signature(path: Path) -> PathSignature:
    file_stat = path.lstat()
    return file_stat.st_dev, file_stat.st_ino, file_stat.st_mode


def _matches(path: Path, expected: PathSignature) -> bool:
    try:
        current = path.lstat()
    except FileNotFoundError:
        return False
    return (
        identity(current) == expected[:2]
        and stat.S_IFMT(current.st_mode) == stat.S_IFMT(expected[2])
    )


def _present(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _restore(source: Path, destination: Path) -> bool:
    try:
        return restore_displaced(source, destination)
    except (FileNotFoundError, OSError):
        return False


def _remove_empty(directory: Path) -> None:
    try:
        directory.rmdir()
    except OSError:
        pass


def _fsync_parent(path: Path) -> None:
    fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_marker_parent(path: Path) -> None:
    _fsync_parent(path)


def publish_from_private_replace(
    source: Path,
    destination: Path,
    *,
    source_identity: PathIdentity,
    expected_destination: PathSignature | None,
    replace: Callable[[Path, Path], None],
    fsync_parent: Callable[[Path], None],
    collision_message: str = "publication path collision",
    on_published: Callable[[], None] | None = None,
) -> None:
    directory = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.publication-", dir=destination.parent
        )
    )
    os.chmod(directory, 0o700)
    displaced = directory / "displaced-destination"
    publication = directory / "publication-source"

    if expected_destination is None:
        try:
            destination.lstat()
        except FileNotFoundError:
            pass
        else:
            _remove_empty(directory)
            raise RuntimeError(collision_message)
    else:
        try:
            os.rename(destination, displaced)
        except FileNotFoundError as exc:
            _remove_empty(directory)
            raise RuntimeError(collision_message) from exc
        if not _matches(displaced, expected_destination):
            _restore(displaced, destination)
            raise RuntimeError(
                f"{collision_message}; preserved recovery evidence at {directory}"
            )

    try:
        replace(source, publication)
    except Exception as exc:
        restored = not _present(displaced)
        if not restored:
            restored = _restore(displaced, destination)
            if restored:
                displaced.unlink()
        _remove_empty(directory)
        if not restored:
            raise RuntimeError(
                f"{collision_message}; preserved recovery evidence at {directory}"
            ) from exc
        raise

    try:
        published_stat = publication.lstat()
    except FileNotFoundError as exc:
        _restore(displaced, destination)
        raise RuntimeError(
            f"{collision_message}; preserved recovery evidence at {directory}"
        ) from exc
    if (
        not stat.S_ISREG(published_stat.st_mode)
        or identity(published_stat) != source_identity
    ):
        _restore(publication, source)
        _restore(displaced, destination)
        raise RuntimeError(
            f"{collision_message}; preserved recovery evidence at {directory}"
        )

    try:
        os.link(publication, destination, follow_symlinks=False)
    except OSError as exc:
        _restore(publication, source)
        _restore(displaced, destination)
        raise RuntimeError(
            f"{collision_message}; preserved recovery evidence at {directory}"
        ) from exc

    try:
        if on_published is not None:
            on_published()
        fsync_parent(destination)
    except Exception:
        raise
    if not _matches(destination, (*source_identity, published_stat.st_mode)):
        _restore(publication, source)
        raise RuntimeError(
            f"{collision_message}; preserved recovery evidence at {directory}"
        )

    publication.unlink()
    if _present(displaced):
        displaced.unlink()
    directory.rmdir()


def transition_marker_exclusive(
    source: Path,
    destination: Path,
    *,
    source_identity: PathIdentity,
    replace: Callable[[Path, Path], None],
) -> None:
    directory = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.transition-", dir=destination.parent
        )
    )
    os.chmod(directory, 0o700)
    candidate = directory / "ready-marker-candidate"
    moved = directory / "ready-marker"
    expected_mode = source.lstat().st_mode
    expected_signature = (*source_identity, expected_mode)
    try:
        os.link(source, destination, follow_symlinks=False)
    except FileExistsError as exc:
        if not _matches(destination, expected_signature):
            directory.rmdir()
            raise RuntimeError("marker path collision") from exc
    except FileNotFoundError:
        directory.rmdir()
        raise

    if not _matches(source, expected_signature) or not _matches(
        destination, expected_signature
    ):
        isolate_and_unlink(destination, source_identity)
        _remove_empty(directory)
        raise RuntimeError(
            f"marker path collision; preserved recovery evidence at {directory}"
        )

    _fsync_parent(destination)
    os.link(source, candidate, follow_symlinks=False)

    try:
        replace(candidate, moved)
    except FileNotFoundError:
        _remove_empty(directory)
        raise
    except Exception:
        isolate_and_unlink(destination, source_identity)
        _remove_empty(directory)
        raise
    if not _matches(source, expected_signature) or not _matches(
        moved, expected_signature
    ) or not _matches(
        destination, expected_signature
    ):
        isolate_and_unlink(destination, source_identity)
        raise RuntimeError(
            f"marker path collision; preserved recovery evidence at {directory}"
        )
    moved.unlink()
    directory.rmdir()


def remove_marker_identity(path: Path, expected: PathIdentity) -> None:
    displaced = isolate_and_unlink(path, expected)
    if displaced is not None:
        raise RuntimeError(
            f"marker path collision; preserved recovery evidence at {displaced.parent}"
        )
    _fsync_parent(path)
