from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

from .paths import DEFAULT_DB_PATH, ZHIJI_HOME  # noqa: E402 — 统一路径来源

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


def _open_connection() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = _open_connection()
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
              content_type TEXT NOT NULL DEFAULT 'event',
              overview TEXT,
              video_path TEXT,
              audio_path TEXT,
              document_path TEXT,
              progress_stages TEXT,
              last_discovered_at TEXT,
              suggested_series_json TEXT,
              last_error TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(source_id) REFERENCES sources(id)
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
              summary_created_at TEXT,
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

            CREATE TABLE IF NOT EXISTS brainstorm_messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              question_id TEXT NOT NULL,
              role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
              content TEXT NOT NULL DEFAULT '',
              refs_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              FOREIGN KEY (question_id) REFERENCES brainstorm_questions(id)
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
              retry_count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              started_at TEXT,
              finished_at TEXT
            );

            -- Unified task management — manual tasks + KI-linked action items
            CREATE TABLE IF NOT EXISTS tasks (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              source TEXT NOT NULL DEFAULT 'manual',
              source_id TEXT,
              source_label TEXT,
              priority TEXT NOT NULL DEFAULT 'medium',
              due_date TEXT,
              status TEXT NOT NULL DEFAULT 'todo',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- Thematic series — AI-discovered clusters of related content
            CREATE TABLE IF NOT EXISTS series (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              description TEXT,
              member_ids TEXT NOT NULL DEFAULT '[]',
              sort_order TEXT DEFAULT '[]',
              status TEXT NOT NULL DEFAULT 'draft',
              intro TEXT,
              summary TEXT,
              paper TEXT,
              updated_at TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- AI usage tracking: per-call token counts and cost estimates
            CREATE TABLE IF NOT EXISTS ai_usage (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              module TEXT DEFAULT '',
              task TEXT DEFAULT '',
              model TEXT DEFAULT '',
              status TEXT NOT NULL DEFAULT 'success',
              prompt_tokens INTEGER NOT NULL DEFAULT 0,
              completion_tokens INTEGER NOT NULL DEFAULT 0,
              total_tokens INTEGER NOT NULL DEFAULT 0,
              cached_tokens INTEGER NOT NULL DEFAULT 0,
              reasoning_tokens INTEGER NOT NULL DEFAULT 0,
              cost_rmb REAL NOT NULL DEFAULT 0,
              duration_ms INTEGER NOT NULL DEFAULT 0,
              error TEXT DEFAULT ''
            );

            -- Series scan cache: persists expand-scan results so re-opening skips AI call
            CREATE TABLE IF NOT EXISTS series_scan_cache (
              series_id TEXT PRIMARY KEY,
              scanned_count INTEGER NOT NULL,
              recommendations_json TEXT NOT NULL DEFAULT '[]',
              scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- 辅导中心 — 学习资料（独立模块，与 events 无关）
            CREATE TABLE IF NOT EXISTS study_materials (
              id              TEXT PRIMARY KEY,
              subject         TEXT NOT NULL DEFAULT '',
              grade           TEXT DEFAULT '',
              textbook        TEXT DEFAULT '',
              study_type      TEXT NOT NULL DEFAULT '',
              title           TEXT NOT NULL DEFAULT '',
              source_type     TEXT DEFAULT 'manual',
              raw_content     TEXT DEFAULT '',
              child_version   TEXT DEFAULT '',
              parent_version  TEXT DEFAULT '',
              formats_json    TEXT DEFAULT '{}',
              status          TEXT DEFAULT 'draft',
              score           INTEGER,
              is_correct      INTEGER,
              mistake_tags    TEXT DEFAULT '[]',
              tags_json       TEXT DEFAULT '[]',
              lessons_json    TEXT DEFAULT '[]',
              created_at      TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );\n\n            CREATE TABLE IF NOT EXISTS industry_chain_nodes (\n              id              TEXT PRIMARY KEY,\n              chain           TEXT NOT NULL DEFAULT '',\n              name            TEXT NOT NULL DEFAULT '',\n              node_type       TEXT NOT NULL DEFAULT '',\n              description     TEXT DEFAULT '',\n              parent_id       TEXT DEFAULT '',\n              global_shares   TEXT DEFAULT '[]',\n              substitutes     TEXT DEFAULT '[]',\n              upstream_ids    TEXT DEFAULT '[]',\n              data_sources    TEXT DEFAULT '{}',\n              last_updated    TEXT DEFAULT '',\n              sort_order      INTEGER DEFAULT 0,\n              created_at      TEXT NOT NULL DEFAULT (datetime('now'))\n            );\n\n            -- 产业链数据更新提示 — 采集内容中检测到的潜在数据更新\n            CREATE TABLE IF NOT EXISTS chain_data_hints (\n              id              TEXT PRIMARY KEY,\n              event_id        TEXT NOT NULL,\n              node_id         TEXT NOT NULL,\n              chain           TEXT NOT NULL DEFAULT '',\n              field           TEXT NOT NULL DEFAULT '',\n              current_value   TEXT DEFAULT '',\n              suggested_value TEXT NOT NULL DEFAULT '',\n              source_quote    TEXT DEFAULT '',\n              confidence      REAL NOT NULL DEFAULT 0.5,\n              status          TEXT NOT NULL DEFAULT 'pending',\n              resolved_value  TEXT DEFAULT '',\n              created_at      TEXT NOT NULL DEFAULT (datetime('now')),\n              reviewed_at     TEXT,\n              FOREIGN KEY (event_id) REFERENCES events(id),\n              FOREIGN KEY (node_id) REFERENCES industry_chain_nodes(id)\n            );\n\n            -- 新产业链建议 — AI 从采集内容中发现的新链条（尚未收录）\n            CREATE TABLE IF NOT EXISTS chain_suggestions (\n              id              TEXT PRIMARY KEY,\n              chain_name      TEXT NOT NULL DEFAULT '',\n              event_id        TEXT NOT NULL,\n              nodes_json      TEXT NOT NULL DEFAULT '[]',\n              reason          TEXT DEFAULT '',\n              source_quote    TEXT DEFAULT '',\n              confidence      REAL NOT NULL DEFAULT 0.5,\n              status          TEXT NOT NULL DEFAULT 'pending',\n              created_at      TEXT NOT NULL DEFAULT (datetime('now')),\n              reviewed_at     TEXT,\n              FOREIGN KEY (event_id) REFERENCES events(id)\n            );\n\n            -- Sync triggers: keep events_fts in sync with events table
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
        # Migration: add intro / updated_at to series
        _migrate_series(conn)
        # Migration: add retry_count to ingest_tasks
        _migrate_ingest_tasks_retry(conn)
        _migrate_video_md5(conn)
        # Performance indexes
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
            CREATE INDEX IF NOT EXISTS idx_events_source_id ON events(source_id);
            CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
            CREATE INDEX IF NOT EXISTS idx_events_topic ON events(topic);
            CREATE INDEX IF NOT EXISTS idx_events_translation_status ON events(translation_status);
            CREATE INDEX IF NOT EXISTS idx_ingest_tasks_created_at ON ingest_tasks(created_at);
            CREATE INDEX IF NOT EXISTS idx_briefings_type ON briefings(type);
            CREATE INDEX IF NOT EXISTS idx_brainstorm_event_id ON brainstorm_questions(event_id);
            CREATE INDEX IF NOT EXISTS idx_brainstorm_status ON brainstorm_questions(status);
            CREATE INDEX IF NOT EXISTS idx_brainstorm_links_question ON brainstorm_event_links(question_id);
            CREATE INDEX IF NOT EXISTS idx_brainstorm_links_event ON brainstorm_event_links(event_id);
            CREATE INDEX IF NOT EXISTS idx_brainstorm_messages_question ON brainstorm_messages(question_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
            CREATE INDEX IF NOT EXISTS idx_tasks_source ON tasks(source);
            CREATE INDEX IF NOT EXISTS idx_study_subject ON study_materials(subject);
            CREATE INDEX IF NOT EXISTS idx_study_type ON study_materials(study_type);
            CREATE INDEX IF NOT EXISTS idx_study_status ON study_materials(status);
            CREATE INDEX IF NOT EXISTS idx_study_created ON study_materials(created_at);
        """)
        # Migration: add textbook column for existing installs
        _migrate_textbook(conn)
        # Migration: add lessons_json column for textbook lesson analysis
        _migrate_lessons_json(conn)
        # Migration: add chain_reports table
        _migrate_chain_reports(conn)
        # Migration: add chain_meta table
        _migrate_chain_meta(conn)
        # Backfill FTS5 index: sync any events not yet in the index
        _backfill_fts(conn)


def _migrate_events_cn(conn: sqlite3.Connection) -> None:
    """Add title_cn, summary_cn, translation_status, translation_error, and last_error columns if missing."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
    for col in ("title_cn", "summary_cn", "translation_status", "translation_error", "last_error", "progress_stages", "video_path", "audio_path", "document_path", "content_type", "overview", "last_discovered_at", "suggested_series_json", "chain_analysis"):
        if col not in cols:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} TEXT")


def _migrate_textbook(conn: sqlite3.Connection) -> None:
    """Add textbook column to study_materials if missing."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(study_materials)").fetchall()}
    if "textbook" not in cols:
        conn.execute("ALTER TABLE study_materials ADD COLUMN textbook TEXT DEFAULT ''")


def _migrate_lessons_json(conn: sqlite3.Connection) -> None:
    """Add lessons_json column to study_materials if missing."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(study_materials)").fetchall()}
    if "lessons_json" not in cols:
        conn.execute("ALTER TABLE study_materials ADD COLUMN lessons_json TEXT DEFAULT '[]'")


def _migrate_chain_reports(conn: sqlite3.Connection) -> None:
    """Create chain_reports table if not exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chain_reports (
            chain_name      TEXT PRIMARY KEY,
            report          TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)


def _migrate_chain_meta(conn: sqlite3.Connection) -> None:
    """Create chain_meta table — stores per-chain metadata like icon and flow summary."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chain_meta (
            chain_name      TEXT PRIMARY KEY,
            icon            TEXT NOT NULL DEFAULT '',
            flow_summary    TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # Migration: add flow_summary column to existing chain_meta tables
    try:
        conn.execute("ALTER TABLE chain_meta ADD COLUMN flow_summary TEXT NOT NULL DEFAULT ''")
    except:
        pass  # column already exists


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
    if "topic" not in cols:
        conn.execute("ALTER TABLE brainstorm_questions ADD COLUMN topic TEXT NOT NULL DEFAULT ''")
    if "answer" not in cols:
        conn.execute("ALTER TABLE brainstorm_questions ADD COLUMN answer TEXT NOT NULL DEFAULT ''")
    if "summary_created_at" not in cols:
        conn.execute("ALTER TABLE brainstorm_questions ADD COLUMN summary_created_at TEXT")

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

    # Migrate old .md answers → brainstorm_messages (single-shot → conversation thread)
    _migrate_brainstorm_answers_to_messages(conn)


def _migrate_brainstorm_answers_to_messages(conn: sqlite3.Connection) -> None:
    """Convert old single-shot answers from .md files into brainstorm_messages rows,
    so they appear as first-round conversations in the new dialog UI."""
    import os as _os
    from pathlib import Path as _Path
    import json as _json
    import re as _re

    def strip_old_header(content: str) -> tuple[str, str | None]:
        """Strip '# 问题 ... 创建时间 ... ---' preamble and '## 回答 (ts)' heading.
        Returns (cleaned_content, timestamp_str_or_None)."""
        # Step 1: strip everything before '## 回答'
        m = _re.search(r'## 回答', content)
        if m:
            content = content[m.start():]
        # Step 2: strip '## 回答 (2026-06-08 17:00)\n\n' heading, extract ts
        ts = None
        m = _re.match(r'## 回答 \(([^)]+)\)\s*\n+', content)
        if m:
            ts = m.group(1)
            content = content[m.end():]
        return content.strip(), ts

    # Find questions that have linked events but NO messages yet
    pending = conn.execute("""
        SELECT bq.id, bq.question
        FROM brainstorm_questions bq
        INNER JOIN brainstorm_event_links bel ON bel.question_id = bq.id
        WHERE NOT EXISTS (
            SELECT 1 FROM brainstorm_messages bm WHERE bm.question_id = bq.id
        )
        GROUP BY bq.id
    """).fetchall()

    if not pending:
        return

    import logging
    log = logging.getLogger("knowledge-intelligence")
    from .paths import BRAINSTORM_DIR as _bd
    brainstorm_dir = _bd

    for row in pending:
        qid = row["id"]
        question_text = row["question"]

        # Read answer from .md file, strip header
        md_path = brainstorm_dir / f"{qid}.md"
        answer_content = ""
        if md_path.exists():
            try:
                raw = md_path.read_text(encoding="utf-8")
                answer_content, answer_ts = strip_old_header(raw)
            except Exception:
                pass

        if not answer_content:
            continue

        # Get linked event IDs as refs
        evt_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?", (qid,)
        ).fetchall()
        refs = [r["event_id"] for r in evt_rows]

        # Insert user message (the original question)
        conn.execute(
            "INSERT INTO brainstorm_messages (question_id, role, content, refs_json) VALUES (?, 'user', ?, '[]')",
            (qid, question_text),
        )
        # Insert assistant message (the old answer), use extracted timestamp if available
        import datetime as _dt
        if answer_ts:
            try:
                parsed = _dt.datetime.strptime(answer_ts, '%Y-%m-%d %H:%M')
                ts_val = parsed.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                ts_val = None
        else:
            ts_val = None

        if ts_val:
            conn.execute(
                "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'assistant', ?, ?, ?)",
                (qid, answer_content, _json.dumps(refs), ts_val),
            )
        else:
            conn.execute(
                "INSERT INTO brainstorm_messages (question_id, role, content, refs_json) VALUES (?, 'assistant', ?, ?)",
                (qid, answer_content, _json.dumps(refs)),
            )
        log.info("Migrated answer for question %s → 2 messages", qid)


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


def _migrate_series(conn: sqlite3.Connection) -> None:
    """Add intro and updated_at columns to series table if missing."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(series)").fetchall()}
    for col in ("intro", "updated_at", "summary"):
        if col not in cols:
            conn.execute(f"ALTER TABLE series ADD COLUMN {col} TEXT")


def _migrate_ingest_tasks_retry(conn: sqlite3.Connection) -> None:
    """Add retry_count column to ingest_tasks if missing."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(ingest_tasks)").fetchall()}
    if "retry_count" not in cols:
        conn.execute("ALTER TABLE ingest_tasks ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")
        logger.info("Migration: added retry_count column to ingest_tasks")


def _migrate_video_md5(conn: sqlite3.Connection) -> None:
    """Add video_md5 column to events if missing."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
    if "video_md5" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN video_md5 TEXT")
        logger.info("Migration: added video_md5 column to events")
