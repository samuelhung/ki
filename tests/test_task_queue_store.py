"""Contracts for queue persistence extracted from :mod:`task_queue`."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend import task_queue_store
from zhiji_backend.db import connect, init_db


def _insert_task(event_id: str, task_id: str) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO sources (id, name, type, url, topic, priority)
               VALUES ('user-upload', 'Upload', 'manual', '', 'test', 'medium')"""
        )
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic, importance,
                       actionability, decision, status, content_type)
               VALUES (?, 'user-upload', 'Task', '', 'test', 4, 4, 'digest',
                       'processing', 'event')""",
            (event_id,),
        )
        conn.execute(
            """INSERT INTO ingest_tasks
                       (id, event_id, ingest_type, payload_json, status)
               VALUES (?, ?, 'document', '{}', 'pending')""",
            (task_id, event_id),
        )


def test_claim_pending_selects_oldest_and_transitions_atomically(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    _insert_task("event-first", "task-first")
    _insert_task("event-second", "task-second")

    assert task_queue_store.claim_pending(connect) == "task-first"

    with connect() as conn:
        rows = conn.execute(
            "SELECT id, status, started_at FROM ingest_tasks ORDER BY created_at, id"
        ).fetchall()
    assert [(row["id"], row["status"]) for row in rows] == [
        ("task-first", "running"),
        ("task-second", "pending"),
    ]
    assert rows[0]["started_at"] is not None
    assert rows[1]["started_at"] is None


def test_shutdown_restore_is_exactly_once_and_preserves_retry_count(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    _insert_task("event-restore", "task-restore")
    with connect() as conn:
        conn.execute(
            "UPDATE ingest_tasks SET status = 'running', retry_count = 1, "
            "started_at = datetime('now'), finished_at = datetime('now'), error = 'old'"
        )
        conn.execute("UPDATE events SET last_error = 'old' WHERE id = 'event-restore'")

    assert task_queue_store.restore_shutdown_interrupted_task("task-restore", connect)
    assert not task_queue_store.restore_shutdown_interrupted_task(
        "task-restore", connect
    )

    with connect() as conn:
        task = conn.execute(
            "SELECT status, started_at, finished_at, error, retry_count "
            "FROM ingest_tasks WHERE id = 'task-restore'"
        ).fetchone()
        event = conn.execute(
            "SELECT status, last_error FROM events WHERE id = 'event-restore'"
        ).fetchone()
    assert tuple(task) == ("pending", None, None, None, 1)
    assert tuple(event) == ("pending", None)
