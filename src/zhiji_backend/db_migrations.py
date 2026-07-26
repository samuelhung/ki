from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from . import db_schema

MigrationFn = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class MigrationSteps:
    migrate_events_cn: MigrationFn
    migrate_brainstorm: MigrationFn
    migrate_brainstorm_answers_to_messages: MigrationFn
    migrate_series: MigrationFn
    migrate_ingest_tasks_retry: MigrationFn
    migrate_video_md5: MigrationFn
    migrate_textbook: MigrationFn
    migrate_lessons_json: MigrationFn
    migrate_chain_reports: MigrationFn
    migrate_chain_meta: MigrationFn
    backfill_fts: MigrationFn
    logger: logging.Logger


_SCOPED_STEPS: ContextVar[MigrationSteps | None] = ContextVar(
    "zhiji_db_migration_steps", default=None
)


def _local_steps() -> MigrationSteps:
    return MigrationSteps(
        migrate_events_cn=_migrate_events_cn,
        migrate_brainstorm=_migrate_brainstorm,
        migrate_brainstorm_answers_to_messages=(
            _migrate_brainstorm_answers_to_messages
        ),
        migrate_series=_migrate_series,
        migrate_ingest_tasks_retry=_migrate_ingest_tasks_retry,
        migrate_video_md5=_migrate_video_md5,
        migrate_textbook=_migrate_textbook,
        migrate_lessons_json=_migrate_lessons_json,
        migrate_chain_reports=_migrate_chain_reports,
        migrate_chain_meta=_migrate_chain_meta,
        backfill_fts=_backfill_fts,
        logger=logging.getLogger("zhiji_backend.db"),
    )


def _current_steps() -> MigrationSteps:
    return _SCOPED_STEPS.get() or _local_steps()


@contextmanager
def migration_steps_scope(steps: MigrationSteps) -> Iterator[None]:
    token = _SCOPED_STEPS.set(steps)
    try:
        yield
    finally:
        _SCOPED_STEPS.reset(token)


def run_migrations(conn: sqlite3.Connection) -> None:
    steps = _current_steps()
    steps.migrate_events_cn(conn)
    steps.migrate_brainstorm(conn)
    steps.migrate_series(conn)
    steps.migrate_ingest_tasks_retry(conn)
    steps.migrate_video_md5(conn)
    db_schema.create_indexes(conn)
    steps.migrate_textbook(conn)
    steps.migrate_lessons_json(conn)
    steps.migrate_chain_reports(conn)
    steps.migrate_chain_meta(conn)
    steps.backfill_fts(conn)


def _migrate_events_cn(conn: sqlite3.Connection) -> None:
    """Add translation, ingest, discovery, and chain-analysis event columns."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
    for col in (
        "title_cn",
        "summary_cn",
        "translation_status",
        "translation_error",
        "last_error",
        "progress_stages",
        "video_path",
        "audio_path",
        "document_path",
        "content_type",
        "overview",
        "last_discovered_at",
        "suggested_series_json",
        "chain_analysis",
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} TEXT")


def _migrate_textbook(conn: sqlite3.Connection) -> None:
    """Add textbook column to study_materials if missing."""
    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(study_materials)").fetchall()
    }
    if "textbook" not in cols:
        conn.execute("ALTER TABLE study_materials ADD COLUMN textbook TEXT DEFAULT ''")


def _migrate_lessons_json(conn: sqlite3.Connection) -> None:
    """Add lessons_json column to study_materials if missing."""
    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(study_materials)").fetchall()
    }
    if "lessons_json" not in cols:
        conn.execute(
            "ALTER TABLE study_materials ADD COLUMN lessons_json TEXT DEFAULT '[]'"
        )


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
    """Create chain_meta table and add flow_summary to legacy tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chain_meta (
            chain_name      TEXT PRIMARY KEY,
            icon            TEXT NOT NULL DEFAULT '',
            flow_summary    TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    try:
        conn.execute(
            "ALTER TABLE chain_meta ADD COLUMN flow_summary TEXT NOT NULL DEFAULT ''"
        )
    except sqlite3.OperationalError:
        pass


def _backfill_fts(conn: sqlite3.Connection) -> None:
    """Sync all events into the FTS5 index, skipping already indexed rows."""
    indexed = {
        row[0] for row in conn.execute("SELECT event_id FROM events_fts").fetchall()
    }
    rows = conn.execute(
        "SELECT id, title, title_cn, raw_summary, summary_cn, ai_summary FROM events"
    ).fetchall()
    count = 0
    for row in rows:
        if row["id"] not in indexed:
            conn.execute(
                "INSERT INTO events_fts(event_id, title, title_cn, raw_summary, "
                "summary_cn, ai_summary) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    row["id"],
                    row["title"],
                    row["title_cn"],
                    row["raw_summary"],
                    row["summary_cn"],
                    row["ai_summary"],
                ),
            )
            count += 1
    if count:
        logging.getLogger("knowledge-intelligence").info(
            "FTS5 backfill: indexed %d events", count
        )


