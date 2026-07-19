from __future__ import annotations

import os
import shutil
import sqlite3
import stat
import tempfile
from datetime import datetime
from pathlib import Path


BACKUP_TEMP_PREFIX = ".intelligence-backup-"


def _read_only_uri(path: Path) -> str:
    return f"{path.as_uri()}?mode=ro"


def _regular_file_identity(path: Path) -> tuple[int, int]:
    file_stat = os.lstat(path)
    if not stat.S_ISREG(file_stat.st_mode):
        raise RuntimeError(f"backup path is not a regular file: {path}")
    return file_stat.st_dev, file_stat.st_ino


def _verify_backup(target: Path) -> None:
    identity = _regular_file_identity(target)
    try:
        with sqlite3.connect(_read_only_uri(target), uri=True) as conn:
            result = [row[0] for row in conn.execute("PRAGMA integrity_check")]
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("backup integrity check failed") from exc

    if result != ["ok"]:
        raise RuntimeError("backup integrity check failed")
    if _regular_file_identity(target) != identity:
        raise RuntimeError("backup changed during integrity verification")


def _publish_backup(
    staged_backup: Path, target: Path, identity: tuple[int, int]
) -> None:
    if _regular_file_identity(staged_backup) != identity:
        raise RuntimeError("staged backup changed before publication")
    os.link(staged_backup, target, follow_symlinks=False)

    if _regular_file_identity(staged_backup) != identity:
        raise RuntimeError("staged backup changed during publication")
    if _regular_file_identity(target) != identity:
        raise RuntimeError("published backup identity mismatch")


def _unlink_if_identity(path: Path, identity: tuple[int, int]) -> None:
    try:
        file_stat = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISREG(file_stat.st_mode) and (
        file_stat.st_dev,
        file_stat.st_ino,
    ) == identity:
        os.unlink(path)


def backup_database(source: Path, output_dir: Path) -> Path:
    """Create and verify a timestamped SQLite backup without overwriting files."""
    requested_source = Path(source).expanduser()
    try:
        source = requested_source.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"database source does not exist: {requested_source}"
        ) from exc
    if not stat.S_ISREG(os.stat(source).st_mode):
        raise FileNotFoundError(f"database source does not exist: {source}")

    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve(strict=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = output_dir / f"intelligence-pre-cleanup-{timestamp}.sqlite"
    temp_dir = Path(tempfile.mkdtemp(prefix=BACKUP_TEMP_PREFIX, dir=output_dir))
    staged_backup = temp_dir / "backup.sqlite"
    staged_identity: tuple[int, int] | None = None

    try:
        with sqlite3.connect(_read_only_uri(source), uri=True) as src:
            with sqlite3.connect(staged_backup) as dst:
                src.backup(dst)
        _verify_backup(staged_backup)
        staged_identity = _regular_file_identity(staged_backup)
        _publish_backup(staged_backup, target, staged_identity)
    except Exception:
        if staged_identity is not None:
            _unlink_if_identity(target, staged_identity)
        raise
    finally:
        try:
            shutil.rmtree(temp_dir)
        except FileNotFoundError:
            pass

    return target
