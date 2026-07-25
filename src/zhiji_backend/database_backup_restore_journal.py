from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database_backup_restore_private import (
    FileIdentity,
    copy_fd,
    hash_fd,
    identity,
    move_to_private,
    read_fd,
)

JournalIdentity = FileIdentity


class JournalPathCollision(RuntimeError):
    pass


_move_to_private = move_to_private


@dataclass
class TrustedJournalDisposition:
    journal_path: Path
    fd: int
    identity: JournalIdentity
    sha256: str
    size: int
    raw: bytes
    recovery_dir: Path | None = None
    recovery_path: Path | None = None
    recovery_identity: JournalIdentity | None = None
    published_fd: int = -1
    published_identity: JournalIdentity | None = None
    published_sha256: str | None = None
    published_size: int | None = None
    require_canonical_absence_for_cleanup: bool = False

    @classmethod
    def capture(
        cls,
        journal_path: Path,
        expected_identity: JournalIdentity,
        expected_payload: dict[str, Any],
    ) -> TrustedJournalDisposition:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            fd = os.open(journal_path, flags)
        except OSError as exc:
            raise RuntimeError(
                "rollback restore journal changed during validation"
            ) from exc
        try:
            before = os.fstat(fd)
            raw = read_fd(fd)
            after = os.fstat(fd)
            published = journal_path.lstat()
            if (
                not stat.S_ISREG(before.st_mode)
                or identity(before) != expected_identity
                or identity(after) != expected_identity
                or identity(published) != expected_identity
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns
                or len(raw) != after.st_size
                or json.loads(raw.decode("utf-8")) != expected_payload
            ):
                raise RuntimeError(
                    "rollback restore journal changed during validation"
                )
            return cls(
                journal_path=journal_path,
                fd=fd,
                identity=expected_identity,
                sha256=hashlib.sha256(raw).hexdigest(),
                size=len(raw),
                raw=raw,
            )
        except Exception:
            os.close(fd)
            raise

    @property
    def disposed(self) -> bool:
        return self.recovery_path is not None

    def _assert_fd(self) -> None:
        current = os.fstat(self.fd)
        if (
            identity(current) != self.identity
            or current.st_size != self.size
            or hash_fd(self.fd) != self.sha256
        ):
            raise RuntimeError("rollback restore trusted journal changed")

    def _assert_path(self, path: Path) -> None:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        candidate_fd = os.open(path, flags)
        try:
            candidate = os.fstat(candidate_fd)
            published = path.lstat()
            if (
                not stat.S_ISREG(candidate.st_mode)
                or identity(candidate) != self.identity
                or identity(published) != self.identity
                or candidate.st_size != self.size
                or hash_fd(candidate_fd) != self.sha256
            ):
                raise RuntimeError("rollback restore trusted journal changed")
        finally:
            os.close(candidate_fd)

    def _assert_recovery(self) -> None:
        if self.recovery_path is None or self.recovery_identity is None:
            raise RuntimeError("rollback restore trusted journal is unavailable")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        recovery_fd = os.open(self.recovery_path, flags)
        try:
            file_stat = os.fstat(recovery_fd)
            published = self.recovery_path.lstat()
            if (
                not stat.S_ISREG(file_stat.st_mode)
                or identity(file_stat) != self.recovery_identity
                or identity(published) != self.recovery_identity
                or file_stat.st_size != self.size
                or hash_fd(recovery_fd) != self.sha256
            ):
                raise RuntimeError("rollback restore trusted journal changed")
        finally:
            os.close(recovery_fd)

    def _copy_fd_to_recovery(self, fd: int, path: Path) -> JournalIdentity:
        return copy_fd(fd, path)

    def _publish_recovery(self, recovery_path: Path) -> None:
        try:
            os.link(self.journal_path, recovery_path, follow_symlinks=False)
            self._assert_path(recovery_path)
            self.recovery_identity = self.identity
        except (OSError, RuntimeError):
            recovery_path.unlink(missing_ok=True)
            self.recovery_identity = self._copy_fd_to_recovery(self.fd, recovery_path)
        self._assert_recovery()

    def quarantine(self, *, fsync_parent: Callable[[Path], None]) -> None:
        self._assert_fd()
        recovery_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{self.journal_path.name}.recovery-",
                dir=self.journal_path.parent,
            )
        )
        os.chmod(recovery_dir, 0o700)
        recovery_path = recovery_dir / self.journal_path.name
        self.recovery_dir = recovery_dir
        self.recovery_path = recovery_path
        try:
            self._publish_recovery(recovery_path)
            fsync_parent(recovery_path)
            moved_path = recovery_dir / "canonical-journal"
            _move_to_private(self.journal_path, moved_path)
            try:
                self._assert_path(moved_path)
            except Exception as exc:
                raise self._collision() from exc
            moved_path.unlink()
            if not self._canonical_path_is_absent():
                raise self._collision()
            fsync_parent(self.journal_path)
        except Exception:
            raise

    def _collision(self) -> JournalPathCollision:
        return JournalPathCollision(
            f"rollback restore journal path collision at {self.journal_path}"
        )

    def _canonical_path_is_absent(self) -> bool:
        try:
            self.journal_path.lstat()
        except FileNotFoundError:
            return True
        return False

    def republish(self, *, fsync_parent: Callable[[Path], None]) -> None:
        if self.recovery_path is None:
            raise RuntimeError("rollback restore journal was not quarantined")
        self._assert_fd()
        self._assert_recovery()
        if not self._canonical_path_is_absent():
            raise self._collision()
        try:
            os.link(
                self.recovery_path,
                self.journal_path,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise self._collision() from exc
        self.published_fd = os.open(
            self.journal_path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        self.published_identity = self.recovery_identity
        self.published_sha256 = self.sha256
        self.published_size = self.size
        self.assert_published()
        fsync_parent(self.journal_path)
        self.assert_published()
        try:
            self._remove_quarantine()
            self._assert_published_or_collision()
        except Exception:
            self._preserve_published_copy()
            raise

    def republish_payload(
        self,
        payload: dict[str, Any],
        *,
        fsync_parent: Callable[[Path], None],
    ) -> None:
        if self.recovery_path is None or self.recovery_dir is None:
            raise RuntimeError("rollback restore journal was not quarantined")
        self._assert_fd()
        self._assert_recovery()
        if not self._canonical_path_is_absent():
            raise self._collision()
        raw = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        staged = self.recovery_dir / "republished-journal.json"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(staged, flags, 0o600)
        try:
            view = memoryview(raw)
            while view:
                view = view[os.write(fd, view) :]
            os.fsync(fd)
            staged_stat = os.fstat(fd)
        finally:
            os.close(fd)
        staged_identity = identity(staged_stat)
        try:
            os.link(staged, self.journal_path, follow_symlinks=False)
        except FileExistsError as exc:
            raise self._collision() from exc
        self.published_fd = os.open(
            self.journal_path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        self.published_identity = staged_identity
        self.published_sha256 = hashlib.sha256(raw).hexdigest()
        self.published_size = len(raw)
        self.assert_published()
        fsync_parent(self.journal_path)
        self.assert_published()
        try:
            self._remove_quarantine()
            self._assert_published_or_collision()
            staged.unlink()
            self._assert_published_or_collision()
            if self.recovery_dir is not None:
                self.recovery_dir.rmdir()
                self.recovery_dir = None
            self._assert_published_or_collision()
        except Exception:
            self._preserve_published_copy()
            raise

    def assert_published(self) -> None:
        if self.published_fd < 0:
            raise RuntimeError("rollback restore journal was not republished")
        published = os.fstat(self.published_fd)
        current = self.journal_path.lstat()
        if (
            identity(published) != self.published_identity
            or identity(current) != self.published_identity
            or published.st_size != self.published_size
            or hash_fd(self.published_fd) != self.published_sha256
        ):
            raise RuntimeError("rollback restore journal republish verification failed")

    def complete(
        self,
        *,
        fsync_parent: Callable[[Path], None],
        final_validator: Callable[[], object],
    ) -> None:
        if self.recovery_path is None:
            raise RuntimeError("rollback restore journal was not quarantined")
        self._assert_fd()
        self._assert_recovery()
        if not self._canonical_path_is_absent():
            raise self._collision()
        fsync_parent(self.journal_path)
        if not self._canonical_path_is_absent():
            raise self._collision()
        final_validator()
        self.require_canonical_absence_for_cleanup = True
        try:
            self._remove_quarantine()
        finally:
            self.require_canonical_absence_for_cleanup = False

    def _assert_published_or_collision(self) -> None:
        try:
            self.assert_published()
        except (FileNotFoundError, OSError, RuntimeError) as exc:
            raise self._collision() from exc

    def _preserve_published_copy(self) -> None:
        if self.recovery_path is not None and self.recovery_path.exists():
            return
        if self.published_fd < 0:
            return
        recovery_dir = self.recovery_dir
        if recovery_dir is None or not recovery_dir.exists():
            recovery_dir = Path(
                tempfile.mkdtemp(
                    prefix=f".{self.journal_path.name}.recovery-",
                    dir=self.journal_path.parent,
                )
            )
            os.chmod(recovery_dir, 0o700)
        recovery_path = recovery_dir / "trusted-republished-journal.json"
        self.recovery_identity = self._copy_fd_to_recovery(
            self.published_fd, recovery_path
        )
        self.recovery_dir = recovery_dir
        self.recovery_path = recovery_path

    def _remove_quarantine(self) -> None:
        if self.recovery_path is None or self.recovery_dir is None:
            return
        if (
            self.require_canonical_absence_for_cleanup
            and not self._canonical_path_is_absent()
        ):
            raise self._collision()
        if self.published_fd >= 0:
            self._assert_published_or_collision()
        self._assert_recovery()
        os.unlink(self.recovery_path)
        self.recovery_path = None
        try:
            self.recovery_dir.rmdir()
        except OSError:
            return
        self.recovery_dir = None

    def close(self) -> None:
        if self.published_fd >= 0:
            os.close(self.published_fd)
            self.published_fd = -1
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
