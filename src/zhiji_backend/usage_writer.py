"""Bounded, process-local writer for non-critical AI usage telemetry."""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto

from .db import connect

logger = logging.getLogger(__name__)

_QUEUE_SIZE = 256
_DROP_WARNING_INTERVAL_SECONDS = 60.0
_RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2)
_DEFAULT_STOP_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class UsageRecord:
    module: str
    task: str
    model: str
    status: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    cost_rmb: float
    duration_ms: int
    error: str


class _LifecycleState(Enum):
    NEW = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    DISABLED = auto()


class _UsageWriter:
    def __init__(self, queue_size: int = _QUEUE_SIZE) -> None:
        self._queue: queue.Queue[UsageRecord] = queue.Queue(maxsize=queue_size)
        self._state_lock = threading.Lock()
        self._warning_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = _LifecycleState.NEW
        self._last_drop_warning = float("-inf")
        self._clock = time.monotonic

    def start(self) -> bool:
        with self._state_lock:
            if self._state is _LifecycleState.RUNNING:
                return self._thread is not None and self._thread.is_alive()
            if self._state in (_LifecycleState.STOPPING, _LifecycleState.DISABLED):
                return False
            return self._start_locked()

    def _start_locked(self) -> bool:
        self._stop_event.clear()
        try:
            thread = threading.Thread(
                target=self._run,
                name="ai-usage-writer",
                daemon=True,
            )
            thread.start()
        except Exception as exc:
            self._thread = None
            self._state = _LifecycleState.DISABLED
            self._stop_event.set()
            self._log_disabled(exc)
            return False
        self._thread = thread
        self._state = _LifecycleState.RUNNING
        return True

    def disable(self, exc: Exception) -> None:
        with self._state_lock:
            self._state = _LifecycleState.DISABLED
            self._stop_event.set()
        self._log_disabled(exc)

    @staticmethod
    def _log_disabled(exc: Exception) -> None:
        logger.error("AI usage writer disabled exception=%s", type(exc).__name__)

    def enqueue(self, record: UsageRecord) -> bool:
        queue_full = False
        with self._state_lock:
            if self._state is _LifecycleState.NEW and not self._start_locked():
                return False
            if self._state is not _LifecycleState.RUNNING:
                return False
            try:
                self._queue.put_nowait(record)
                return True
            except queue.Full:
                queue_full = True
        if queue_full:
            self._warn_queue_full()
        return False

    def stop(self, timeout: float = _DEFAULT_STOP_TIMEOUT_SECONDS) -> int:
        with self._state_lock:
            thread = self._thread
            if self._state is _LifecycleState.NEW:
                self._state = _LifecycleState.STOPPED
                self._stop_event.set()
                return self._unfinished_count()
            if self._state in (_LifecycleState.STOPPED, _LifecycleState.DISABLED):
                return self._unfinished_count()
            if self._state is _LifecycleState.RUNNING:
                self._state = _LifecycleState.STOPPING
            self._stop_event.set()

        if thread is not None:
            thread.join(max(0.0, timeout))
        with self._state_lock:
            alive = thread is not None and thread.is_alive()
            if not alive and self._state is _LifecycleState.STOPPING:
                self._state = _LifecycleState.STOPPED
            if not alive and self._thread is thread:
                self._thread = None
        unwritten = self._unfinished_count()
        if unwritten:
            logger.error("AI usage writer stopped with %d usage record(s) unwritten", unwritten)
        return unwritten

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set() or not self._queue.empty():
                try:
                    record = self._queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                try:
                    self._write_with_retry(record)
                finally:
                    self._queue.task_done()
        finally:
            current = threading.current_thread()
            with self._state_lock:
                if self._state is _LifecycleState.STOPPING:
                    self._state = _LifecycleState.STOPPED
                elif self._state is _LifecycleState.RUNNING:
                    self._state = _LifecycleState.DISABLED
                if self._thread is current:
                    self._thread = None

    def _write_with_retry(self, record: UsageRecord) -> bool:
        for attempt in range(len(_RETRY_DELAYS_SECONDS) + 1):
            try:
                self._write_once(record)
                return True
            except sqlite3.OperationalError as exc:
                if not self._is_busy_or_locked(exc) or attempt >= len(_RETRY_DELAYS_SECONDS):
                    self._log_permanent_failure(record, exc)
                    return False
                time.sleep(_RETRY_DELAYS_SECONDS[attempt])
            except Exception as exc:
                self._log_permanent_failure(record, exc)
                return False
        return False

    def _write_once(self, record: UsageRecord) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO ai_usage
                   (module, task, model, status, prompt_tokens, completion_tokens, total_tokens,
                    cached_tokens, reasoning_tokens, cost_rmb, duration_ms, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.module,
                    record.task,
                    record.model,
                    record.status,
                    record.prompt_tokens,
                    record.completion_tokens,
                    record.total_tokens,
                    record.cached_tokens,
                    record.reasoning_tokens,
                    record.cost_rmb,
                    record.duration_ms,
                    record.error,
                ),
            )

    @staticmethod
    def _is_busy_or_locked(exc: sqlite3.OperationalError) -> bool:
        error_code = getattr(exc, "sqlite_errorcode", None)
        if error_code is not None:
            return error_code & 0xFF in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
        message = str(exc).lower()
        return "database is locked" in message or "database is busy" in message

    @staticmethod
    def _log_permanent_failure(record: UsageRecord, exc: Exception) -> None:
        logger.error(
            "AI usage write failed module=%s task=%s status=%s exception=%s",
            record.module,
            record.task,
            record.status,
            type(exc).__name__,
        )

    def _warn_queue_full(self) -> None:
        now = self._clock()
        with self._warning_lock:
            if now - self._last_drop_warning < _DROP_WARNING_INTERVAL_SECONDS:
                return
            self._last_drop_warning = now
        logger.warning("AI usage queue full; dropping telemetry record")

    def _unfinished_count(self) -> int:
        with self._queue.all_tasks_done:
            return self._queue.unfinished_tasks


_writer = _UsageWriter()


def start_usage_writer() -> bool:
    try:
        return _writer.start()
    except Exception as exc:
        _writer.disable(exc)
        return False


def enqueue_usage(record: UsageRecord) -> bool:
    try:
        return _writer.enqueue(record)
    except Exception as exc:
        _writer.disable(exc)
        return False


def stop_usage_writer(timeout: float = _DEFAULT_STOP_TIMEOUT_SECONDS) -> int:
    try:
        return _writer.stop(timeout=timeout)
    except Exception as exc:
        _writer.disable(exc)
        return _writer._unfinished_count()
