"""Persistent ingest task queue and worker lifecycle compatibility facade."""

from __future__ import annotations

import errno as errno
import json as json
import logging
import os as os
import shutil as shutil
import signal
import sqlite3 as sqlite3
import subprocess as subprocess
import sys as sys
import threading
import time as time
import uuid as uuid
from pathlib import Path as Path

from .db import connect as connect
from .db import init_db as init_db
from .paths import INGEST_ROOT
from .security.constraints import safe_identifier as safe_identifier
from .security.paths import PathSecurityError as PathSecurityError
from .security.paths import resolve_under as resolve_under
from .security.paths import safe_unlink_under as safe_unlink_under
from .security.redaction import classify_task_error as classify_task_error
from .security.redaction import sanitize_task_error as sanitize_task_error

logger = logging.getLogger(__name__)
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

_TASK_TIMEOUT_SECONDS = 900
_SHUTDOWN_TERMINATE_TIMEOUT_SECONDS = 5
_SHUTDOWN_JOIN_TIMEOUT_SECONDS = 10


class EnqueueError(RuntimeError):
    """Raised when a task cannot be persisted after compensation."""


def _store():
    from . import task_queue_store

    return task_queue_store


def _supervisor():
    from . import task_process_supervisor

    return task_process_supervisor


def _safe_pending_unlink(path_value: str) -> None:
    _store().safe_pending_unlink(
        path_value, PENDING_DIR, logger, Path, safe_unlink_under
    )


def _compensate_failed_enqueue(event_id: str, task_id: str) -> None:
    _store().compensate_failed_enqueue(event_id, task_id, connect, logger)


def enqueue(event_id: str, ingest_type: str, content, topic: str, title: str) -> str:
    """Enqueue an ingest task and return its ID."""
    return _store().enqueue(event_id, ingest_type, content, topic, title)


def recover_stuck() -> int:
    """Return crash-orphaned running tasks to pending."""
    return _store().recover_stuck()


def _restore_shutdown_interrupted_task(task_id: str) -> None:
    _store().restore_shutdown_interrupted_task(task_id, connect)


def _release_active_process(task_id: str, proc: subprocess.Popen[str]) -> bool:
    return _supervisor().release_active_process(task_id, proc)


def _clear_shutdown_interrupted(task_id: str, proc: subprocess.Popen[str]) -> None:
    _supervisor().clear_shutdown_interrupted(task_id, proc)


def _observe_process_returncode(
    proc: subprocess.Popen[str], task_id: str, phase: str
) -> int | None:
    return _supervisor().observe_returncode(proc, task_id, phase)


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


def _resolve_shutdown_interruption(task_id: str, proc: subprocess.Popen[str]) -> None:
    _supervisor().resolve_shutdown_interruption(task_id, proc)


def _record_shutdown_signal(
    task_id: str,
    proc: subprocess.Popen[str],
    sig: signal.Signals,
    used_fallback: bool,
    leader_returncode_after_send: int | None,
) -> None:
    _supervisor()._record_signal(
        task_id, proc, sig, used_fallback, leader_returncode_after_send
    )


def _matches_shutdown_causation(
    task_id: str, proc: subprocess.Popen[str], returncode: int | None
) -> bool:
    return _supervisor().matches_shutdown_causation(task_id, proc, returncode)


def _signal_ingest_process(
    proc: subprocess.Popen[str],
    process_group_id: int | None,
    sig: signal.Signals,
    fallback_operation: str,
    task_id: str,
) -> tuple[bool, bool]:
    return _supervisor().signal_process(
        proc,
        process_group_id,
        sig,
        fallback_operation,
        task_id,
        _log_shutdown_operation_failure,
    )


def _process_group_exists(process_group_id: int | None, task_id: str) -> bool:
    return _supervisor().process_group_exists(process_group_id, task_id)


def _wait_for_process_tree_exit(
    proc: subprocess.Popen[str],
    process_group_id: int | None,
    task_id: str,
    timeout: float,
) -> tuple[int | None, bool]:
    return _supervisor().wait_for_process_tree_exit(
        proc,
        process_group_id,
        task_id,
        timeout,
        _observe_process_returncode,
        _process_group_exists,
    )


def _process_one(task_id: str) -> None:
    supervisor = _supervisor()
    result = supervisor.process_one(task_id)
    if not (
        isinstance(result, tuple)
        and len(result) == 2
        and result[0] is supervisor.POST_PROCESS
    ):
        return result
    event_id = result[1]
    try:
        from .ai_client import chat
        from .series_auto_suggest_service import auto_suggest_series

        auto_suggest_series(event_id, connect_fn=connect, chat_fn=chat)
    except Exception:
        logger.warning("auto_suggest_series failed for %s", event_id, exc_info=True)
    _run_chain_detection(event_id)


