"""Persistent ingest task queue — replaces FastAPI BackgroundTasks.

Tasks survive server restarts. A background worker thread polls for pending
tasks and executes them one at a time. Failed tasks record their error and
can be retried via the API.
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
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


def enqueue(event_id: str, ingest_type: str, content, topic: str, title: str) -> str:
    """Enqueue an ingest task. Returns the task ID.

    For file uploads (content is a Path), the file is copied to a persistent
    pending directory so it survives temp dir cleanup.
    """
    init_db()
    task_id = f"task-{uuid.uuid4().hex[:12]}"

    if isinstance(content, Path):
        # File upload — persist to pending dir
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        persistent = PENDING_DIR / f"{event_id}{content.suffix}"
        shutil.copy2(content, persistent)
        payload = {"content_path": str(persistent), "topic": topic, "title": title}
    else:
        # String content (douyin share text)
        payload = {"content_text": str(content), "topic": topic, "title": title}

    with connect() as conn:
        conn.execute(
            """INSERT INTO ingest_tasks (id, event_id, ingest_type, payload_json)
               VALUES (?, ?, ?, ?)""",
            (task_id, event_id, ingest_type, json.dumps(payload, ensure_ascii=False)),
        )
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


def _process_one(task_id: str) -> None:
    """Process a single pending task with a timeout guard.

    The actual pipeline runs in a child thread so the main worker thread can
    detect hangs.  If the timeout fires the child is abandoned (Python cannot
    kill threads safely), but the task is marked as error in the database.
    On the next server restart ``recover_stuck()`` will clean up the orphan.
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

    # Run pipeline in a child thread so we can enforce a timeout
    pipeline_error: Exception | None = None

    def _run_pipeline() -> None:
        nonlocal pipeline_error
        try:
            from .routes.ingest_routes import _process_ingest
            _process_ingest(event_id, ingest_type, content, topic, title)
        except Exception as e:
            pipeline_error = e

    child = threading.Thread(target=_run_pipeline, daemon=True, name=f"ingest-{task_id[:12]}")
    child.start()
    child.join(timeout=_TASK_TIMEOUT_SECONDS)

    if child.is_alive():
        # Pipeline may have actually completed but the child thread
        # hasn't exited yet. Check the event status first.
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
                else:
                    # Already retried once — permanent error
                    error_msg = f"任务超时（{_TASK_TIMEOUT_SECONDS}s），已自动重试1次仍失败，可能卡在下载或转写步骤"
                    conn.execute(
                        "UPDATE ingest_tasks SET status = 'error', error = ?, finished_at = datetime('now') WHERE id = ?",
                        (error_msg, task_id),
                    )
                    logger.error("Task %s timed out after %ds + 1 retry — permanent error", task_id, _TASK_TIMEOUT_SECONDS)
        return

    if pipeline_error is not None:
        error_msg = str(pipeline_error)[:500]
        with connect() as conn:
            conn.execute(
                "UPDATE ingest_tasks SET status = 'error', error = ?, finished_at = datetime('now') WHERE id = ?",
                (error_msg, task_id),
            )
        logger.exception("Task %s failed for event %s: %s", task_id, event_id, error_msg)
        return

    # Success
    with connect() as conn:
        conn.execute(
            "UPDATE ingest_tasks SET status = 'done', finished_at = datetime('now') WHERE id = ?",
            (task_id,),
        )
    # Cleanup pending file if any
    if content_path := payload.get("content_path"):
        Path(content_path).unlink(missing_ok=True)
    logger.info("Task %s completed for event %s", task_id, event_id)

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
            with connect() as conn:
                row = conn.execute(
                    "SELECT id FROM ingest_tasks WHERE status = 'pending' ORDER BY created_at LIMIT 1"
                ).fetchone()

            if row:
                _process_one(row["id"])
            else:
                # No pending tasks — idle, reset error counter
                idle_cycles += 1
                consecutive_errors = 0

                # Periodic recover_stuck: clean up orphaned processing events every 60s
                if idle_cycles % 30 == 0:
                    try:
                        with connect() as conn:
                            stuck = conn.execute(
                                "SELECT COUNT(*) FROM events WHERE status = 'processing'"
                            ).fetchone()[0]
                            if stuck:
                                conn.execute("UPDATE events SET status = 'pending' WHERE status = 'processing'")
                                logger.warning("Periodic cleanup: reset %d stuck processing event(s) → pending", stuck)
                    except Exception:
                        pass

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
    _shutdown_flag.clear()

    # Recover any tasks that were running when the server crashed
    recovered = recover_stuck()
    if recovered:
        logger.info("Recovered %d stuck task(s)", recovered)

    _worker = threading.Thread(target=_worker_loop, daemon=True, name="ingest-worker")
    _worker.start()


def stop_worker() -> None:
    """Signal the worker to stop and wait for graceful shutdown."""
    _shutdown_flag.set()
    if _worker and _worker.is_alive():
        _worker.join(timeout=10)
