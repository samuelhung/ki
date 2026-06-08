from __future__ import annotations

import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "intelligence.sqlite"

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


def connect() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              type TEXT NOT NULL,
              url TEXT NOT NULL,
              topic TEXT,
              tags_json TEXT NOT NULL DEFAULT '[]',
              priority TEXT NOT NULL DEFAULT 'medium',
              enabled INTEGER NOT NULL DEFAULT 1,
              last_checked_at TEXT,
              last_error TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS events (
              id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL,
              title TEXT NOT NULL,
              url TEXT NOT NULL,
              published_at TEXT,
              raw_summary TEXT,
              ai_summary TEXT,
              title_cn TEXT,
              summary_cn TEXT,
              translation_status TEXT,
              translation_error TEXT,
              topic TEXT,
              tags_json TEXT NOT NULL DEFAULT '[]',
              importance INTEGER NOT NULL DEFAULT 0,
              actionability INTEGER NOT NULL DEFAULT 0,
              decision TEXT NOT NULL DEFAULT 'digest',
              status TEXT NOT NULL DEFAULT 'new',
              last_error TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(source_id) REFERENCES sources(id)
            );

            CREATE TABLE IF NOT EXISTS digests (
              date TEXT PRIMARY KEY,
              markdown TEXT NOT NULL,
              events_used INTEGER NOT NULL DEFAULT 0,
              action_candidates_created INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS topics (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              event_count INTEGER NOT NULL DEFAULT 0,
              last_event_at TEXT,
              summary TEXT,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS briefings (
              id TEXT PRIMARY KEY,
              type TEXT NOT NULL DEFAULT 'quick',
              topics_json TEXT NOT NULL DEFAULT '[]',
              events_used INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS brainstorm_questions (
              id TEXT PRIMARY KEY,
              event_id TEXT,
              question TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'open',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(event_id) REFERENCES events(id)
            );

            CREATE TABLE IF NOT EXISTS brainstorm_event_links (
              question_id TEXT NOT NULL,
              event_id TEXT NOT NULL,
              PRIMARY KEY (question_id, event_id),
              FOREIGN KEY (question_id) REFERENCES brainstorm_questions(id),
              FOREIGN KEY (event_id) REFERENCES events(id)
            );

            CREATE TABLE IF NOT EXISTS brainstorm_contemplate_cache (
              question_id TEXT NOT NULL,
              event_id TEXT NOT NULL,
              relevance TEXT NOT NULL,
              reason TEXT,
              judged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (question_id, event_id)
            );

            -- FTS5 full-text search (standalone table, trigram tokenizer for Chinese + English)
            CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
              event_id UNINDEXED,
              title, title_cn, raw_summary, summary_cn, ai_summary,
              tokenize='trigram'
            );

            -- Persistent ingest task queue (replaces BackgroundTasks)
            CREATE TABLE IF NOT EXISTS ingest_tasks (
              id TEXT PRIMARY KEY,
              event_id TEXT NOT NULL,
              ingest_type TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              error TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              started_at TEXT,
              finished_at TEXT
            );

            -- Sync triggers: keep events_fts in sync with events table
            CREATE TRIGGER IF NOT EXISTS trg_events_fts_insert AFTER INSERT ON events BEGIN
              INSERT INTO events_fts(event_id, title, title_cn, raw_summary, summary_cn, ai_summary)
              VALUES (NEW.id, NEW.title, NEW.title_cn, NEW.raw_summary, NEW.summary_cn, NEW.ai_summary);
            END;

            CREATE TRIGGER IF NOT EXISTS trg_events_fts_delete AFTER DELETE ON events BEGIN
              DELETE FROM events_fts WHERE event_id = OLD.id;
            END;

            CREATE TRIGGER IF NOT EXISTS trg_events_fts_update AFTER UPDATE ON events BEGIN
              DELETE FROM events_fts WHERE event_id = OLD.id;
              INSERT INTO events_fts(event_id, title, title_cn, raw_summary, summary_cn, ai_summary)
              VALUES (NEW.id, NEW.title, NEW.title_cn, NEW.raw_summary, NEW.summary_cn, NEW.ai_summary);
            END;
            """
        )
        # Migration: add Chinese translation columns if they don't exist yet
        _migrate_events_cn(conn)
        # Migration: add answered_event_ids
        _migrate_brainstorm(conn)
        # Performance indexes
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
            CREATE INDEX IF NOT EXISTS idx_events_source_id ON events(source_id);
            CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
            CREATE INDEX IF NOT EXISTS idx_events_translation_status ON events(translation_status);
            CREATE INDEX IF NOT EXISTS idx_briefings_type ON briefings(type);
            CREATE INDEX IF NOT EXISTS idx_brainstorm_event_id ON brainstorm_questions(event_id);
            CREATE INDEX IF NOT EXISTS idx_brainstorm_status ON brainstorm_questions(status);
            CREATE INDEX IF NOT EXISTS idx_brainstorm_links_question ON brainstorm_event_links(question_id);
            CREATE INDEX IF NOT EXISTS idx_brainstorm_links_event ON brainstorm_event_links(event_id);
        """)
        # Backfill FTS5 index: sync any events not yet in the index
        _backfill_fts(conn)


def _migrate_events_cn(conn: sqlite3.Connection) -> None:
    """Add title_cn, summary_cn, translation_status, translation_error, and last_error columns if missing."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
    for col in ("title_cn", "summary_cn", "translation_status", "translation_error", "last_error", "progress_stages", "video_path", "audio_path", "document_path"):
        if col not in cols:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} TEXT")


def _backfill_fts(conn: sqlite3.Connection) -> None:
    """Sync all events into the FTS5 index (idempotent — skips already indexed)."""
    indexed = {row[0] for row in conn.execute("SELECT event_id FROM events_fts").fetchall()}
    rows = conn.execute(
        "SELECT id, title, title_cn, raw_summary, summary_cn, ai_summary FROM events"
    ).fetchall()
    count = 0
    for row in rows:
        if row["id"] not in indexed:
            conn.execute(
                "INSERT INTO events_fts(event_id, title, title_cn, raw_summary, summary_cn, ai_summary) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (row["id"], row["title"], row["title_cn"], row["raw_summary"], row["summary_cn"], row["ai_summary"]),
            )
            count += 1
    if count:
        import logging
        logging.getLogger("knowledge-intelligence").info("FTS5 backfill: indexed %d events", count)


def _migrate_brainstorm(conn: sqlite3.Connection) -> None:
    """Migrate answered_event_ids JSON → brainstorm_event_links table, add content_md."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(brainstorm_questions)").fetchall()}
    if "content_md" not in cols:
        conn.execute("ALTER TABLE brainstorm_questions ADD COLUMN content_md TEXT NOT NULL DEFAULT ''")

    # Migrate JSON answered_event_ids → relational table
    if "answered_event_ids" in cols:
        import json as _json
        rows = conn.execute("SELECT id, answered_event_ids FROM brainstorm_questions").fetchall()
        for row in rows:
            try:
                ids = _json.loads(row["answered_event_ids"])
                for eid in ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
                        (row["id"], eid),
                    )
            except (_json.JSONDecodeError, TypeError):
                pass


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
