"""Tests for ingest task queue timeout isolation."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

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


class _BlockingProcess:
    returncode = None

    def __init__(self, *, survive_terminate: bool = False):
        self.started = threading.Event()
        self.exited = threading.Event()
        self.terminated = False
        self.killed = False
        self.survive_terminate = survive_terminate

    def communicate(self, timeout=None):
        self.started.set()
        if not self.exited.wait(timeout=2):
            raise AssertionError("test process was not stopped")
        return "", ""

    def terminate(self):
        self.terminated = True
        if not self.survive_terminate:
            self.returncode = -15
            self.exited.set()

    def wait(self, timeout=None):
        if not self.exited.wait(timeout=0 if timeout is None else min(timeout, 0.05)):
            raise task_queue.subprocess.TimeoutExpired(cmd=["runner"], timeout=timeout or 0)
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.exited.set()


class _TerminateFailureProcess(_BlockingProcess):
    def terminate(self):
        self.terminated = True
        self.returncode = 1
        self.exited.set()
        raise OSError("terminate unavailable")

    def communicate(self, timeout=None):
        self.started.set()
        if not self.exited.wait(timeout=2):
            raise AssertionError("test process was not released")
        return "", "ordinary child failure"


@pytest.fixture(autouse=True)
def _reset_worker_state():
    task_queue._shutdown_flag.clear()
    task_queue._worker = None
    if hasattr(task_queue, "_active_process"):
        task_queue._active_process = None
    if hasattr(task_queue, "_active_task_id"):
        task_queue._active_task_id = None
    if hasattr(task_queue, "_shutdown_interrupted"):
        task_queue._shutdown_interrupted = None
    if hasattr(task_queue, "_shutdown_signal_succeeded"):
        task_queue._shutdown_signal_succeeded = False
    if hasattr(task_queue, "_shutdown_signal_resolved"):
        task_queue._shutdown_signal_resolved.clear()
    yield
    task_queue._shutdown_flag.set()
    worker = task_queue._worker
    if worker and worker.is_alive():
        worker.join(timeout=1)
    task_queue._worker = None


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
    assert task_queue._active_process is None
    assert task_queue._active_task_id is None


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
    assert task_queue._active_process is None
    assert task_queue._active_task_id is None


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


def test_stop_worker_terminates_active_child_and_restores_exact_task(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(event_id="evt-shutdown", task_id="task-shutdown")
    with connect() as conn:
        conn.execute(
            "UPDATE ingest_tasks SET retry_count = 1, error = 'old', finished_at = datetime('now') WHERE id = ?",
            (task_id,),
        )
        conn.execute("UPDATE events SET last_error = 'old' WHERE id = 'evt-shutdown'")

    process = _BlockingProcess()
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: process)

    worker = threading.Thread(target=task_queue._process_one, args=(task_id,))
    task_queue._worker = worker
    worker.start()
    assert process.started.wait(timeout=1)

    assert task_queue.stop_worker() is True

    with connect() as conn:
        task = conn.execute(
            "SELECT status, started_at, finished_at, error, retry_count FROM ingest_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        event = conn.execute(
            "SELECT status, last_error FROM events WHERE id = 'evt-shutdown'"
        ).fetchone()

    assert process.terminated is True
    assert process.killed is False
    assert worker.is_alive() is False
    assert tuple(task) == ("pending", None, None, None, 1)
    assert tuple(event) == ("pending", None)
    assert task_queue._active_process is None
    assert task_queue._active_task_id is None


def test_stop_worker_kills_child_that_ignores_terminate(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(event_id="evt-kill", task_id="task-kill")
    process = _BlockingProcess(survive_terminate=True)
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: process)

    worker = threading.Thread(target=task_queue._process_one, args=(task_id,))
    task_queue._worker = worker
    worker.start()
    assert process.started.wait(timeout=1)

    assert task_queue.stop_worker() is True

    assert process.terminated is True
    assert process.killed is True
    with connect() as conn:
        task = conn.execute(
            "SELECT status, retry_count FROM ingest_tasks WHERE id = ?", (task_id,)
        ).fetchone()
    assert tuple(task) == ("pending", 0)


def test_failed_terminate_does_not_reclassify_ordinary_child_failure(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(
        event_id="evt-terminate-failed", task_id="task-terminate-failed"
    )
    process = _TerminateFailureProcess()
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: process)

    worker = threading.Thread(target=task_queue._process_one, args=(task_id,))
    task_queue._worker = worker
    worker.start()
    assert process.started.wait(timeout=1)

    assert task_queue.stop_worker() is True

    with connect() as conn:
        task = conn.execute(
            "SELECT status, error FROM ingest_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        event = conn.execute(
            "SELECT status, last_error FROM events WHERE id = 'evt-terminate-failed'"
        ).fetchone()
    assert tuple(task) == ("error", "ordinary child failure")
    assert tuple(event) == ("error", "ordinary child failure")


def test_shutdown_before_spawn_restores_claimed_task_without_starting_child(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(event_id="evt-race", task_id="task-race")
    spawned = False

    def spawn(*args, **kwargs):
        nonlocal spawned
        spawned = True
        return _FailingProcess()

    monkeypatch.setattr(task_queue.subprocess, "Popen", spawn)
    task_queue._shutdown_flag.set()

    task_queue._process_one(task_id)

    assert spawned is False
    with connect() as conn:
        task = conn.execute(
            "SELECT status, started_at, finished_at, error FROM ingest_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        event = conn.execute(
            "SELECT status, last_error FROM events WHERE id = 'evt-race'"
        ).fetchone()
    assert tuple(task) == ("pending", None, None, None)
    assert tuple(event) == ("pending", None)


def test_process_reference_is_cleared_after_ordinary_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(event_id="evt-clear", task_id="task-clear")
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: _FailingProcess())

    task_queue._process_one(task_id)

    assert task_queue._active_process is None
    assert task_queue._active_task_id is None


def test_stop_worker_without_active_child_is_idempotent():
    assert task_queue.stop_worker() is True
    assert task_queue.stop_worker() is True


def test_stop_worker_fallback_recovers_exact_task_when_thread_does_not_exit(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(event_id="evt-fallback", task_id="task-fallback")
    with connect() as conn:
        conn.execute(
            "UPDATE ingest_tasks SET status = 'running', started_at = datetime('now'), "
            "finished_at = datetime('now'), error = 'interrupted' WHERE id = ?",
            (task_id,),
        )
        conn.execute("UPDATE events SET last_error = 'interrupted' WHERE id = 'evt-fallback'")

    process = _BlockingProcess()

    class _StuckWorker:
        join_timeouts = []

        def is_alive(self):
            return True

        def join(self, timeout=None):
            self.join_timeouts.append(timeout)

    task_queue._active_process = process
    task_queue._active_task_id = task_id
    task_queue._worker = _StuckWorker()

    with caplog.at_level("ERROR"):
        assert task_queue.stop_worker() is False

    with connect() as conn:
        task = conn.execute(
            "SELECT status, started_at, finished_at, error, retry_count FROM ingest_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        event = conn.execute(
            "SELECT status, last_error FROM events WHERE id = 'evt-fallback'"
        ).fetchone()
    assert tuple(task) == ("pending", None, None, None, 0)
    assert tuple(event) == ("pending", None)
    assert task_queue._worker.join_timeouts[0] == task_queue._SHUTDOWN_JOIN_TIMEOUT_SECONDS
    assert "fallback recovery applied task=task-fallback" in caplog.text


def test_shutdown_recovery_does_not_change_event_after_task_already_finished(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(event_id="evt-finished", task_id="task-finished")
    with connect() as conn:
        conn.execute(
            "UPDATE ingest_tasks SET status = 'done', finished_at = datetime('now') WHERE id = ?",
            (task_id,),
        )

    task_queue._restore_shutdown_interrupted_task(task_id)

    with connect() as conn:
        task = conn.execute(
            "SELECT status FROM ingest_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        event = conn.execute(
            "SELECT status FROM events WHERE id = 'evt-finished'"
        ).fetchone()
    assert task["status"] == "done"
    assert event["status"] == "processing"


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
