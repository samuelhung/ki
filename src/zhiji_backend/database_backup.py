from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


def _verify_backup(target: Path) -> None:
    try:
        with sqlite3.connect(target) as conn:
            result = [row[0] for row in conn.execute("PRAGMA integrity_check")]
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("backup integrity check failed") from exc

    if result != ["ok"]:
        raise RuntimeError("backup integrity check failed")


def backup_database(source: Path, output_dir: Path) -> Path:
    """Create and verify a timestamped SQLite backup without overwriting files."""
    source = Path(source).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"database source does not exist: {source}")

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = output_dir / f"intelligence-pre-cleanup-{timestamp}.sqlite"

    with target.open("xb"):
        pass

    try:
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
        _verify_backup(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise

    return target
