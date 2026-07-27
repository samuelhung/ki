"""Contracts for queue persistence extracted from :mod:`task_queue`."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend import task_queue, task_queue_store
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


def test_enqueue_failure_uses_facade_cleanup_and_compensation_seams(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(task_queue, "PENDING_DIR", tmp_path / "pending")
    monkeypatch.setattr(task_queue, "init_db", lambda: None)
    monkeypatch.setattr(task_queue, "connect", lambda: (_ for _ in ()).throw(OSError()))
    cleaned = []
    compensated = []
    monkeypatch.setattr(task_queue, "_safe_pending_unlink", cleaned.append)
    monkeypatch.setattr(
        task_queue,
        "_compensate_failed_enqueue",
        lambda event_id, task_id: compensated.append((event_id, task_id)),
    )

    with pytest.raises(task_queue.EnqueueError):
        task_queue.enqueue("event-failure", "video_file", source, "test", "Title")

    assert cleaned == [str(tmp_path / "pending/event-failure.mp4")]
    assert compensated[0][0] == "event-failure"
    assert compensated[0][1].startswith("task-")


def test_enqueue_resolves_uuid_path_and_shutil_from_facade_at_call_time(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    _insert_task("existing-event", "existing-task")
    source_type = type(tmp_path)
    source = source_type(tmp_path / "source.pdf")
    source.write_bytes(b"document")
    copies = []
    monkeypatch.setattr(task_queue, "PENDING_DIR", tmp_path / "pending")
    monkeypatch.setattr(task_queue, "Path", source_type)
    monkeypatch.setattr(
        task_queue,
        "uuid",
        types.SimpleNamespace(uuid4=lambda: types.SimpleNamespace(hex="abcdef1234567")),
    )
    monkeypatch.setattr(
        task_queue,
        "shutil",
        types.SimpleNamespace(copy2=lambda source, dest: copies.append((source, dest))),
    )

    task_id = task_queue.enqueue("existing-event", "document", source, "test", "Title")

    assert task_id == "task-abcdef123456"
    assert copies == [(source, tmp_path / "pending/existing-event.pdf")]


def test_safe_pending_unlink_resolves_path_and_unlink_from_facade(
    tmp_path, monkeypatch
):
    calls = []

    def path_factory(value):
        calls.append(("path", value))
        return Path(value)

    def unlink(pending_dir, candidate):
        calls.append(("unlink", pending_dir, candidate))

    monkeypatch.setattr(task_queue, "PENDING_DIR", tmp_path / "pending")
    monkeypatch.setattr(task_queue, "Path", path_factory)
    monkeypatch.setattr(task_queue, "safe_unlink_under", unlink)

    task_queue._safe_pending_unlink("queued.pdf")

    assert calls == [
        ("path", "queued.pdf"),
        ("unlink", tmp_path / "pending", Path("queued.pdf")),
    ]


def test_recover_stuck_resolves_sqlite_and_time_from_facade(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    attempts = []
    waits = []
    monkeypatch.setattr(
        task_queue,
        "sqlite3",
        types.SimpleNamespace(
            connect=lambda path: (
                attempts.append(path) or (_ for _ in ()).throw(OSError("locked"))
            )
        ),
    )
    monkeypatch.setattr(task_queue, "time", types.SimpleNamespace(sleep=waits.append))

    assert task_queue.recover_stuck() == 0
    assert len(attempts) == 3
    assert waits == [2, 4, 8]


def test_enqueue_resolves_json_dumps_from_facade_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    _insert_task("event-json", "existing-json-task")
    calls = []

    def dumps(payload, *, ensure_ascii):
        calls.append((payload, ensure_ascii))
        return '{"facade":"json"}'

    monkeypatch.setattr(task_queue, "json", types.SimpleNamespace(dumps=dumps))

    task_id = task_queue.enqueue("event-json", "document", "body", "test", "Title")

    with connect() as conn:
        row = conn.execute(
            "SELECT payload_json FROM ingest_tasks WHERE id = ?", (task_id,)
        ).fetchone()
    assert calls == [
        ({"content_text": "body", "topic": "test", "title": "Title"}, False)
    ]
    assert row["payload_json"] == '{"facade":"json"}'
