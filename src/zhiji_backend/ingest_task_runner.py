from __future__ import annotations

import json
import sys
from pathlib import Path

from .db import connect


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
    content = Path(payload["content_path"]) if payload.get("content_path") else payload.get("content_text", "")
    topic = payload.get("topic", "uncategorized")
    title = payload.get("title", "")

    from .routes.ingest_routes import _process_ingest

    _process_ingest(event_id, ingest_type, content, topic, title)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m zhiji_backend.ingest_task_runner <task_id>")
    run_task(sys.argv[1])
