"""Persistent ingest task queue — replaces FastAPI BackgroundTasks.

Tasks survive server restarts. A background worker thread polls for pending
tasks and executes them one at a time. Failed tasks record their error and
can be retried via the API.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from .db import connect, init_db

logger = logging.getLogger(__name__)

INGEST_ROOT = Path(__file__).resolve().parents[3] / "data" / "ingest"
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

    Returns count of recovered tasks.
    """
    init_db()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE ingest_tasks SET status = 'pending', started_at = NULL "
            "WHERE status = 'running'"
        )
        return cur.rowcount if hasattr(cur, "rowcount") else 0


def _process_one(task_id: str) -> None:
    """Process a single pending task."""
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

    try:
        from .routes.ingest_routes import _process_ingest
        _process_ingest(event_id, ingest_type, content, topic, title)
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
    except Exception as e:
        error_msg = str(e)[:500]
        with connect() as conn:
            conn.execute(
                "UPDATE ingest_tasks SET status = 'error', error = ?, finished_at = datetime('now') WHERE id = ?",
                (error_msg, task_id),
            )
        logger.exception("Task %s failed for event %s: %s", task_id, event_id, error_msg)


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
                consecutive_errors = 0
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