def _migrate_brainstorm(conn: sqlite3.Connection) -> None:
    """Migrate answered_event_ids JSON to links and add question columns."""
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(brainstorm_questions)").fetchall()
    }
    if "content_md" not in cols:
        conn.execute(
            "ALTER TABLE brainstorm_questions "
            "ADD COLUMN content_md TEXT NOT NULL DEFAULT ''"
        )
    if "topic" not in cols:
        conn.execute(
            "ALTER TABLE brainstorm_questions ADD COLUMN topic TEXT NOT NULL DEFAULT ''"
        )
    if "answer" not in cols:
        conn.execute(
            "ALTER TABLE brainstorm_questions ADD COLUMN answer TEXT NOT NULL DEFAULT ''"
        )
    if "summary_created_at" not in cols:
        conn.execute(
            "ALTER TABLE brainstorm_questions ADD COLUMN summary_created_at TEXT"
        )

    if "answered_event_ids" in cols:
        import json as _json

        rows = conn.execute(
            "SELECT id, answered_event_ids FROM brainstorm_questions"
        ).fetchall()
        for row in rows:
            try:
                ids = _json.loads(row["answered_event_ids"])
                for event_id in ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO brainstorm_event_links "
                        "(question_id, event_id) VALUES (?, ?)",
                        (row["id"], event_id),
                    )
            except (_json.JSONDecodeError, TypeError):
                pass

    _current_steps().migrate_brainstorm_answers_to_messages(conn)


def _migrate_brainstorm_answers_to_messages(conn: sqlite3.Connection) -> None:
    """Convert old Markdown answers into brainstorm conversation messages."""
    import json as _json
    import re as _re

    def strip_old_header(content: str) -> tuple[str, str | None]:
        match = _re.search(r"## 回答", content)
        if match:
            content = content[match.start() :]
        timestamp = None
        match = _re.match(r"## 回答 \(([^)]+)\)\s*\n+", content)
        if match:
            timestamp = match.group(1)
            content = content[match.end() :]
        return content.strip(), timestamp

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

    log = logging.getLogger("knowledge-intelligence")
    from .paths import BRAINSTORM_DIR as brainstorm_dir

    for row in pending:
        question_id = row["id"]
        md_path = brainstorm_dir / f"{question_id}.md"
        answer_content = ""
        if md_path.exists():
            try:
                raw = md_path.read_text(encoding="utf-8")
                answer_content, answer_ts = strip_old_header(raw)
            except Exception:
                pass
        if not answer_content:
            continue

        event_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            (question_id,),
        ).fetchall()
        refs = [event_row["event_id"] for event_row in event_rows]
        conn.execute(
            "INSERT INTO brainstorm_messages "
            "(question_id, role, content, refs_json) VALUES (?, 'user', ?, '[]')",
            (question_id, row["question"]),
        )

        timestamp_value = None
        import datetime as _dt

        if answer_ts:
            try:
                parsed = _dt.datetime.strptime(answer_ts, "%Y-%m-%d %H:%M")
                timestamp_value = parsed.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        if timestamp_value:
            conn.execute(
                "INSERT INTO brainstorm_messages "
                "(question_id, role, content, refs_json, created_at) "
                "VALUES (?, 'assistant', ?, ?, ?)",
                (
                    question_id,
                    answer_content,
                    _json.dumps(refs),
                    timestamp_value,
                ),
            )
        else:
            conn.execute(
                "INSERT INTO brainstorm_messages "
                "(question_id, role, content, refs_json) "
                "VALUES (?, 'assistant', ?, ?)",
                (question_id, answer_content, _json.dumps(refs)),
            )
        log.info("Migrated answer for question %s → 2 messages", question_id)


def _migrate_series(conn: sqlite3.Connection) -> None:
    """Add intro, updated_at, and summary columns to series if missing."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(series)").fetchall()}
    for col in ("intro", "updated_at", "summary"):
        if col not in cols:
            conn.execute(f"ALTER TABLE series ADD COLUMN {col} TEXT")


def _migrate_ingest_tasks_retry(conn: sqlite3.Connection) -> None:
    """Add retry_count column to ingest_tasks if missing."""
    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(ingest_tasks)").fetchall()
    }
    if "retry_count" not in cols:
        conn.execute(
            "ALTER TABLE ingest_tasks "
            "ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0"
        )
        _current_steps().logger.info(
            "Migration: added retry_count column to ingest_tasks"
        )


def _migrate_video_md5(conn: sqlite3.Connection) -> None:
    """Add video_md5 column to events if missing."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
    if "video_md5" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN video_md5 TEXT")
        _current_steps().logger.info("Migration: added video_md5 column to events")
