from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from . import db_migrations, db_schema
from .paths import DEFAULT_DB_PATH

DEFAULT_SOURCES = [
    {
        "id": "bbc-world",
        "name": "BBC World",
        "type": "rss",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "topic": "world",
        "priority": "high",
    },
    {
        "id": "bbc-top-stories",
        "name": "BBC Top Stories",
        "type": "rss",
        "url": "https://feeds.bbci.co.uk/news/rss.xml",
        "topic": "world",
        "priority": "medium",
    },
    {
        "id": "bbc-business",
        "name": "BBC Business",
        "type": "rss",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "topic": "business",
        "priority": "medium",
    },
    {
        "id": "bbc-technology",
        "name": "BBC Technology",
        "type": "rss",
        "url": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "topic": "tech-ai",
        "priority": "high",
    },
    {
        "id": "reuters-world",
        "name": "The Guardian",
        "type": "rss",
        "url": "https://www.theguardian.com/world/rss",
        "topic": "world",
        "priority": "high",
    },
    {
        "id": "npr",
        "name": "NPR",
        "type": "rss",
        "url": "https://feeds.npr.org/1001/rss.xml",
        "topic": "world",
        "priority": "medium",
    },
    {
        "id": "al-jazeera",
        "name": "Al Jazeera",
        "type": "rss",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "topic": "world",
        "priority": "medium",
    },
    {
        "id": "nyt-world",
        "name": "NYT World",
        "type": "rss",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "topic": "world",
        "priority": "high",
    },
]


def get_db_path() -> Path:
    configured = os.getenv("KI_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_DB_PATH


def _open_connection(*, busy_timeout_ms: int = 5000) -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_timeout_ms = max(0, busy_timeout_ms)
    conn = sqlite3.connect(path, timeout=normalized_timeout_ms / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={normalized_timeout_ms}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def connect(*, busy_timeout_ms: int = 5000) -> Iterator[sqlite3.Connection]:
    conn = _open_connection(busy_timeout_ms=busy_timeout_ms)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        db_schema.create_schema(conn)
        db_migrations.run_migrations(conn)


def seed_default_sources() -> int:
    init_db()
    inserted = 0
    with connect() as conn:
        for source in DEFAULT_SOURCES:
            before = conn.total_changes
            conn.execute(
                """
                INSERT OR IGNORE INTO sources (id, name, type, url, topic, priority, enabled)
                VALUES (:id, :name, :type, :url, :topic, :priority, 1)
                """,
                source,
            )
            inserted += conn.total_changes - before
    return inserted
