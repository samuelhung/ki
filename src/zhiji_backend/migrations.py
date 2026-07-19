"""Simple SQLite migration manager — no external deps.

Usage:
    from .migrations import ensure_migrations
    ensure_migrations(db_path)  # run before init_db()
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

MigrationFn = Callable[[sqlite3.Connection], None]
_registry: list[tuple[str, MigrationFn]] = []


def register(name: str) -> Callable[[MigrationFn], MigrationFn]:
    """Decorator to register a migration by name."""

    def decorator(fn: MigrationFn) -> MigrationFn:
        _registry.append((name, fn))
        return fn

    return decorator


def ensure_migrations(db_path: Path) -> None:
    """Apply any pending migrations to the database."""
    conn = sqlite3.connect(str(db_path))
    try:
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
            try:
                conn.execute("BEGIN IMMEDIATE")
                fn(conn)
                conn.execute("INSERT INTO _migrations (name) VALUES (?)", (name,))
                conn.commit()
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
