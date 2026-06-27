"""Tests for ingest task queue timeout isolation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend import task_queue
from zhiji_backend.db import connect, init_db


class _TimeoutProcess:
    returncode = None
    terminated = False
    killed = False

    def communicate(self, timeout=None):
        if not self.terminated:
            raise task_queue.subprocess.TimeoutExpired(cmd=["runner"], timeout=timeout or 0)
        self.returncode = -15
        return "", ""

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.returncode = -9


class _FailingProcess:
    returncode = 1

    def communicate(self, timeout=None):
        return "", "runner failed"


def _insert_processing_task(event_id: str = "evt-timeout", task_id: str = "task-timeout") -> str:
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO sources (id, name, type, url, topic, priority)
               VALUES ('user-upload', '用户上传', 'manual', '', 'test', 'medium')"""
        )
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic,
               importance, actionability, decision, status, content_type)
               VALUES (?, 'user-upload', '超时任务', '', 'test', 4, 4, 'digest', 'processing', 'event')""",
            (event_id,),
        )
        conn.execute(
            """INSERT INTO ingest_tasks (id, event_id, ingest_type, payload_json, status)
               VALUES (?, ?, 'document', '{"content_text":"body","topic":"test","title":"超时任务"}', 'pending')""",
            (task_id, event_id),
        )
    return task_id


def test_timeout_marks_task_error_and_event_error_after_retry_exhausted(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task()
    with connect() as conn:
        conn.execute("UPDATE ingest_tasks SET retry_count = 1 WHERE id = ?", (task_id,))

    monkeypatch.setattr(task_queue, "_TASK_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: _TimeoutProcess())

    task_queue._process_one(task_id)

    with connect() as conn:
        task = conn.execute("SELECT status, error FROM ingest_tasks WHERE id = ?", (task_id,)).fetchone()
        event = conn.execute("SELECT status, last_error FROM events WHERE id = 'evt-timeout'").fetchone()

    assert task["status"] == "error"
    assert "任务超时" in task["error"]
    assert event["status"] == "error"
    assert event["last_error"] == task["error"]


def test_timeout_retry_resets_task_and_event_to_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(event_id="evt-retry", task_id="task-retry")

    monkeypatch.setattr(task_queue, "_TASK_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: _TimeoutProcess())

    task_queue._process_one(task_id)

    with connect() as conn:
        task = conn.execute("SELECT status, error, retry_count FROM ingest_tasks WHERE id = ?", (task_id,)).fetchone()
        event = conn.execute("SELECT status, last_error FROM events WHERE id = 'evt-retry'").fetchone()

    assert task["status"] == "pending"
    assert task["error"] is None
    assert task["retry_count"] == 1
    assert event["status"] == "pending"
    assert event["last_error"] is None


def test_child_process_failure_marks_processing_event_error(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(event_id="evt-failed", task_id="task-failed")

    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: _FailingProcess())

    task_queue._process_one(task_id)

    with connect() as conn:
        task = conn.execute("SELECT status, error FROM ingest_tasks WHERE id = ?", (task_id,)).fetchone()
        event = conn.execute("SELECT status, last_error FROM events WHERE id = 'evt-failed'").fetchone()

    assert task["status"] == "error"
    assert task["error"] == "runner failed"
    assert event["status"] == "error"
    assert event["last_error"] == task["error"]


def test_safe_pending_unlink_refuses_paths_outside_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(task_queue, "PENDING_DIR", tmp_path / "pending")
    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")

    task_queue._safe_pending_unlink(str(outside))

    assert outside.exists()


def test_start_worker_does_not_start_duplicate_thread(monkeypatch):
    class _AliveWorker:
        def is_alive(self):
            return True

    monkeypatch.setattr(task_queue, "_worker", _AliveWorker())
    called = False

    def _recover_stuck():
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(task_queue, "recover_stuck", _recover_stuck)

    task_queue.start_worker()

    assert called is False
