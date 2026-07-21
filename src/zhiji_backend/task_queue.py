"""Persistent ingest task queue — replaces FastAPI BackgroundTasks.

Tasks survive server restarts. A background worker thread polls for pending
tasks and executes them one at a time. Failed tasks record their error and
can be retried via the API.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import signal
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from .db import connect, init_db

logger = logging.getLogger(__name__)

from .paths import INGEST_ROOT
PENDING_DIR = INGEST_ROOT / "pending"

_worker: threading.Thread | None = None
_shutdown_flag = threading.Event()
_active_process_lock = threading.Lock()
_active_process: subprocess.Popen[str] | None = None
_active_task_id: str | None = None
_active_process_group_id: int | None = None
_shutdown_interrupted: tuple[str, subprocess.Popen[str]] | None = None
_shutdown_signal_resolved = threading.Event()
_shutdown_signals_sent: set[int] = set()
_shutdown_signal_delivery_confirmed = False
_shutdown_fallback_causation = False


class EnqueueError(RuntimeError):
    """Raised when a task cannot be persisted after compensation."""


def _safe_pending_unlink(path_value: str) -> None:
    try:
        pending_root = PENDING_DIR.resolve()
        path = Path(path_value).expanduser().resolve()
        if path == pending_root or pending_root in path.parents:
            path.unlink(missing_ok=True)
        else:
            logger.warning("Refusing to delete pending file outside %s: %s", pending_root, path)
    except Exception:
        logger.warning("Failed to delete pending file safely: %s", path_value, exc_info=True)


def _compensate_failed_enqueue(event_id: str, task_id: str) -> None:
    try:
        with connect() as conn:
            conn.execute("DELETE FROM ingest_tasks WHERE id = ?", (task_id,))
            event = conn.execute(
                "SELECT status FROM events WHERE id = ?", (event_id,)
            ).fetchone()
            if event and event["status"] == "processing":
                surviving_task = conn.execute(
                    "SELECT 1 FROM ingest_tasks WHERE event_id = ? LIMIT 1",
                    (event_id,),
                ).fetchone()
                if not surviving_task:
                    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    except Exception:
        logger.exception("Failed to compensate enqueue failure for event %s", event_id)


def enqueue(event_id: str, ingest_type: str, content, topic: str, title: str) -> str:
    """Enqueue an ingest task. Returns the task ID.

    For file uploads (content is a Path), the file is copied to a persistent
    pending directory so it survives temp dir cleanup.
    """
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    persistent: Path | None = None
    try:
        init_db()
        if isinstance(content, Path):
            PENDING_DIR.mkdir(parents=True, exist_ok=True)
            persistent = PENDING_DIR / f"{event_id}{content.suffix}"
            shutil.copy2(content, persistent)
            payload = {"content_path": str(persistent), "topic": topic, "title": title}
        else:
            payload = {"content_text": str(content), "topic": topic, "title": title}

        with connect() as conn:
            conn.execute(
                """INSERT INTO ingest_tasks (id, event_id, ingest_type, payload_json)
                   VALUES (?, ?, ?, ?)""",
                (task_id, event_id, ingest_type, json.dumps(payload, ensure_ascii=False)),
            )
    except Exception:
        logger.exception("Failed to enqueue task for event %s", event_id)
        if persistent is not None:
            _safe_pending_unlink(str(persistent))
        _compensate_failed_enqueue(event_id, task_id)
        raise EnqueueError("任务无法加入处理队列") from None
    logger.info("Enqueued task %s for event %s (%s)", task_id, event_id, ingest_type)
    return task_id


def recover_stuck() -> int:
    """Mark any 'running' tasks as 'pending' (recovery after crash).

    Uses a standalone connection with retry and WAL checkpoint to survive
    stale locks left by a crashed predecessor process.

    Returns count of recovered tasks.
    """
    from .db import get_db_path

    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    last_err = None
    for attempt in range(1, 4):
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            # Give the WAL recovery a generous window
            conn.execute("PRAGMA busy_timeout=15000")
            # Clean up stale WAL frames left by crashed process
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            cur = conn.execute(
                "UPDATE ingest_tasks SET status = 'pending', started_at = NULL "
                "WHERE status = 'running'"
            )
            conn.commit()
            count = cur.rowcount if hasattr(cur, "rowcount") else 0
            conn.close()
            if count:
                logger.warning("Recovered %d orphaned running task(s) → pending", count)
            return count
        except Exception as e:
            last_err = e
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            wait = min(2 ** attempt, 8)
            logger.warning(
                "recover_stuck attempt %d/3 failed (%s), retrying in %ds",
                attempt, e, wait,
            )
            time.sleep(wait)

    logger.error("recover_stuck failed after 3 attempts: %s", last_err)
    return 0


# Per-task timeout to prevent a hung download/transcribe from blocking the queue forever.
# 15 minutes: document (2s) / audio (6 min poll) / video (8 min) / scanned PDF OCR (10 min + summarize)
_TASK_TIMEOUT_SECONDS = 900
_SHUTDOWN_TERMINATE_TIMEOUT_SECONDS = 5
_SHUTDOWN_JOIN_TIMEOUT_SECONDS = 10


def _restore_shutdown_interrupted_task(task_id: str) -> None:
    """Return an exact shutdown-interrupted task to its recoverable state."""
    with connect() as conn:
        row = conn.execute(
            "SELECT t.event_id, e.status AS event_status "
            "FROM ingest_tasks t JOIN events e ON e.id = t.event_id "
            "WHERE t.id = ?",
            (task_id,),
        ).fetchone()
        if not row:
            return
        if row["event_status"] == "completed":
            conn.execute(
                "UPDATE ingest_tasks SET status = 'done', "
                "finished_at = datetime('now'), error = NULL "
                "WHERE id = ? AND status = 'running'",
                (task_id,),
            )
            return
        restored = conn.execute(
            "UPDATE ingest_tasks SET status = 'pending', started_at = NULL, "
            "finished_at = NULL, error = NULL WHERE id = ? AND status = 'running'",
            (task_id,),
        )
        if restored.rowcount:
            conn.execute(
                "UPDATE events SET status = 'pending', last_error = NULL "
                "WHERE id = ? AND status = 'processing'",
                (row["event_id"],),
            )


def _release_active_process(task_id: str, proc: subprocess.Popen[str]) -> bool:
    """Release process ownership and report whether shutdown selected it."""
    global _active_process, _active_task_id, _active_process_group_id
    with _active_process_lock:
        shutdown_selected = _shutdown_interrupted == (task_id, proc)
        if _active_process is proc and _active_task_id == task_id:
            _active_process = None
            _active_task_id = None
            _active_process_group_id = None
    if not shutdown_selected:
        return False

    # stop_worker resolves this immediately after terminate() returns. Waiting
    # outside the ownership lock prevents a failed signal from being mistaken
    # for an intentional shutdown interruption.
    _shutdown_signal_resolved.wait(timeout=_SHUTDOWN_TERMINATE_TIMEOUT_SECONDS)
    return _matches_shutdown_causation(task_id, proc, proc.returncode)


def _clear_shutdown_interrupted(task_id: str, proc: subprocess.Popen[str]) -> None:
    global _shutdown_interrupted, _shutdown_signal_delivery_confirmed
    global _shutdown_fallback_causation
    with _active_process_lock:
        if _shutdown_interrupted == (task_id, proc):
            _shutdown_interrupted = None
            _shutdown_signals_sent.clear()
            _shutdown_signal_delivery_confirmed = False
            _shutdown_fallback_causation = False
            _shutdown_signal_resolved.clear()


def _observe_process_returncode(
    proc: subprocess.Popen[str], task_id: str, phase: str
) -> int | None:
    """Poll without allowing process-observation failures to escape shutdown."""
    try:
        return proc.poll()
    except Exception:
        logger.warning(
            "Failed to poll ingest child for task %s during %s",
            task_id,
            phase,
            exc_info=True,
        )
        try:
            return proc.returncode
        except Exception:
            return None


def _resolve_shutdown_interruption(task_id: str, proc: subprocess.Popen[str]) -> None:
    with _active_process_lock:
        if _shutdown_interrupted == (task_id, proc):
            _shutdown_signal_resolved.set()


def _record_shutdown_signal(
    task_id: str,
    proc: subprocess.Popen[str],
    sig: signal.Signals,
    used_fallback: bool,
    leader_returncode_after_send: int | None,
) -> None:
    global _shutdown_signal_delivery_confirmed, _shutdown_fallback_causation
    with _active_process_lock:
        if _shutdown_interrupted != (task_id, proc):
            return
        if not used_fallback:
            _shutdown_signals_sent.add(int(sig))
            _shutdown_signal_delivery_confirmed = True
        elif leader_returncode_after_send is None:
            _shutdown_signals_sent.add(int(sig))
            _shutdown_signal_delivery_confirmed = True
        elif leader_returncode_after_send == -int(sig):
            _shutdown_signals_sent.add(int(sig))
        if (
            used_fallback
            and os.name != "posix"
            and leader_returncode_after_send is None
        ):
            _shutdown_fallback_causation = True


def _matches_shutdown_causation(
    task_id: str, proc: subprocess.Popen[str], returncode: int | None
) -> bool:
    with _active_process_lock:
        if _shutdown_interrupted != (task_id, proc) or returncode is None:
            return False
        if returncode < 0 and -returncode in _shutdown_signals_sent:
            return True
        if returncode >= 0 and _shutdown_signal_delivery_confirmed:
            return True
        return _shutdown_fallback_causation


def _log_shutdown_operation_failure(
    task_id: str, operation: str, *, level: int = logging.WARNING
) -> None:
    logger.log(
        level,
        "Failed to stop ingest child for task %s during %s",
        task_id,
        operation,
        exc_info=True,
    )


def _worker_is_alive(worker: threading.Thread | None) -> bool:
    if worker is None:
        return False
    try:
        return worker.is_alive()
    except Exception:
        logger.error("Failed to inspect ingest task worker state", exc_info=True)
        return True


def _signal_ingest_process(
    proc: subprocess.Popen[str],
    process_group_id: int | None,
    sig: signal.Signals,
    fallback_operation: str,
    task_id: str,
) -> tuple[bool, bool]:
    if os.name == "posix" and process_group_id is not None:
        try:
            own_group_id = os.getpgrp()
        except Exception:
            logger.warning("Failed to inspect server process group", exc_info=True)
        else:
            if process_group_id != own_group_id:
                try:
                    os.killpg(process_group_id, sig)
                    return True, False
                except Exception:
                    _log_shutdown_operation_failure(
                        task_id, f"process-group {fallback_operation}"
                    )
            else:
                logger.error(
                    "Refusing to signal server process group for ingest task %s",
                    task_id,
                )

    try:
        getattr(proc, fallback_operation)()
        return True, True
    except Exception:
        _log_shutdown_operation_failure(task_id, fallback_operation)
        return False, True


def _process_group_exists(process_group_id: int | None, task_id: str) -> bool:
    if os.name != "posix" or process_group_id is None:
        return False
    try:
        if process_group_id == os.getpgrp():
            return False
        os.killpg(process_group_id, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        if exc.errno == errno.EPERM:
            return True
        logger.warning(
            "Failed to inspect ingest process group for task %s",
            task_id,
            exc_info=True,
        )
        return True
    except Exception:
        logger.warning(
            "Failed to inspect ingest process group for task %s",
            task_id,
            exc_info=True,
        )
        return True


def _wait_for_process_tree_exit(
    proc: subprocess.Popen[str],
    process_group_id: int | None,
    task_id: str,
    timeout: float,
) -> tuple[int | None, bool]:
    deadline = time.monotonic() + max(0.0, timeout)
    returncode = _observe_process_returncode(proc, task_id, "process-tree wait")
    while True:
        group_gone = not _process_group_exists(process_group_id, task_id)
        if returncode is not None and group_gone:
            return returncode, True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return returncode, returncode is not None and group_gone
        if returncode is None:
            try:
                returncode = proc.wait(timeout=min(0.05, remaining))
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                _log_shutdown_operation_failure(task_id, "process-tree wait")
                returncode = _observe_process_returncode(
                    proc, task_id, "after process-tree wait failure"
                )
                return returncode, (
                    returncode is not None
                    and not _process_group_exists(process_group_id, task_id)
                )
        else:
            time.sleep(min(0.05, remaining))


def _process_one(task_id: str) -> None:
    """Process a single pending task with a timeout guard.

    The actual pipeline runs in a child process so the main worker thread can
    detect hangs and terminate real work. If the timeout fires, both the queue
    task and its event are moved out of ``running``/``processing`` states so
    later polls cannot race against orphaned pipeline writes.
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT event_id, ingest_type, payload_json FROM ingest_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

    if not row:
        return

    event_id = row["event_id"]
    ingest_type = row["ingest_type"]
    payload = json.loads(row["payload_json"])

    # Reconstruct content from payload
    if payload.get("content_path"):
        content = Path(payload["content_path"])
    else:
        content = payload.get("content_text", "")

    topic = payload.get("topic", "uncategorized")
    title = payload.get("title", "")

    # Mark as running
    with connect() as conn:
        conn.execute(
            "UPDATE ingest_tasks SET status = 'running', started_at = datetime('now') WHERE id = ?",
            (task_id,),
        )

    # Check shutdown, spawn, and publish ownership atomically so stop_worker()
    # cannot miss a child created between its shutdown signal and process scan.
    global _active_process, _active_task_id, _active_process_group_id
    with _active_process_lock:
        if _shutdown_flag.is_set():
            proc = None
        else:
            popen_kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
            }
            if os.name == "posix":
                popen_kwargs["start_new_session"] = True
            proc = subprocess.Popen(
                [sys.executable, "-m", "zhiji_backend.ingest_task_runner", task_id],
                **popen_kwargs,
            )
            _active_process = proc
            _active_task_id = task_id
            pid = getattr(proc, "pid", None)
            process_group_id = (
                pid if os.name == "posix" and isinstance(pid, int) and pid > 0 else None
            )
            _active_process_group_id = process_group_id

    if proc is None:
        _restore_shutdown_interrupted_task(task_id)
        return

    interrupted_by_shutdown = False
    try:
        try:
            stdout, stderr = proc.communicate(timeout=_TASK_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process_tree_quiesced = False
            _signal_ingest_process(
                proc,
                process_group_id,
                signal.SIGTERM,
                "terminate",
                task_id,
            )
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                _signal_ingest_process(
                    proc,
                    process_group_id,
                    signal.SIGKILL,
                    "kill",
                    task_id,
                )
                try:
                    stdout, stderr = proc.communicate(
                        timeout=_SHUTDOWN_TERMINATE_TIMEOUT_SECONDS
                    )
                except subprocess.TimeoutExpired:
                    logger.error(
                        "Task %s child did not exit after timeout kill", task_id
                    )
                    stdout, stderr = "", ""
                _, process_tree_quiesced = _wait_for_process_tree_exit(
                    proc,
                    process_group_id,
                    task_id,
                    _SHUTDOWN_TERMINATE_TIMEOUT_SECONDS,
                )
            else:
                if _process_group_exists(process_group_id, task_id):
                    _signal_ingest_process(
                        proc,
                        process_group_id,
                        signal.SIGKILL,
                        "kill",
                        task_id,
                    )
                    _, process_tree_quiesced = _wait_for_process_tree_exit(
                        proc,
                        process_group_id,
                        task_id,
                        _SHUTDOWN_TERMINATE_TIMEOUT_SECONDS,
                    )
                else:
                    process_tree_quiesced = True

            interrupted_by_shutdown = _release_active_process(task_id, proc)
            if interrupted_by_shutdown:
                _restore_shutdown_interrupted_task(task_id)
                return

            if not process_tree_quiesced:
                error_msg = (
                    "内部超时：采集进程组在 SIGKILL 后仍未退出，已阻止自动重试"
                )
                with connect() as conn:
                    conn.execute(
                        "UPDATE ingest_tasks SET status = 'error', error = ?, "
                        "finished_at = datetime('now') WHERE id = ?",
                        (error_msg, task_id),
                    )
                    conn.execute(
                        "UPDATE events SET status = 'error', last_error = ? WHERE id = ?",
                        (error_msg, event_id),
                    )
                logger.error("Task %s %s", task_id, error_msg)
                return

            # Pipeline may have actually completed but the child process did not
            # exit in time. Check the event status first.
            with connect() as conn:
                event_status = conn.execute(
                    "SELECT status FROM events WHERE id = ?", (event_id,)
                ).fetchone()

                if event_status and event_status["status"] == "completed":
                    # Pipeline finished — just slow, not hung
                    conn.execute(
                        "UPDATE ingest_tasks SET status = 'done', finished_at = datetime('now') WHERE id = ?",
                        (task_id,),
                    )
                    msg = f"completed but exceeded {_TASK_TIMEOUT_SECONDS}s timeout — marked done"
                    logger.warning("Task %s %s", task_id, msg)
                else:
                    # Truly hung — check if we should auto-retry
                    retry_count = conn.execute(
                        "SELECT COALESCE(retry_count, 0) FROM ingest_tasks WHERE id = ?", (task_id,)
                    ).fetchone()
                    current_retries = retry_count[0] if retry_count else 0

                    if current_retries < 1:
                        # Auto-retry once: wait 60s then reset to pending
                        logger.warning("Task %s timed out — auto-retrying in 60s (retry %d→%d)",
                                       task_id, current_retries, current_retries + 1)
                        conn.execute(
                            "UPDATE ingest_tasks SET status = 'pending', error = NULL, "
                            "started_at = NULL, finished_at = NULL, "
                            "retry_count = COALESCE(retry_count, 0) + 1 WHERE id = ?",
                            (task_id,),
                        )
                        conn.execute(
                            "UPDATE events SET status = 'pending', last_error = NULL "
                            "WHERE id = ? AND status = 'processing'",
                            (event_id,),
                        )
                    else:
                        # Already retried once — permanent error
                        error_msg = f"任务超时（{_TASK_TIMEOUT_SECONDS}s），已自动重试1次仍失败，可能卡在下载或转写步骤"
                        conn.execute(
                            "UPDATE ingest_tasks SET status = 'error', error = ?, finished_at = datetime('now') WHERE id = ?",
                            (error_msg, task_id),
                        )
                        conn.execute(
                            "UPDATE events SET status = 'error', last_error = ? "
                            "WHERE id = ? AND status = 'processing'",
                            (error_msg, event_id),
                        )
                        logger.error("Task %s timed out after %ds + 1 retry — permanent error", task_id, _TASK_TIMEOUT_SECONDS)
            return

        interrupted_by_shutdown = _release_active_process(task_id, proc)
        if interrupted_by_shutdown:
            _restore_shutdown_interrupted_task(task_id)
            return

        if proc.returncode != 0:
            error_msg = (stderr or stdout or f"ingest child exited with {proc.returncode}")[-500:]
            with connect() as conn:
                conn.execute(
                    "UPDATE ingest_tasks SET status = 'error', error = ?, finished_at = datetime('now') WHERE id = ?",
                    (error_msg, task_id),
                )
                conn.execute(
                    "UPDATE events SET status = 'error', last_error = ? "
                    "WHERE id = ? AND status = 'processing'",
                    (error_msg, event_id),
                )
            logger.error("Task %s failed for event %s: %s", task_id, event_id, error_msg)
            return

        # Success
        with connect() as conn:
            conn.execute(
                "UPDATE ingest_tasks SET status = 'done', finished_at = datetime('now') WHERE id = ?",
                (task_id,),
            )
        # Cleanup pending file if any
        if content_path := payload.get("content_path"):
            _safe_pending_unlink(str(content_path))
        logger.info("Task %s completed for event %s", task_id, event_id)
    finally:
        shutdown_state_owned = _shutdown_interrupted == (task_id, proc)
        interrupted_by_shutdown = _release_active_process(task_id, proc) or interrupted_by_shutdown
        if shutdown_state_owned:
            _clear_shutdown_interrupted(task_id, proc)

    # Auto-suggest: AI checks if this event belongs to any existing series
    try:
        from .routes.series_routes import auto_suggest_series
        auto_suggest_series(event_id)
    except Exception:
        logger.warning("auto_suggest_series failed for %s", event_id, exc_info=True)

    # Chain data detection: check if content contains chain node data updates
    try:
        from .chain_detector import detect_chain_data_hints, detect_new_chains
        hints_found = detect_chain_data_hints(event_id)
        if hints_found:
            logger.info("chain_detector: found %d hint(s) for event %s", hints_found, event_id)
        new_chains = detect_new_chains(event_id)
        if new_chains:
            logger.info("chain_detector: found %d new chain suggestion(s) for event %s", new_chains, event_id)
    except Exception:
        logger.warning("chain_detector failed for %s", event_id, exc_info=True)


def _worker_loop() -> None:
    """Background worker: poll for pending tasks and process them one at a time.

    Uses exponential backoff on errors to avoid CPU spin and log floods.
    After MAX_CONSECUTIVE_ERRORS, pauses for a cooldown period before retrying.
    """
    MAX_CONSECUTIVE_ERRORS = 10
    COOLDOWN_SECONDS = 300  # 5 minutes
    INITIAL_BACKOFF = 2
    MAX_BACKOFF = 64

    logger.info("Ingest task worker started")
    consecutive_errors = 0
    idle_cycles = 0

    def _backoff_wait() -> float:
        """Calculate wait time. Returns COOLDOWN_SECONDS when max errors reached."""
        nonlocal consecutive_errors
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            return COOLDOWN_SECONDS
        return min(INITIAL_BACKOFF * (2 ** (consecutive_errors - 1)), MAX_BACKOFF)

    while not _shutdown_flag.is_set():
        try:
            task_id = None
            with connect() as conn:
                row = conn.execute(
                    "SELECT id FROM ingest_tasks WHERE status = 'pending' ORDER BY created_at LIMIT 1"
                ).fetchone()
                if row:
                    candidate = row["id"]
                    cur = conn.execute(
                        "UPDATE ingest_tasks SET status = 'running', started_at = datetime('now') "
                        "WHERE id = ? AND status = 'pending'",
                        (candidate,),
                    )
                    if cur.rowcount:
                        task_id = candidate

            if task_id:
                _process_one(task_id)
            else:
                # No pending tasks — idle, reset error counter
                idle_cycles += 1
                consecutive_errors = 0

                # Periodic cleanup: only reset events whose queue task has been stuck for over 1 hour.
                if idle_cycles % 30 == 0:
                    try:
                        with connect() as conn:
                            stuck_rows = conn.execute(
                                """SELECT e.id
                                   FROM events e
                                   WHERE e.status = 'processing'
                                     AND NOT EXISTS (
                                       SELECT 1 FROM ingest_tasks t
                                       WHERE t.event_id = e.id
                                         AND t.status = 'running'
                                     )
                                     AND EXISTS (
                                       SELECT 1 FROM ingest_tasks t
                                       WHERE t.event_id = e.id
                                         AND t.status IN ('pending', 'error', 'done')
                                         AND COALESCE(t.started_at, t.created_at) < datetime('now', '-1 hour')
                                     )"""
                            ).fetchall()
                            if stuck_rows:
                                ids = [row["id"] for row in stuck_rows]
                                placeholders = ",".join("?" for _ in ids)
                                conn.execute(
                                    f"UPDATE events SET status = 'pending' WHERE id IN ({placeholders})",
                                    ids,
                                )
                                logger.warning("Periodic cleanup: reset %d stale processing event(s) → pending", len(ids))
                    except Exception:
                        logger.warning("Periodic cleanup failed", exc_info=True)

                _shutdown_flag.wait(timeout=2)
        except Exception:
            consecutive_errors += 1
            wait = _backoff_wait()
            if wait >= COOLDOWN_SECONDS:
                logger.error(
                    "Task worker: %d consecutive errors, pausing for %ds",
                    consecutive_errors, wait,
                )
                _shutdown_flag.wait(timeout=wait)
                consecutive_errors = 0  # reset after cooldown
            else:
                logger.exception(
                    "Task worker loop error (consecutive=%d) — retrying in %.0fs",
                    consecutive_errors, wait,
                )
                _shutdown_flag.wait(timeout=wait)

    logger.info("Ingest task worker stopped")


def start_worker() -> None:
    """Start the background task worker thread."""
    global _worker, _shutdown_flag
    if _worker and _worker.is_alive():
        logger.info("Ingest task worker already running")
        return
    _shutdown_flag.clear()

    # Recover any tasks that were running when the server crashed
    recovered = recover_stuck()
    if recovered:
        logger.info("Recovered %d stuck task(s)", recovered)

    _worker = threading.Thread(target=_worker_loop, daemon=True, name="ingest-worker")
    _worker.start()


def stop_worker() -> bool:
    """Stop the worker and its exact active child, returning quiescence status."""
    global _shutdown_interrupted, _shutdown_signal_delivery_confirmed
    global _shutdown_fallback_causation
    _shutdown_flag.set()
    with _active_process_lock:
        proc = _active_process
        task_id = _active_task_id
        process_group_id = _active_process_group_id
        if proc is None or task_id is None:
            proc = None
            task_id = None
            process_group_id = None
        else:
            leader_alive = (
                _observe_process_returncode(proc, task_id, "selection") is None
            )
            group_alive = _process_group_exists(process_group_id, task_id)
            if leader_alive:
                _shutdown_interrupted = (task_id, proc)
                _shutdown_signals_sent.clear()
                _shutdown_signal_delivery_confirmed = False
                _shutdown_fallback_causation = False
                _shutdown_signal_resolved.clear()
            elif not group_alive:
                proc = None
                task_id = None
                process_group_id = None

    process_tree_quiesced = True
    verified_interruption = False
    if proc is not None:
        sent, used_fallback = _signal_ingest_process(
            proc, process_group_id, signal.SIGTERM, "terminate", task_id
        )
        if sent:
            returncode_after_send = _observe_process_returncode(
                proc, task_id, "after terminate"
            )
            _record_shutdown_signal(
                task_id,
                proc,
                signal.SIGTERM,
                used_fallback,
                returncode_after_send,
            )

        if sent:
            returncode, process_tree_quiesced = _wait_for_process_tree_exit(
                proc,
                process_group_id,
                task_id,
                _SHUTDOWN_TERMINATE_TIMEOUT_SECONDS,
            )
        else:
            returncode = _observe_process_returncode(
                proc, task_id, "after failed terminate"
            )
            process_tree_quiesced = (
                returncode is not None
                and not _process_group_exists(process_group_id, task_id)
            )
        if not process_tree_quiesced:
            sent, used_fallback = _signal_ingest_process(
                proc, process_group_id, signal.SIGKILL, "kill", task_id
            )
            if sent:
                returncode_after_send = _observe_process_returncode(
                    proc, task_id, "after kill"
                )
                _record_shutdown_signal(
                    task_id,
                    proc,
                    signal.SIGKILL,
                    used_fallback,
                    returncode_after_send,
                )
            returncode, process_tree_quiesced = _wait_for_process_tree_exit(
                proc,
                process_group_id,
                task_id,
                _SHUTDOWN_TERMINATE_TIMEOUT_SECONDS,
            )

        verified_interruption = _matches_shutdown_causation(
            task_id, proc, returncode
        )
        _resolve_shutdown_interruption(task_id, proc)

    worker = _worker
    if _worker_is_alive(worker):
        try:
            worker.join(timeout=_SHUTDOWN_JOIN_TIMEOUT_SECONDS)
        except Exception:
            logger.error("Failed to join ingest task worker", exc_info=True)

    worker_quiesced = not _worker_is_alive(worker)
    quiesced = worker_quiesced and process_tree_quiesced

    if not worker_quiesced:
        fallback_applied = False
        if task_id is not None and verified_interruption:
            try:
                _restore_shutdown_interrupted_task(task_id)
                fallback_applied = True
            except Exception:
                logger.error(
                    "Failed fallback recovery for shutdown-interrupted task %s",
                    task_id,
                    exc_info=True,
                )
        if fallback_applied:
            logger.error(
                "Ingest task worker did not stop within %ss; fallback recovery applied task=%s",
                _SHUTDOWN_JOIN_TIMEOUT_SECONDS,
                task_id,
            )
        else:
            logger.error(
                "Ingest task worker did not stop within %ss; no verified interrupted task to recover",
                _SHUTDOWN_JOIN_TIMEOUT_SECONDS,
            )
    if not process_tree_quiesced:
        if _process_group_exists(process_group_id, task_id or "none"):
            logger.error(
                "Ingest process group still exists after SIGKILL task=%s pgid=%s",
                task_id or "none",
                process_group_id,
            )
        else:
            logger.error(
                "Ingest child still active after SIGKILL task=%s",
                task_id or "none",
            )
    return quiesced
