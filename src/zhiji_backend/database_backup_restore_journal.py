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

JournalIdentity = tuple[int, int]


def _identity(file_stat: os.stat_result) -> JournalIdentity:
    return file_stat.st_dev, file_stat.st_ino


def _hash_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, 1024 * 1024):
        digest.update(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def _read_fd(fd: int) -> bytes:
    chunks: list[bytes] = []
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, 1024 * 1024):
        chunks.append(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return b"".join(chunks)


class JournalPathCollision(RuntimeError):
    pass


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
    published_fd: int = -1
    published_identity: JournalIdentity | None = None
    published_sha256: str | None = None
    published_size: int | None = None

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
            raw = _read_fd(fd)
            after = os.fstat(fd)
            published = journal_path.lstat()
            if (
                not stat.S_ISREG(before.st_mode)
                or _identity(before) != expected_identity
                or _identity(after) != expected_identity
                or _identity(published) != expected_identity
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
            _identity(current) != self.identity
            or current.st_size != self.size
            or _hash_fd(self.fd) != self.sha256
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
                or _identity(candidate) != self.identity
                or _identity(published) != self.identity
                or candidate.st_size != self.size
                or _hash_fd(candidate_fd) != self.sha256
            ):
                raise RuntimeError("rollback restore trusted journal changed")
        finally:
            os.close(candidate_fd)

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
            self._assert_path(self.journal_path)
            os.replace(self.journal_path, recovery_path)
            self._assert_path(recovery_path)
            fsync_parent(recovery_path)
            fsync_parent(self.journal_path)
        except Exception:
            try:
                recovery_dir.rmdir()
            except OSError:
                pass
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
        self._assert_path(self.recovery_path)
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
        self._assert_path(self.journal_path)
        self.published_fd = os.open(
            self.journal_path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        self.published_identity = self.identity
        self.published_sha256 = self.sha256
        self.published_size = self.size
        self.assert_published()
        fsync_parent(self.journal_path)
        self.assert_published()
        self._remove_quarantine()
        self.assert_published()

    def republish_payload(
        self,
        payload: dict[str, Any],
        *,
        fsync_parent: Callable[[Path], None],
    ) -> None:
        if self.recovery_path is None or self.recovery_dir is None:
            raise RuntimeError("rollback restore journal was not quarantined")
        self._assert_fd()
        self._assert_path(self.recovery_path)
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
        staged_identity = _identity(staged_stat)
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
        self._remove_quarantine()
        staged.unlink()
        if self.recovery_dir is not None:
            self.recovery_dir.rmdir()
            self.recovery_dir = None
        self.assert_published()

    def assert_published(self) -> None:
        if self.published_fd < 0:
            raise RuntimeError("rollback restore journal was not republished")
        published = os.fstat(self.published_fd)
        current = self.journal_path.lstat()
        if (
            _identity(published) != self.published_identity
            or _identity(current) != self.published_identity
            or published.st_size != self.published_size
            or _hash_fd(self.published_fd) != self.published_sha256
        ):
            raise RuntimeError("rollback restore journal republish verification failed")

    def complete(self, *, fsync_parent: Callable[[Path], None]) -> None:
        if self.recovery_path is None:
            raise RuntimeError("rollback restore journal was not quarantined")
        self._assert_fd()
        self._assert_path(self.recovery_path)
        if not self._canonical_path_is_absent():
            raise self._collision()
        self._remove_quarantine()
        fsync_parent(self.journal_path)

    def _remove_quarantine(self) -> None:
        if self.recovery_path is None or self.recovery_dir is None:
            return
        self._assert_path(self.recovery_path)
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