def _run_chain_detection(event_id: str) -> None:
    try:
        from .chain_detector import detect_chain_data_hints, detect_new_chains

        hints = detect_chain_data_hints(event_id)
        if hints:
            logger.info(
                "chain_detector: found %d hint(s) for event %s", hints, event_id
            )
        chains = detect_new_chains(event_id)
        if chains:
            logger.info(
                "chain_detector: found %d new chain suggestion(s) for event %s",
                chains,
                event_id,
            )
    except Exception:
        logger.warning("chain_detector failed for %s", event_id, exc_info=True)


def _worker_loop() -> None:
    """Poll pending tasks with the established exponential error backoff."""
    max_errors, cooldown, initial, maximum = 10, 300, 2, 64
    logger.info("Ingest task worker started")
    consecutive_errors = 0
    idle_cycles = 0
    while not _shutdown_flag.is_set():
        try:
            task_id = _store().claim_pending(connect)
            if task_id:
                _process_one(task_id)
                continue
            idle_cycles += 1
            consecutive_errors = 0
            if idle_cycles % 30 == 0:
                try:
                    count = _store().cleanup_stale_processing(connect)
                    if count:
                        logger.warning(
                            "Periodic cleanup: reset %d stale processing event(s) → pending",
                            count,
                        )
                except Exception:
                    logger.warning("Periodic cleanup failed", exc_info=True)
            _shutdown_flag.wait(timeout=2)
        except Exception:
            consecutive_errors += 1
            wait = (
                cooldown
                if consecutive_errors >= max_errors
                else min(initial * (2 ** (consecutive_errors - 1)), maximum)
            )
            if wait >= cooldown:
                logger.error(
                    "Task worker: %d consecutive errors, pausing for %ds",
                    consecutive_errors,
                    wait,
                )
                _shutdown_flag.wait(timeout=wait)
                consecutive_errors = 0
            else:
                logger.exception(
                    "Task worker loop error (consecutive=%d) — retrying in %.0fs",
                    consecutive_errors,
                    wait,
                )
                _shutdown_flag.wait(timeout=wait)
    logger.info("Ingest task worker stopped")


def _worker_is_alive(worker: threading.Thread | None) -> bool:
    if worker is None:
        return False
    try:
        return worker.is_alive()
    except Exception:
        logger.error("Failed to inspect ingest task worker state", exc_info=True)
        return True


def start_worker() -> None:
    """Start the background task worker thread."""
    global _worker
    if _worker and _worker.is_alive():
        logger.info("Ingest task worker already running")
        return
    _shutdown_flag.clear()
    recovered = recover_stuck()
    if recovered:
        logger.info("Recovered %d stuck task(s)", recovered)
    _worker = threading.Thread(target=_worker_loop, daemon=True, name="ingest-worker")
    _worker.start()


def stop_worker() -> bool:
    """Stop the worker and its exact active child, returning quiescence status."""
    _shutdown_flag.set()
    supervisor = _supervisor()
    proc, task_id, group_id = supervisor.select_active_for_shutdown()
    process_tree_quiesced = True
    verified_interruption = False
    if proc is not None:
        returncode, process_tree_quiesced = supervisor.stop_process_tree(
            task_id, proc, group_id, _SHUTDOWN_TERMINATE_TIMEOUT_SECONDS
        )
        verified_interruption = _matches_shutdown_causation(task_id, proc, returncode)
        _resolve_shutdown_interruption(task_id, proc)

    worker = _worker
    if _worker_is_alive(worker):
        try:
            worker.join(timeout=_SHUTDOWN_JOIN_TIMEOUT_SECONDS)
        except Exception:
            logger.error("Failed to join ingest task worker", exc_info=True)
    worker_quiesced = not _worker_is_alive(worker)

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
                "Ingest task worker did not stop within %ss; "
                "fallback recovery applied task=%s",
                _SHUTDOWN_JOIN_TIMEOUT_SECONDS,
                task_id,
            )
        else:
            logger.error(
                "Ingest task worker did not stop within %ss; "
                "no verified interrupted task to recover",
                _SHUTDOWN_JOIN_TIMEOUT_SECONDS,
            )
    if not process_tree_quiesced:
        if supervisor.process_group_exists(group_id, task_id or "none"):
            logger.error(
                "Ingest process group still exists after SIGKILL task=%s pgid=%s",
                task_id or "none",
                group_id,
            )
        else:
            logger.error(
                "Ingest child still active after SIGKILL task=%s", task_id or "none"
            )
    return worker_quiesced and process_tree_quiesced
