from __future__ import annotations

import io
import logging
import logging.handlers
import os
import stat
from collections.abc import Callable, Iterator
from contextlib import suppress
from pathlib import Path
from re import Pattern

logger = logging.getLogger("zhiji_backend.security.redaction")


def _reject_symlink(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(mode):
        raise OSError(f"refusing symlink log target: {path.name}")
    if not stat.S_ISREG(mode):
        raise OSError(f"refusing non-regular log target: {path.name}")
    return True


def _rotation_candidates(
    log_path: Path,
    ext_match: Pattern[str] | None,
    namer: Callable[[str], str] | None,
) -> Iterator[Path]:
    if ext_match is None:
        return
    for path in log_path.parent.iterdir():
        if namer is None:
            prefix = f"{log_path.name}."
            if not path.name.startswith(prefix):
                continue
            suffix = path.name[len(prefix) :]
            if ext_match.fullmatch(suffix):
                yield path
            continue
        match = ext_match.search(path.name)
        while match is not None:
            rotated_name = namer(f"{log_path}.{match.group(0)}")
            if Path(rotated_name).name == path.name:
                yield path
                break
            match = ext_match.search(path.name, match.start() + 1)


def _harden_existing_logs(
    log_path: Path,
    *,
    ext_match: Pattern[str] | None = None,
    namer: Callable[[str], str] | None = None,
) -> None:
    paths = (log_path, *_rotation_candidates(log_path, ext_match, namer))
    for path in paths:
        try:
            mode = path.lstat().st_mode
        except OSError:
            continue
        if stat.S_ISREG(mode):
            try:
                path.chmod(0o600, follow_symlinks=False)
            except OSError as exc:
                if path == log_path:
                    raise
                logger.warning(
                    "Unable to harden rotated log file=%s error_class=%s",
                    path.name,
                    type(exc).__name__,
                )


def _secure_rotator_destination(path: Path) -> None:
    if _reject_symlink(path):
        path.chmod(0o600, follow_symlinks=False)
        return

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


class SecureTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Timed rotation with no-follow creation and mode 0600 for every log."""

    def __init__(self, filename: str | os.PathLike[str], *args, **kwargs):
        log_path = Path(filename)
        _reject_symlink(log_path)
        _harden_existing_logs(log_path)
        super().__init__(str(log_path), *args, **kwargs)
        _harden_existing_logs(
            log_path,
            ext_match=self.extMatch,
            namer=self.namer,
        )

    def _open(self):
        path = Path(self.baseFilename)
        _reject_symlink(path)
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
        except Exception:
            with suppress(Exception):
                os.close(fd)
            raise

        binary_mode = self.mode if "b" in self.mode else f"{self.mode}b"
        try:
            raw = io.FileIO(fd, binary_mode, closefd=True)
        except Exception:
            with suppress(Exception):
                os.close(fd)
            raise
        try:
            return io.TextIOWrapper(
                raw,
                encoding=self.encoding,
                errors=self.errors,
                newline=None,
            )
        except Exception:
            with suppress(Exception):
                raw.close()
            raise

    def rotate(self, source: str, dest: str) -> None:
        source_path = Path(source)
        dest_path = Path(dest)
        if not _reject_symlink(source_path):
            return
        _reject_symlink(dest_path)
        custom_rotator = callable(self.rotator)
        if custom_rotator:
            _secure_rotator_destination(dest_path)
        super().rotate(source, dest)
        if not _reject_symlink(dest_path):
            if custom_rotator:
                dest_path.chmod(0o600, follow_symlinks=False)
            return
        dest_path.chmod(0o600, follow_symlinks=False)

    def doRollover(self) -> None:  # noqa: N802 - logging API name
        super().doRollover()
        _harden_existing_logs(
            Path(self.baseFilename),
            ext_match=self.extMatch,
            namer=self.namer,
        )
