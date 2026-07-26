from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path

from ._database_backup_fs import identity, restore_displaced

Identity = tuple[int, int]


def isolate_and_unlink(
    path: Path,
    expected: Identity,
    *,
    collision_destination: Path | None = None,
    validator: Callable[[Path], object] | None = None,
) -> Path | None:
    isolation_dir = Path(
        tempfile.mkdtemp(prefix=f".{path.name}.unlink-", dir=path.parent)
    )
    os.chmod(isolation_dir, 0o700)
    isolated = isolation_dir / "isolated"
    try:
        os.rename(path, isolated)
    except FileNotFoundError:
        isolation_dir.rmdir()
        return None
    file_stat = isolated.lstat()
    valid = True
    if validator is not None:
        try:
            validator(isolated)
        except (OSError, RuntimeError):
            valid = False
    matched = (
        stat.S_ISREG(file_stat.st_mode)
        and identity(file_stat) == expected
        and valid
    )
    if matched:
        isolated.unlink()
        isolation_dir.rmdir()
        return None
    restore_displaced(isolated, collision_destination or path)
    return isolated
