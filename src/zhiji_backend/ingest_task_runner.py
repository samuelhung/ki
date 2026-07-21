from __future__ import annotations

import json
import sys
from pathlib import Path

from .db import connect
from .paths import INGEST_ROOT
from .security.paths import PathSecurityError, resolve_under
from .usage_writer import start_usage_writer, stop_usage_writer

PENDING_DIR = INGEST_ROOT / "pending"


def run_task(task_id: str) -> None:
    with connect() as conn:
        row = conn.execute(
            "SELECT event_id, ingest_type, payload_json FROM ingest_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

    if not row:
        raise SystemExit(f"task not found: {task_id}")

    event_id = row["event_id"]
    ingest_type = row["ingest_type"]
    payload = json.loads(row["payload_json"])
    if payload.get("content_path"):
        try:
            content = resolve_under(
                PENDING_DIR, Path(payload["content_path"]), expected="file"
            )
        except (PathSecurityError, TypeError, ValueError):
            raise SystemExit("invalid queued content path") from None
    else:
        content = payload.get("content_text", "")
    topic = payload.get("topic", "uncategorized")
    title = payload.get("title", "")

    from .routes.ingest_routes import _process_ingest

    _process_ingest(event_id, ingest_type, content, topic, title)


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: python -m zhiji_backend.ingest_task_runner <task_id>")
    start_usage_writer()
    try:
        run_task(args[0])
    finally:
        stop_usage_writer()


if __name__ == "__main__":
    main()
