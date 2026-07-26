from __future__ import annotations

import logging
import logging.handlers
import os
import stat
from pathlib import Path

logger = logging.getLogger("zhiji_backend.security.redaction")


def _reject_symlink(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        raise OSError(f"refusing symlink log target: {path.name}")
    if not stat.S_ISREG(mode):
        raise OSError(f"refusing non-regular log target: {path.name}")


def _harden_existing_logs(log_path: Path) -> None:
    for path in log_path.parent.glob(f"{log_path.name}*"):
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


class SecureTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Timed rotation with no-follow creation and mode 0600 for every log."""

    def __init__(self, filename: str | os.PathLike[str], *args, **kwargs):
        log_path = Path(filename)
        _reject_symlink(log_path)
        _harden_existing_logs(log_path)
        super().__init__(str(log_path), *args, **kwargs)
        _harden_existing_logs(log_path)

    def _open(self):
        path = Path(self.baseFilename)
        _reject_symlink(path)
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
            return open(
                fd,
                self.mode,
                encoding=self.encoding,
                errors=self.errors,
                closefd=True,
            )
        except Exception:
            os.close(fd)
            raise

    def rotate(self, source: str, dest: str) -> None:
        source_path = Path(source)
        dest_path = Path(dest)
        _reject_symlink(source_path)
        _reject_symlink(dest_path)
        super().rotate(source, dest)
        dest_path.chmod(0o600, follow_symlinks=False)

    def doRollover(self) -> None:  # noqa: N802 - logging API name
        super().doRollover()
        _harden_existing_logs(Path(self.baseFilename))
