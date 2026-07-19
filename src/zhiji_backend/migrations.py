"""Simple SQLite migration manager — no external deps.

Usage:
    from .migrations import ensure_migrations
    ensure_migrations(db_path)  # run before init_db()
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

MigrationFn = Callable[[sqlite3.Connection], None]
_registry: list[tuple[str, MigrationFn]] = []
MIGRATION_BUSY_TIMEOUT_MS = 1000
MIGRATION_LOCK_RETRY_SECONDS = 60.0
MIGRATION_LOCK_RETRY_INITIAL_DELAY_SECONDS = 0.05
MIGRATION_LOCK_RETRY_MAX_DELAY_SECONDS = 1.0
_monotonic = time.monotonic
_sleep = time.sleep


def register(name: str) -> Callable[[MigrationFn], MigrationFn]:
    """Decorator to register a migration by name."""

    def decorator(fn: MigrationFn) -> MigrationFn:
        if any(existing_name == name for existing_name, _fn in _registry):
            raise ValueError(f"duplicate migration name: {name}")
        if _registry and name <= _registry[-1][0]:
            raise ValueError(
                "migrations must be registered in chronological order: "
                f"{name} must follow {_registry[-1][0]}"
            )
        _registry.append((name, fn))
        return fn

    return decorator


def _is_lock_error(exc: sqlite3.OperationalError) -> bool:
    error_code = getattr(exc, "sqlite_errorcode", None)
    if error_code is not None:
        return error_code & 0xFF in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
    message = str(exc).lower()
    return "database is locked" in message or "database table is locked" in message


def _begin_immediate_with_retry(conn: sqlite3.Connection) -> None:
    deadline = _monotonic() + MIGRATION_LOCK_RETRY_SECONDS
    delay = MIGRATION_LOCK_RETRY_INITIAL_DELAY_SECONDS

    while True:
        try:
            conn.execute("BEGIN IMMEDIATE")
            return
        except sqlite3.OperationalError as exc:
            conn.rollback()
            remaining = deadline - _monotonic()
            if not _is_lock_error(exc) or remaining <= 0:
                raise
            _sleep(min(delay, remaining))
            delay = min(delay * 2, MIGRATION_LOCK_RETRY_MAX_DELAY_SECONDS)


def ensure_migrations(db_path: Path) -> None:
    """Apply any pending migrations to the database."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(f"PRAGMA busy_timeout={MIGRATION_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

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
            try:
                _begin_immediate_with_retry(conn)
                if conn.execute(
                    "SELECT 1 FROM _migrations WHERE name = ?", (name,)
                ).fetchone():
                    conn.commit()
                    applied.add(name)
                    continue
                fn(conn)
                conn.execute("INSERT INTO _migrations (name) VALUES (?)", (name,))
                conn.commit()
                applied.add(name)
            except Exception:
                conn.rollback()
                raise
            logger.info("Migration applied: %s", name)
    finally:
        conn.close()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


@register("20260719_remove_retired_features")
def remove_retired_features(conn: sqlite3.Connection) -> None:
    """Remove retired persistence while preserving active briefing history."""
    for index_name in (
        "idx_event_entities_event",
        "idx_event_entities_entity",
        "idx_entity_relations_src",
        "idx_entity_relations_tgt",
        "idx_entities_type",
        "idx_entities_name",
    ):
        conn.execute(f"DROP INDEX IF EXISTS {index_name}")

    for table_name in (
        "event_entities",
        "entity_relations",
        "entities",
        "digests",
        "topics",
    ):
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")

    if _table_exists(conn, "ai_usage"):
        conn.execute(
            """
            DELETE FROM ai_usage
            WHERE module = 'knowledge_graph'
               OR (module IN ('digest_briefing', 'briefing') AND task = 'digest')
            """
        )
        conn.execute(
            """
            UPDATE ai_usage
            SET module = 'briefing'
            WHERE module = 'digest_briefing'
              AND task IN ('briefing_quick', 'briefing_daily')
            """
        )
