from __future__ import annotations

import os
import tempfile
from pathlib import Path

from . import _database_backup_fs

FileIdentity = _database_backup_fs.FileIdentity
copy_fd = _database_backup_fs.copy_fd
hash_fd = _database_backup_fs.hash_fd
identity = _database_backup_fs.identity
read_fd = _database_backup_fs.read_fd
restore_displaced = _database_backup_fs.restore_displaced


def create_recovery_copy(
    canonical: Path,
    fd: int,
    filename: str,
    directory: Path | None = None,
) -> tuple[Path, Path, FileIdentity]:
    if directory is None or not directory.exists():
        directory = Path(
            tempfile.mkdtemp(
                prefix=f".{canonical.name}.recovery-", dir=canonical.parent
            )
        )
        os.chmod(directory, 0o700)
    recovery_path = directory / filename
    return directory, recovery_path, copy_fd(fd, recovery_path)


def move_to_private(source: Path, destination: Path) -> None:
    os.rename(source, destination)


def path_absent(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    return False
