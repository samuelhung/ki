"""SQLite persistence operations for the ingest task queue."""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
import uuid
from pathlib import Path

from .security.paths import safe_unlink_under


def _facade():
    from . import task_queue

    return task_queue


def safe_pending_unlink(path_value: str, pending_dir: Path, logger) -> None:
    try:
        safe_unlink_under(pending_dir, Path(path_value).expanduser())
    except Exception:
        logger.warning("Refusing to delete unsafe pending file", exc_info=True)


def compensate_failed_enqueue(event_id: str, task_id: str, connect_fn, logger) -> None:
    try:
        with connect_fn() as conn:
            conn.execute("DELETE FROM ingest_tasks WHERE id = ?", (task_id,))
            event = conn.execute(
                "SELECT status FROM events WHERE id = ?", (event_id,)
            ).fetchone()
            if event and event["status"] == "processing":
                survivor = conn.execute(
                    "SELECT 1 FROM ingest_tasks WHERE event_id = ? LIMIT 1",
                    (event_id,),
                ).fetchone()
                if not survivor:
                    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    except Exception:
        logger.exception("Failed to compensate enqueue failure for event %s", event_id)


def enqueue(event_id: str, ingest_type: str, content, topic: str, title: str) -> str:
    """Persist an ingest task using the facade's call-time dependencies."""
    q = _facade()
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    persistent: Path | None = None
    try:
        q.safe_identifier(event_id)
        q.init_db()
        if isinstance(content, Path):
            q.PENDING_DIR.mkdir(parents=True, exist_ok=True)
            persistent = q.resolve_under(
                q.PENDING_DIR, f"{event_id}{content.suffix}", must_exist=False
            )
            shutil.copy2(content, persistent)
            payload = {"content_path": str(persistent), "topic": topic, "title": title}
        else:
            payload = {"content_text": str(content), "topic": topic, "title": title}
        with q.connect() as conn:
            conn.execute(
                """INSERT INTO ingest_tasks (id, event_id, ingest_type, payload_json)
                   VALUES (?, ?, ?, ?)""",
                (
                    task_id,
                    event_id,
                    ingest_type,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
    except Exception:
        q.logger.exception("Failed to enqueue task for event %s", event_id)
        if persistent is not None:
            safe_pending_unlink(str(persistent), q.PENDING_DIR, q.logger)
        compensate_failed_enqueue(event_id, task_id, q.connect, q.logger)
        raise q.EnqueueError("任务无法加入处理队列") from None
    q.logger.info("Enqueued task %s for event %s (%s)", task_id, event_id, ingest_type)
    return task_id


def recover_stuck() -> int:
    """Recover running tasks using the facade's retry and logging contracts."""
    from .db import get_db_path

    q = _facade()
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    last_err = None
    for attempt in range(1, 4):
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=15000")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            cur = conn.execute(
                "UPDATE ingest_tasks SET status = 'pending', started_at = NULL "
                "WHERE status = 'running'"
            )
            conn.commit()
            count = cur.rowcount if hasattr(cur, "rowcount") else 0
            conn.close()
            if count:
                q.logger.warning(
                    "Recovered %d orphaned running task(s) → pending", count
                )
            return count
        except Exception as exc:
            last_err = exc
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            wait = min(2**attempt, 8)
            q.logger.warning(
                "recover_stuck attempt %d/3 failed (%s), retrying in %ds",
                attempt,
                exc,
                wait,
            )
            time.sleep(wait)
    q.logger.error("recover_stuck failed after 3 attempts: %s", last_err)
    return 0


def load_task(task_id: str, connect_fn):
    with connect_fn() as conn:
        return conn.execute(
            "SELECT event_id, ingest_type, payload_json FROM ingest_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()


def claim_pending(connect_fn) -> str | None:
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id FROM ingest_tasks WHERE status = 'pending' "
            "ORDER BY created_at LIMIT 1"
        ).fetchone()
        if not row:
            return None
        candidate = row["id"]
        cur = conn.execute(
            "UPDATE ingest_tasks SET status = 'running', "
            "started_at = datetime('now') WHERE id = ? AND status = 'pending'",
            (candidate,),
        )
        return candidate if cur.rowcount else None


def mark_running(task_id: str, connect_fn) -> None:
    with connect_fn() as conn:
        conn.execute(
            "UPDATE ingest_tasks SET status = 'running', "
            "started_at = datetime('now') WHERE id = ?",
            (task_id,),
        )


def mark_done(task_id: str, connect_fn, *, clear_error: bool = False) -> None:
    error_sql = ", error = NULL" if clear_error else ""
    with connect_fn() as conn:
        conn.execute(
            "UPDATE ingest_tasks SET status = 'done', finished_at = datetime('now')"
            f"{error_sql} WHERE id = ?",
            (task_id,),
        )


def mark_error(
    task_id: str,
    event_id: str,
    error: str,
    connect_fn,
    *,
    processing_only: bool = True,
) -> None:
    event_guard = " AND status = 'processing'" if processing_only else ""
    with connect_fn() as conn:
        conn.execute(
            "UPDATE ingest_tasks SET status = 'error', error = ?, "
            "finished_at = datetime('now') WHERE id = ?",
            (error, task_id),
        )
        conn.execute(
            "UPDATE events SET status = 'error', last_error = ? WHERE id = ?"
            f"{event_guard}",
            (error, event_id),
        )


def apply_timeout(
    task_id: str, event_id: str, error: str, connect_fn
) -> tuple[str, int]:
    """Apply timeout completion/retry/error and return the selected outcome."""
    with connect_fn() as conn:
        event = conn.execute(
            "SELECT status FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if event and event["status"] == "completed":
            conn.execute(
                "UPDATE ingest_tasks SET status = 'done', "
                "finished_at = datetime('now') WHERE id = ?",
                (task_id,),
            )
            return "done", 0
        retry = conn.execute(
            "SELECT COALESCE(retry_count, 0) FROM ingest_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        current = retry[0] if retry else 0
        if current < 1:
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
            return "retry", current
        conn.execute(
            "UPDATE ingest_tasks SET status = 'error', error = ?, "
            "finished_at = datetime('now') WHERE id = ?",
            (error, task_id),
        )
        conn.execute(
            "UPDATE events SET status = 'error', last_error = ? "
            "WHERE id = ? AND status = 'processing'",
            (error, event_id),
        )
        return "error", current


def restore_shutdown_interrupted_task(task_id: str, connect_fn) -> bool:
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT t.event_id, e.status AS event_status FROM ingest_tasks t "
            "JOIN events e ON e.id = t.event_id WHERE t.id = ?",
            (task_id,),
        ).fetchone()
        if not row:
            return False
        if row["event_status"] == "completed":
            cur = conn.execute(
                "UPDATE ingest_tasks SET status = 'done', "
                "finished_at = datetime('now'), error = NULL "
                "WHERE id = ? AND status = 'running'",
                (task_id,),
            )
            return bool(cur.rowcount)
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
        return bool(restored.rowcount)


def cleanup_stale_processing(connect_fn) -> int:
    with connect_fn() as conn:
        rows = conn.execute(
            """SELECT e.id FROM events e WHERE e.status = 'processing'
               AND NOT EXISTS (SELECT 1 FROM ingest_tasks t
                 WHERE t.event_id = e.id AND t.status = 'running')
               AND EXISTS (SELECT 1 FROM ingest_tasks t WHERE t.event_id = e.id
                 AND t.status IN ('pending', 'error', 'done')
                 AND COALESCE(t.started_at, t.created_at)
                     < datetime('now', '-1 hour'))"""
        ).fetchall()
        if not rows:
            return 0
        ids = [row["id"] for row in rows]
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE events SET status = 'pending' WHERE id IN ({placeholders})",
            ids,
        )
        return len(ids)
