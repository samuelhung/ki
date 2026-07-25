from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

SidecarIdentity = tuple[int, int]


def _identity(file_stat: os.stat_result) -> SidecarIdentity:
    return file_stat.st_dev, file_stat.st_ino


class SidecarPathCollision(RuntimeError):
    pass


@dataclass
class _PinnedSidecar:
    path: Path
    fd: int
    identity: SidecarIdentity
    recovery_path: Path | None = None

    @classmethod
    def capture(cls, path: Path) -> _PinnedSidecar | None:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            fd = os.open(path, flags)
        except FileNotFoundError:
            return None
        try:
            file_stat = os.fstat(fd)
            published = path.lstat()
            if (
                not stat.S_ISREG(file_stat.st_mode)
                or _identity(file_stat) != _identity(published)
            ):
                raise SidecarPathCollision(
                    f"rollback restore sidecar path collision at {path}"
                )
            return cls(path, fd, _identity(file_stat))
        except Exception:
            os.close(fd)
            raise

    def _matches_path(self, path: Path) -> bool:
        try:
            file_stat = path.lstat()
        except FileNotFoundError:
            return False
        return stat.S_ISREG(file_stat.st_mode) and _identity(file_stat) == self.identity

    def quarantine(self, recovery_dir: Path) -> None:
        recovery_path = recovery_dir / self.path.name
        moved_path = recovery_dir / f"{self.path.name}.moved"
        self.recovery_path = recovery_path
        try:
            os.link(self.path, recovery_path, follow_symlinks=False)
        except (FileExistsError, FileNotFoundError, OSError) as exc:
            raise SidecarPathCollision(
                f"rollback restore sidecar path collision at {self.path}"
            ) from exc
        if not self._matches_path(recovery_path):
            raise SidecarPathCollision(
                f"rollback restore sidecar path collision at {self.path}"
            )
        try:
            os.rename(self.path, moved_path)
        except OSError as exc:
            raise SidecarPathCollision(
                f"rollback restore sidecar path collision at {self.path}"
            ) from exc
        if not self._matches_path(moved_path):
            raise SidecarPathCollision(
                f"rollback restore sidecar path collision at {self.path}"
            )
        moved_path.unlink()

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


@dataclass
class SidecarDisposition:
    database_path: Path
    database_identity: SidecarIdentity
    paths: tuple[Path, Path]
    pinned: tuple[_PinnedSidecar | None, _PinnedSidecar | None]
    recovery_dir: Path | None = None

    @classmethod
    def capture(cls, database_path: Path) -> SidecarDisposition:
        database_identity = _identity(database_path.lstat())
        paths = tuple(Path(f"{database_path}{suffix}") for suffix in ("-wal", "-shm"))
        captured: list[_PinnedSidecar | None] = []
        try:
            for path in paths:
                captured.append(_PinnedSidecar.capture(path))
        except Exception:
            for sidecar in captured:
                if sidecar is not None:
                    sidecar.close()
            raise
        return cls(
            database_path,
            database_identity,
            paths,
            (captured[0], captured[1]),
        )

    def quarantine(self) -> None:
        present = [sidecar for sidecar in self.pinned if sidecar is not None]
        if present:
            self.recovery_dir = Path(
                tempfile.mkdtemp(
                    prefix=f".{self.paths[0].name}.sidecars-",
                    dir=self.paths[0].parent,
                )
            )
            os.chmod(self.recovery_dir, 0o700)
            for sidecar in present:
                sidecar.quarantine(self.recovery_dir)
        self.assert_clear()

    def assert_clear(self) -> None:
        for path in self.paths:
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            raise SidecarPathCollision(
                f"rollback restore sidecar path collision at {path}"
            )

    def cleanup(self) -> None:
        self.assert_clear()
        self._cleanup_recovery()

    def restore_if_database_unchanged(self) -> None:
        try:
            current_identity = _identity(self.database_path.lstat())
        except FileNotFoundError:
            return
        if current_identity != self.database_identity:
            return
        for sidecar in self.pinned:
            if sidecar is None or sidecar.recovery_path is None:
                continue
            try:
                os.link(sidecar.recovery_path, sidecar.path, follow_symlinks=False)
            except (FileExistsError, OSError) as exc:
                raise SidecarPathCollision(
                    f"rollback restore sidecar path collision at {sidecar.path}"
                ) from exc
            if not sidecar._matches_path(sidecar.path):
                raise SidecarPathCollision(
                    f"rollback restore sidecar path collision at {sidecar.path}"
                )
        self._cleanup_recovery()

    def _cleanup_recovery(self) -> None:
        if self.recovery_dir is None:
            return
        for sidecar in self.pinned:
            if sidecar is not None and sidecar.recovery_path is not None:
                sidecar.recovery_path.unlink(missing_ok=True)
        self.recovery_dir.rmdir()
        self.recovery_dir = None

    def close(self) -> None:
        for sidecar in self.pinned:
            if sidecar is not None:
                sidecar.close()


def restore_after_failure(
    disposition: SidecarDisposition | None, failure: Exception
) -> Exception:
    if disposition is None:
        return failure
    try:
        disposition.restore_if_database_unchanged()
    except Exception as sidecar_failure:
        return sidecar_failure
    return failure
