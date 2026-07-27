"""Contracts for process supervision extracted from :mod:`task_queue`."""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
import types
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


def test_stop_worker_forwards_signal_observe_and_wait_seams_at_call_time(
    monkeypatch,
):
    process = object()
    calls = []
    monkeypatch.setattr(task_queue, "_active_process", process)
    monkeypatch.setattr(task_queue, "_active_task_id", "task-forward-stop")
    monkeypatch.setattr(task_queue, "_active_process_group_id", 4242)
    monkeypatch.setattr(task_queue, "_worker", None)
    monkeypatch.setattr(task_queue, "_process_group_exists", lambda *_: False)

    def observe(proc, task_id, phase):
        calls.append(("observe", proc, task_id, phase))
        return None

    def send(proc, group_id, sig, operation, task_id):
        calls.append(("signal", proc, group_id, sig, operation, task_id))
        return True, False

    def wait(proc, group_id, task_id, timeout):
        calls.append(("wait", proc, group_id, task_id, timeout))
        return -signal.SIGTERM, True

    monkeypatch.setattr(task_queue, "_observe_process_returncode", observe)
    monkeypatch.setattr(task_queue, "_signal_ingest_process", send)
    monkeypatch.setattr(task_queue, "_wait_for_process_tree_exit", wait)
    monkeypatch.setattr(
        task_queue,
        "_record_shutdown_signal",
        lambda *args: calls.append(("record", *args)),
    )
    monkeypatch.setattr(
        task_queue,
        "_matches_shutdown_causation",
        lambda *args: calls.append(("matches", *args)) or True,
    )
    monkeypatch.setattr(
        task_queue,
        "_resolve_shutdown_interruption",
        lambda *args: calls.append(("resolve", *args)),
    )

    assert task_queue.stop_worker() is True
    assert [call[0] for call in calls] == [
        "observe",
        "signal",
        "observe",
        "record",
        "wait",
        "matches",
        "resolve",
    ]


