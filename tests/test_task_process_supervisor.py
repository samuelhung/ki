"""Contracts for process supervision extracted from :mod:`task_queue`."""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend import task_process_supervisor, task_queue
from zhiji_backend.db import connect, init_db


class _SuccessfulProcess:
    returncode = 0

    def communicate(self, timeout=None):
        return "completed", ""


def _insert_task() -> None:
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO sources (id, name, type, url, topic, priority)
               VALUES ('user-upload', 'Upload', 'manual', '', 'test', 'medium')"""
        )
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic, importance,
                       actionability, decision, status, content_type)
               VALUES ('event-success', 'user-upload', 'Task', '', 'test', 4, 4,
                       'digest', 'processing', 'event')"""
        )
        conn.execute(
            """INSERT INTO ingest_tasks
                       (id, event_id, ingest_type, payload_json, status)
               VALUES ('task-success', 'event-success', 'document', '{}', 'pending')"""
        )


def test_process_one_uses_facade_popen_and_completes_normal_exit(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    _insert_task()
    monkeypatch.setattr(
        task_queue.subprocess, "Popen", lambda *args, **kwargs: _SuccessfulProcess()
    )
    monkeypatch.setattr(task_queue, "_shutdown_flag", threading.Event())

    task_process_supervisor.process_one("task-success")

    with connect() as conn:
        row = conn.execute(
            "SELECT status, finished_at FROM ingest_tasks WHERE id = 'task-success'"
        ).fetchone()
    assert row["status"] == "done"
    assert row["finished_at"] is not None
    assert task_queue._active_process is None
    assert task_queue._active_task_id is None


def test_stop_process_tree_escalates_from_terminate_to_kill(monkeypatch):
    calls = []

    class Process:
        pid = 4242
        returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            if self.returncode is None:
                raise subprocess.TimeoutExpired(["runner"], timeout)
            return self.returncode

    process = Process()

    def killpg(group_id, sig):
        if sig == 0:
            if process.returncode is None:
                return
            raise ProcessLookupError
        calls.append(sig)
        if sig == signal.SIGKILL:
            process.returncode = -signal.SIGKILL

    monkeypatch.setattr(task_queue.os, "getpgrp", lambda: 9999)
    monkeypatch.setattr(task_queue.os, "killpg", killpg)

    result = task_process_supervisor.stop_process_tree(
        "task-stop", process, process.pid, 0
    )

    assert result == (-signal.SIGKILL, True)
    assert calls == [signal.SIGTERM, signal.SIGKILL]
