"""Simple SQLite migration manager — no external deps.

Usage:
    from .migrations import ensure_migrations
    ensure_migrations(db_path)  # run before init_db()
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

MigrationFn = Callable[[], None]
_registry: list[tuple[str, MigrationFn]] = []


def register(name: str) -> Callable[[MigrationFn], MigrationFn]:
    """Decorator to register a migration by name."""

    def decorator(fn: MigrationFn) -> MigrationFn:
        _registry.append((name, fn))
        return fn

    return decorator


def ensure_migrations(db_path: Path) -> None:
    """Apply any pending migrations to the database."""
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    conn.execute(
        """CREATE TABLE IF NOT EXISTS _migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )
    conn.commit()

    applied = {row[0] for row in conn.execute("SELECT name FROM _migrations")}

    for name, fn in _registry:
        if name in applied:
            continue
        logger.info("Applying migration: %s", name)
        fn()
        conn.execute("INSERT INTO _migrations (name) VALUES (?)", (name,))
        conn.commit()
        logger.info("Migration applied: %s", name)

    conn.close()