def test_process_one_forwards_release_and_restore_seams_at_call_time(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    _insert_task()
    monkeypatch.setattr(
        task_queue.subprocess, "Popen", lambda *args, **kwargs: _SuccessfulProcess()
    )
    monkeypatch.setattr(task_queue, "_shutdown_flag", threading.Event())
    released = []
    restored = []
    monkeypatch.setattr(
        task_queue,
        "_release_active_process",
        lambda task_id, proc: released.append((task_id, proc)) or True,
    )
    monkeypatch.setattr(
        task_queue, "_restore_shutdown_interrupted_task", restored.append
    )

    task_queue._process_one("task-success")

    assert [task_id for task_id, _proc in released] == ["task-success", "task-success"]
    assert restored == ["task-success"]


def test_signal_failure_forwards_to_legacy_logging_seam(monkeypatch):
    class Process:
        def terminate(self):
            raise OSError("cannot terminate")

    calls = []
    monkeypatch.setattr(task_queue.os, "name", "not-posix")
    monkeypatch.setattr(
        task_queue,
        "_log_shutdown_operation_failure",
        lambda task_id, operation, **kwargs: calls.append((task_id, operation, kwargs)),
    )

    assert task_queue._signal_ingest_process(
        Process(), None, signal.SIGTERM, "terminate", "task-log"
    ) == (False, True)
    assert calls == [("task-log", "terminate", {})]


def test_legacy_shutdown_operation_logger_preserves_message(caplog):
    with caplog.at_level("WARNING"):
        try:
            raise OSError("stop failed")
        except OSError:
            task_queue._log_shutdown_operation_failure("task-log", "terminate")

    assert (
        "Failed to stop ingest child for task task-log during terminate" in caplog.text
    )


def test_process_one_forwards_clear_shutdown_hook_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    _insert_task()
    process = _SuccessfulProcess()
    monkeypatch.setattr(task_queue, "_shutdown_flag", threading.Event())
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(task_queue, "_shutdown_interrupted", ("task-success", process))
    monkeypatch.setattr(task_queue, "_release_active_process", lambda *_: False)
    cleared = []
    monkeypatch.setattr(
        task_queue,
        "_clear_shutdown_interrupted",
        lambda *args: cleared.append(args),
    )

    task_queue._process_one("task-success")

    assert cleared == [("task-success", process)]


def test_success_cleanup_and_payload_decode_use_facade_hooks(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    _insert_task()
    pending = tmp_path / "pending"
    pending.mkdir()
    queued = pending / "queued.pdf"
    queued.write_bytes(b"document")
    process = _SuccessfulProcess()
    calls = []
    monkeypatch.setattr(task_queue, "PENDING_DIR", pending)
    monkeypatch.setattr(task_queue, "_shutdown_flag", threading.Event())
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        task_queue,
        "json",
        types.SimpleNamespace(
            loads=lambda value: (
                calls.append(("loads", value)) or {"content_path": str(queued)}
            )
        ),
    )

    def path_factory(value):
        calls.append(("path", value))
        return Path(value)

    monkeypatch.setattr(task_queue, "Path", path_factory)
    monkeypatch.setattr(
        task_queue,
        "_safe_pending_unlink",
        lambda value: calls.append(("unlink", value)),
    )

    task_queue._process_one("task-success")

    assert calls == [
        ("loads", "{}"),
        ("path", str(queued)),
        ("unlink", str(queued)),
    ]


def test_process_group_check_resolves_errno_from_facade(monkeypatch):
    class GroupError(OSError):
        errno = 9876

    monkeypatch.setattr(
        task_queue,
        "errno",
        types.SimpleNamespace(ESRCH=9876, EPERM=9877),
    )
    monkeypatch.setattr(task_queue.os, "name", "posix")
    monkeypatch.setattr(task_queue.os, "getpgrp", lambda: 111)
    monkeypatch.setattr(
        task_queue.os, "killpg", lambda *_: (_ for _ in ()).throw(GroupError())
    )

    assert task_queue._process_group_exists(222, "task-errno") is False


def test_process_tree_wait_resolves_monotonic_and_sleep_from_facade(monkeypatch):
    times = iter([10.0, 10.1])
    sleeps = []
    groups = iter([True, False])
    monkeypatch.setattr(
        task_queue,
        "time",
        types.SimpleNamespace(monotonic=lambda: next(times), sleep=sleeps.append),
    )
    monkeypatch.setattr(task_queue, "_observe_process_returncode", lambda *_: 0)
    monkeypatch.setattr(task_queue, "_process_group_exists", lambda *_: next(groups))

    assert task_queue._wait_for_process_tree_exit(
        _SuccessfulProcess(), 4242, "task-clock", 1
    ) == (0, True)
    assert sleeps == [0.05]


def test_stop_process_tree_resolves_signals_from_facade(monkeypatch):
    sent = []
    waits = iter([(None, False), (-202, True)])
    monkeypatch.setattr(
        task_queue,
        "signal",
        types.SimpleNamespace(SIGTERM=101, SIGKILL=202),
    )
    monkeypatch.setattr(
        task_queue,
        "_signal_ingest_process",
        lambda _proc, _group, sig, _operation, _task: sent.append(sig) or (True, False),
    )
    monkeypatch.setattr(task_queue, "_observe_process_returncode", lambda *_: None)
    monkeypatch.setattr(task_queue, "_record_shutdown_signal", lambda *args: None)
    monkeypatch.setattr(
        task_queue, "_wait_for_process_tree_exit", lambda *_: next(waits)
    )

    assert task_process_supervisor.stop_process_tree(
        "task-signal", object(), 4242, 1
    ) == (-202, True)
    assert sent == [101, 202]


def test_concurrent_stop_worker_has_one_signal_owner(monkeypatch):
    class Process:
        returncode = None

    process = Process()
    owner_started = threading.Event()
    follower_waiting = threading.Event()
    release_owner = threading.Event()
    signals = []
    results = []
    monkeypatch.setattr(task_queue, "_active_process", process)
    monkeypatch.setattr(task_queue, "_active_task_id", "task-concurrent-stop")
    monkeypatch.setattr(task_queue, "_active_process_group_id", 4242)
    monkeypatch.setattr(task_queue, "_shutdown_interrupted", None)
    monkeypatch.setattr(task_queue, "_shutdown_signals_sent", set())
    monkeypatch.setattr(task_queue, "_shutdown_signal_delivery_confirmed", False)
    monkeypatch.setattr(task_queue, "_worker", None)
    monkeypatch.setattr(task_queue, "_process_group_exists", lambda *_: False)
    monkeypatch.setattr(
        task_queue, "_observe_process_returncode", lambda *_: process.returncode
    )

    def send(*_args):
        signals.append("term")
        owner_started.set()
        return True, False

    def wait(*_args):
        assert release_owner.wait(timeout=1)
        process.returncode = -signal.SIGTERM
        return process.returncode, True

    original_wait = task_process_supervisor.wait_for_shutdown_owner

    def wait_for_owner(*args):
        follower_waiting.set()
        return original_wait(*args)

    monkeypatch.setattr(task_queue, "_signal_ingest_process", send)
    monkeypatch.setattr(task_queue, "_wait_for_process_tree_exit", wait)
    monkeypatch.setattr(
        task_process_supervisor, "wait_for_shutdown_owner", wait_for_owner
    )

    owner = threading.Thread(target=lambda: results.append(task_queue.stop_worker()))
    follower = threading.Thread(target=lambda: results.append(task_queue.stop_worker()))
    owner.start()
    assert owner_started.wait(timeout=1)
    follower.start()
    assert follower_waiting.wait(timeout=1)
    assert signals == ["term"]
    release_owner.set()
    owner.join(timeout=1)
    follower.join(timeout=1)

    assert not owner.is_alive()
    assert not follower.is_alive()
    assert sorted(results) == [True, True]
    assert signals == ["term"]


def test_completed_owner_prevents_second_signal_to_reused_process_group(monkeypatch):
    class Process:
        returncode = 0

    process = Process()
    signals = []
    monkeypatch.setattr(task_queue, "_active_process", process)
    monkeypatch.setattr(task_queue, "_active_task_id", "task-reused-pgid")
    monkeypatch.setattr(task_queue, "_active_process_group_id", 5252)
    monkeypatch.setattr(task_queue, "_shutdown_interrupted", None)
    monkeypatch.setattr(task_queue, "_worker", None)
    monkeypatch.setattr(task_queue, "_observe_process_returncode", lambda *_: 0)
    monkeypatch.setattr(task_queue, "_process_group_exists", lambda *_: True)
    monkeypatch.setattr(
        task_queue,
        "_signal_ingest_process",
        lambda *_args: signals.append("signal") or (True, False),
    )
    monkeypatch.setattr(task_queue, "_wait_for_process_tree_exit", lambda *_: (0, True))

    assert task_queue.stop_worker() is True
    assert task_queue.stop_worker() is True
    assert signals == ["signal"]


def test_final_nonquiescent_check_uses_facade_group_hook(monkeypatch):
    process = object()
    facade_checks = []
    supervisor = task_queue._supervisor()
    monkeypatch.setattr(
        supervisor,
        "select_active_for_shutdown",
        lambda: (process, "task-nonquiescent", 6262, True),
    )
    monkeypatch.setattr(supervisor, "stop_process_tree", lambda *_: (None, False))
    monkeypatch.setattr(supervisor, "complete_shutdown_claim", lambda *_: None)
    monkeypatch.setattr(task_queue, "_matches_shutdown_causation", lambda *_: False)
    monkeypatch.setattr(task_queue, "_resolve_shutdown_interruption", lambda *_: None)
    monkeypatch.setattr(task_queue, "_worker", None)
    monkeypatch.setattr(
        task_queue,
        "_process_group_exists",
        lambda group_id, task_id: facade_checks.append((group_id, task_id)) or True,
    )
    monkeypatch.setattr(
        supervisor,
        "process_group_exists",
        lambda *_: (_ for _ in ()).throw(AssertionError("bypassed facade")),
    )

    assert task_queue.stop_worker() is False
    assert facade_checks == [(6262, "task-nonquiescent")]
