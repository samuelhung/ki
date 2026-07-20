"""Tests for ingest task queue timeout isolation."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
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

    def poll(self):
        return self.returncode

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


class _AlreadyExitedProcess:
    returncode = None

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.terminated = False
        self.poll_calls = 0

    def communicate(self, timeout=None):
        self.started.set()
        if not self.release.wait(timeout=2):
            raise AssertionError("normal child result was not observed")
        return "completed", ""

    def poll(self):
        self.poll_calls += 1
        self.returncode = 0
        self.release.set()
        return 0

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


class _ExitedBetweenPollAndTerminateProcess(_AlreadyExitedProcess):
    def poll(self):
        self.poll_calls += 1
        if self.poll_calls == 1:
            return None
        self.returncode = 0
        self.release.set()
        return 0

    def terminate(self):
        self.terminated = True


class _ShutdownOperationFailureProcess:
    returncode = None

    def __init__(self, failure_point: str):
        self.failure_point = failure_point
        self.calls: list[str] = []
        self.wait_calls = 0
        self.killed = False

    def poll(self):
        return None

    def terminate(self):
        self.calls.append("terminate")
        if self.failure_point == "terminate":
            raise RuntimeError("terminate failed")

    def wait(self, timeout=None):
        self.wait_calls += 1
        self.calls.append(f"wait-{self.wait_calls}")
        if self.failure_point == "wait":
            raise RuntimeError("wait failed")
        if not self.killed:
            time.sleep(timeout or 0)
            raise task_queue.subprocess.TimeoutExpired(cmd=["runner"], timeout=timeout or 0)
        if self.failure_point == "post-kill-wait":
            raise RuntimeError("post-kill wait failed")
        self.returncode = -9
        return self.returncode

    def kill(self):
        self.calls.append("kill")
        if self.failure_point == "kill":
            raise RuntimeError("kill failed")
        self.killed = True


class _GroupSignalProcess(_BlockingProcess):
    def __init__(self, *, survive_terminate: bool = False):
        super().__init__()
        self.pid = 4242
        self.descendant_survives_terminate = survive_terminate
        self.group_alive = True
        self.fallback_terminate_called = False
        self.fallback_kill_called = False

    def terminate(self):
        self.fallback_terminate_called = True
        super().terminate()

    def kill(self):
        self.fallback_kill_called = True
        super().kill()

    def receive_group_signal(self, sig):
        if sig == signal.SIGTERM:
            self.terminated = True
            self.returncode = -signal.SIGTERM
            self.exited.set()
            if not self.descendant_survives_terminate:
                self.group_alive = False
        elif sig == signal.SIGKILL:
            self.killed = True
            self.returncode = -signal.SIGKILL
            self.exited.set()
            self.group_alive = False


class _TimeoutGroupProcess(_TimeoutProcess):
    def __init__(self):
        self.pid = 4343
        self.returncode = None
        self.terminated = False
        self.killed = False
        self.group_alive = True

    def poll(self):
        return self.returncode

    def receive_group_signal(self, sig):
        if sig == signal.SIGTERM:
            self.terminated = True
            self.returncode = -signal.SIGTERM
        elif sig == signal.SIGKILL:
            self.killed = True
            self.group_alive = False


class _UnkillableTimeoutGroupProcess(_TimeoutGroupProcess):
    def __init__(self, *, leader_exits_after_term: bool):
        super().__init__()
        self.leader_exits_after_term = leader_exits_after_term

    def communicate(self, timeout=None):
        if not self.terminated:
            raise task_queue.subprocess.TimeoutExpired(
                cmd=["runner"], timeout=timeout or 0
            )
        if not self.killed and not self.leader_exits_after_term:
            raise task_queue.subprocess.TimeoutExpired(
                cmd=["runner"], timeout=timeout or 0
            )
        return "", ""

    def receive_group_signal(self, sig):
        if sig == signal.SIGTERM:
            self.terminated = True
            if self.leader_exits_after_term:
                self.returncode = -signal.SIGTERM
        elif sig == signal.SIGKILL:
            self.killed = True
            self.returncode = -signal.SIGKILL


class _UnrelatedSignalProcess(_BlockingProcess):
    def terminate(self):
        self.terminated = True
        self.returncode = -signal.SIGINT
        self.exited.set()

    def communicate(self, timeout=None):
        self.started.set()
        if not self.exited.wait(timeout=2):
            raise AssertionError("unrelated signal result was not released")
        return "", "unrelated signal"


class _HandledShutdownSignalProcess(_BlockingProcess):
    def __init__(self, returncode: int):
        super().__init__()
        self.handled_returncode = returncode

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        if not self.terminated:
            raise task_queue.subprocess.TimeoutExpired(
                cmd=["runner"], timeout=timeout or 0
            )
        self.returncode = self.handled_returncode
        self.exited.set()
        return self.returncode

    def communicate(self, timeout=None):
        self.started.set()
        if not self.exited.wait(timeout=2):
            raise AssertionError("handled shutdown result was not released")
        return "", "handled shutdown"


class _ImmediateHandledGroupSignalProcess(_BlockingProcess):
    def __init__(self, returncode: int):
        super().__init__()
        self.pid = 4545
        self.handled_returncode = returncode
        self.group_alive = True

    def receive_group_signal(self, sig):
        if sig == signal.SIGTERM:
            self.terminated = True
            self.returncode = self.handled_returncode
            self.group_alive = False
            self.exited.set()

    def communicate(self, timeout=None):
        self.started.set()
        if not self.exited.wait(timeout=2):
            raise AssertionError("handled process-group result was not released")
        return "", "handled process-group shutdown"


class _JoinableWorker:
    def __init__(self):
        self.alive = True
        self.join_timeout = None

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_timeout = timeout
        self.alive = False


@pytest.fixture(autouse=True)
def _reset_worker_state():
    task_queue._shutdown_flag.clear()
    task_queue._worker = None
    if hasattr(task_queue, "_active_process"):
        task_queue._active_process = None
    if hasattr(task_queue, "_active_task_id"):
        task_queue._active_task_id = None
    if hasattr(task_queue, "_active_process_group_id"):
        task_queue._active_process_group_id = None
    if hasattr(task_queue, "_shutdown_interrupted"):
        task_queue._shutdown_interrupted = None
    if hasattr(task_queue, "_shutdown_signals_sent"):
        task_queue._shutdown_signals_sent.clear()
    if hasattr(task_queue, "_shutdown_signal_delivery_confirmed"):
        task_queue._shutdown_signal_delivery_confirmed = False
    if hasattr(task_queue, "_shutdown_fallback_causation"):
        task_queue._shutdown_fallback_causation = False
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


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups only")
def test_timeout_terminates_remaining_runner_descendants(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(
        event_id="evt-timeout-group", task_id="task-timeout-group"
    )
    process = _TimeoutGroupProcess()
    signals = []

    def kill_group(group_id, sig):
        if sig == 0:
            if process.group_alive:
                return
            raise ProcessLookupError
        signals.append((group_id, sig))
        process.receive_group_signal(sig)

    monkeypatch.setattr(task_queue, "_TASK_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(task_queue.os, "getpgrp", lambda: 9999)
    monkeypatch.setattr(task_queue.os, "killpg", kill_group)
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: process)

    task_queue._process_one(task_id)

    assert signals == [
        (process.pid, signal.SIGTERM),
        (process.pid, signal.SIGKILL),
    ]
    with connect() as conn:
        task = conn.execute(
            "SELECT status, retry_count FROM ingest_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        event = conn.execute(
            "SELECT status FROM events WHERE id = 'evt-timeout-group'"
        ).fetchone()
    assert tuple(task) == ("pending", 1)
    assert event["status"] == "pending"


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups only")
@pytest.mark.parametrize("leader_exits_after_term", [True, False])
def test_timeout_orphaned_process_tree_is_not_requeued(
    leader_exits_after_term, tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(
        event_id=f"evt-timeout-orphan-{leader_exits_after_term}",
        task_id=f"task-timeout-orphan-{leader_exits_after_term}",
    )
    process = _UnkillableTimeoutGroupProcess(
        leader_exits_after_term=leader_exits_after_term
    )
    signals = []

    def kill_group(group_id, sig):
        if sig == 0:
            return
        signals.append((group_id, sig))
        process.receive_group_signal(sig)

    monkeypatch.setattr(task_queue, "_TASK_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(task_queue, "_SHUTDOWN_TERMINATE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(task_queue.os, "getpgrp", lambda: 9999)
    monkeypatch.setattr(task_queue.os, "killpg", kill_group)
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: process)

    with caplog.at_level("ERROR"):
        task_queue._process_one(task_id)

    assert signals == [
        (process.pid, signal.SIGTERM),
        (process.pid, signal.SIGKILL),
    ]
    with connect() as conn:
        task = conn.execute(
            "SELECT status, error, retry_count FROM ingest_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        event = conn.execute(
            "SELECT status, last_error FROM events WHERE id = ?",
            (f"evt-timeout-orphan-{leader_exits_after_term}",),
        ).fetchone()
    assert task["status"] == "error"
    assert "SIGKILL" in task["error"]
    assert task["retry_count"] == 0
    assert tuple(event) == ("error", task["error"])
    assert "阻止自动重试" in caplog.text


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


@pytest.mark.skipif(os.name != "posix", reason="POSIX process sessions only")
def test_ingest_runner_starts_in_its_own_session(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(event_id="evt-session", task_id="task-session")
    observed_kwargs = {}

    def spawn(*args, **kwargs):
        observed_kwargs.update(kwargs)
        return _FailingProcess()

    monkeypatch.setattr(task_queue.subprocess, "Popen", spawn)

    task_queue._process_one(task_id)

    assert observed_kwargs["start_new_session"] is True


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
    monkeypatch.setattr(task_queue, "_SHUTDOWN_TERMINATE_TIMEOUT_SECONDS", 0.1)

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


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups only")
@pytest.mark.parametrize(
    "survive_terminate, expected_signals",
    [
        (False, [signal.SIGTERM]),
        (True, [signal.SIGTERM, signal.SIGKILL]),
    ],
)
def test_stop_worker_signals_entire_process_group(
    survive_terminate, expected_signals, monkeypatch
):
    process = _GroupSignalProcess(survive_terminate=survive_terminate)
    worker = _JoinableWorker()
    signals = []

    def kill_group(group_id, sig):
        if sig == 0:
            if process.group_alive:
                return
            raise ProcessLookupError
        signals.append((group_id, sig))
        process.receive_group_signal(sig)

    monkeypatch.setattr(task_queue.os, "getpgrp", lambda: 9999)
    monkeypatch.setattr(task_queue.os, "killpg", kill_group)
    monkeypatch.setattr(task_queue, "_SHUTDOWN_TERMINATE_TIMEOUT_SECONDS", 0.01)
    task_queue._active_process = process
    task_queue._active_process_group_id = process.pid
    task_queue._active_task_id = "task-group"
    task_queue._worker = worker

    assert task_queue.stop_worker() is True

    assert signals == [(process.pid, sig) for sig in expected_signals]
    assert process.fallback_terminate_called is False
    assert process.fallback_kill_called is False
    assert worker.join_timeout == task_queue._SHUTDOWN_JOIN_TIMEOUT_SECONDS


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups only")
def test_stop_worker_reports_nonquiescent_when_group_survives_sigkill(
    monkeypatch, caplog
):
    process = _GroupSignalProcess(survive_terminate=True)
    worker = _JoinableWorker()
    signals = []

    def kill_group(group_id, sig):
        if sig == 0:
            return
        signals.append((group_id, sig))
        if sig == signal.SIGTERM:
            process.receive_group_signal(sig)

    monkeypatch.setattr(task_queue, "_SHUTDOWN_TERMINATE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(task_queue.os, "getpgrp", lambda: 9999)
    monkeypatch.setattr(task_queue.os, "killpg", kill_group)
    task_queue._active_process = process
    task_queue._active_process_group_id = process.pid
    task_queue._active_task_id = "task-stubborn-group"
    task_queue._worker = worker

    with caplog.at_level("ERROR"):
        assert task_queue.stop_worker() is False

    assert signals == [
        (process.pid, signal.SIGTERM),
        (process.pid, signal.SIGKILL),
    ]
    assert "process group" in caplog.text


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups only")
def test_stop_worker_never_signals_its_own_process_group(monkeypatch):
    process = _GroupSignalProcess()
    process.pid = os.getpgrp()
    worker = _JoinableWorker()
    group_signals = []
    monkeypatch.setattr(task_queue.os, "killpg", lambda *args: group_signals.append(args))
    task_queue._active_process = process
    task_queue._active_process_group_id = process.pid
    task_queue._active_task_id = "task-own-group"
    task_queue._worker = worker

    assert task_queue.stop_worker() is True

    assert group_signals == []
    assert process.fallback_terminate_called is True


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups only")
def test_stop_worker_terminates_real_parent_and_descendant_processes(monkeypatch):
    script = (
        "import subprocess, sys, time; "
        "code = \"import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('ready', flush=True); time.sleep(10)\"; "
        "child = subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE, text=True); "
        "child.stdout.readline(); print(child.pid, flush=True); time.sleep(10)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    assert process.stdout is not None
    child_pid = int(process.stdout.readline().strip())
    worker = _JoinableWorker()
    task_queue._active_process = process
    task_queue._active_process_group_id = process.pid
    task_queue._active_task_id = "task-real-group"
    task_queue._worker = worker
    monkeypatch.setattr(task_queue, "_SHUTDOWN_TERMINATE_TIMEOUT_SECONDS", 0.2)

    try:
        assert task_queue.stop_worker() is True
        assert process.poll() is not None

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            except PermissionError:
                pytest.skip("process inspection is restricted in this environment")
            time.sleep(0.05)
        else:
            pytest.fail(f"descendant process {child_pid} is still running")
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            process.wait(timeout=4)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups only")
def test_stop_worker_cleans_group_after_leader_already_exited_normally(monkeypatch):
    script = (
        "import subprocess, sys; "
        "code = \"import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('ready', flush=True); time.sleep(10)\"; "
        "child = subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE, text=True); "
        "child.stdout.readline(); print(child.pid, flush=True)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    assert process.stdout is not None
    child_pid = int(process.stdout.readline().strip())
    assert process.wait(timeout=2) == 0
    worker = _JoinableWorker()
    task_queue._active_process = process
    task_queue._active_process_group_id = process.pid
    task_queue._active_task_id = "task-leader-exited"
    task_queue._worker = worker
    monkeypatch.setattr(task_queue, "_SHUTDOWN_TERMINATE_TIMEOUT_SECONDS", 0.2)

    try:
        assert task_queue.stop_worker() is True
        assert task_queue._shutdown_interrupted is None

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            except PermissionError:
                pytest.skip("process inspection is restricted in this environment")
            time.sleep(0.05)
        else:
            pytest.fail(f"descendant process {child_pid} is still running")
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def test_already_exited_child_is_not_reclassified_as_shutdown_interrupted(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(
        event_id="evt-already-exited", task_id="task-already-exited"
    )
    with connect() as conn:
        conn.execute(
            "UPDATE events SET status = 'completed' WHERE id = 'evt-already-exited'"
        )

    process = _AlreadyExitedProcess()
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: process)
    worker = threading.Thread(target=task_queue._process_one, args=(task_id,))
    task_queue._worker = worker
    worker.start()
    assert process.started.wait(timeout=1)

    assert task_queue.stop_worker() is True

    with connect() as conn:
        task = conn.execute(
            "SELECT status FROM ingest_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        event = conn.execute(
            "SELECT status FROM events WHERE id = 'evt-already-exited'"
        ).fetchone()
    assert process.poll_calls >= 1
    assert process.terminated is False
    assert task["status"] == "done"
    assert event["status"] == "completed"


def test_noop_terminate_after_exit_is_not_shutdown_causation(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(
        event_id="evt-exit-race", task_id="task-exit-race"
    )
    with connect() as conn:
        conn.execute("UPDATE events SET status = 'completed' WHERE id = 'evt-exit-race'")

    process = _ExitedBetweenPollAndTerminateProcess()
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: process)
    worker = threading.Thread(target=task_queue._process_one, args=(task_id,))
    task_queue._worker = worker
    worker.start()
    assert process.started.wait(timeout=1)

    assert task_queue.stop_worker() is True

    with connect() as conn:
        task = conn.execute(
            "SELECT status FROM ingest_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        event = conn.execute(
            "SELECT status FROM events WHERE id = 'evt-exit-race'"
        ).fetchone()
    assert process.terminated is True
    assert process.poll_calls >= 2
    assert task["status"] == "done"
    assert event["status"] == "completed"


@pytest.mark.parametrize(
    "failure_point, expected_calls, expected_quiesced",
    [
        ("terminate", ["terminate", "kill", "wait-1"], True),
        ("wait", ["terminate", "wait-1", "kill", "wait-2"], False),
        ("kill", ["terminate", "wait-1", "kill", "wait-2"], False),
        ("post-kill-wait", ["terminate", "wait-1", "kill", "wait-2"], False),
    ],
)
def test_stop_worker_contains_shutdown_operation_failures(
    failure_point, expected_calls, expected_quiesced, monkeypatch, caplog
):
    process = _ShutdownOperationFailureProcess(failure_point)

    worker = _JoinableWorker()
    task_queue._active_process = process
    task_queue._active_task_id = "task-operation-failure"
    task_queue._worker = worker
    monkeypatch.setattr(task_queue, "_SHUTDOWN_TERMINATE_TIMEOUT_SECONDS", 0.01)

    with caplog.at_level("WARNING"):
        assert task_queue.stop_worker() is expected_quiesced

    assert process.calls == expected_calls
    assert worker.join_timeout == task_queue._SHUTDOWN_JOIN_TIMEOUT_SECONDS
    assert "Failed to stop ingest child" in caplog.text


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


def test_unrelated_negative_exit_is_not_shutdown_interruption_and_clears_state(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(
        event_id="evt-unrelated-signal", task_id="task-unrelated-signal"
    )
    process = _UnrelatedSignalProcess()
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
    assert tuple(task) == ("error", "unrelated signal")
    assert task_queue._shutdown_interrupted is None
    assert not task_queue._shutdown_signals_sent
    assert task_queue._shutdown_fallback_causation is False
    assert task_queue._shutdown_signal_resolved.is_set() is False


@pytest.mark.parametrize("returncode", [0, 1])
def test_handled_exit_after_confirmed_shutdown_signal_restores_pending(
    tmp_path, monkeypatch, returncode
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(
        event_id="evt-handled-signal", task_id="task-handled-signal"
    )
    process = _HandledShutdownSignalProcess(returncode=returncode)
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: process)
    worker = threading.Thread(target=task_queue._process_one, args=(task_id,))
    task_queue._worker = worker
    worker.start()
    assert process.started.wait(timeout=1)

    assert task_queue.stop_worker() is True

    with connect() as conn:
        task = conn.execute(
            "SELECT status, started_at, finished_at, error FROM ingest_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        event = conn.execute(
            "SELECT status, last_error FROM events WHERE id = 'evt-handled-signal'"
        ).fetchone()
    assert tuple(task) == ("pending", None, None, None)
    assert tuple(event) == ("pending", None)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups only")
@pytest.mark.parametrize("returncode", [0, 1])
def test_process_group_signal_immediate_handled_exit_restores_pending(
    tmp_path, monkeypatch, returncode
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(
        event_id=f"evt-group-handled-{returncode}",
        task_id=f"task-group-handled-{returncode}",
    )
    process = _ImmediateHandledGroupSignalProcess(returncode)
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(task_queue.os, "getpgrp", lambda: 9999)

    def kill_group(group_id, sig):
        assert group_id == process.pid
        if sig == 0:
            if process.group_alive:
                return
            raise ProcessLookupError
        process.receive_group_signal(sig)

    monkeypatch.setattr(task_queue.os, "killpg", kill_group)
    worker = threading.Thread(target=task_queue._process_one, args=(task_id,))
    task_queue._worker = worker
    worker.start()
    assert process.started.wait(timeout=1)

    assert task_queue.stop_worker() is True

    with connect() as conn:
        task = conn.execute(
            "SELECT status, started_at, finished_at, error FROM ingest_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        event = conn.execute(
            "SELECT status, last_error FROM events WHERE id = ?",
            (f"evt-group-handled-{returncode}",),
        ).fetchone()
    assert tuple(task) == ("pending", None, None, None)
    assert tuple(event) == ("pending", None)


def test_completed_event_during_shutdown_child_tail_finalizes_task_done(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    task_id = _insert_processing_task(
        event_id="evt-completed-tail", task_id="task-completed-tail"
    )
    with connect() as conn:
        conn.execute(
            "UPDATE events SET status = 'completed' WHERE id = 'evt-completed-tail'"
        )
    process = _HandledShutdownSignalProcess(returncode=1)
    monkeypatch.setattr(task_queue.subprocess, "Popen", lambda *args, **kwargs: process)
    worker = threading.Thread(target=task_queue._process_one, args=(task_id,))
    task_queue._worker = worker
    worker.start()
    assert process.started.wait(timeout=1)

    assert task_queue.stop_worker() is True

    with connect() as conn:
        task = conn.execute(
            "SELECT status, started_at, finished_at, error FROM ingest_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        event = conn.execute(
            "SELECT status, last_error FROM events WHERE id = 'evt-completed-tail'"
        ).fetchone()
    assert task["status"] == "done"
    assert task["started_at"] is not None
    assert task["finished_at"] is not None
    assert task["error"] is None
    assert tuple(event) == ("completed", None)


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
