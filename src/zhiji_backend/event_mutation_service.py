"""Event deletion and collection mutations for event route adapters."""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger("zhiji_backend.routes.event_routes")


class EventNotFoundError(LookupError):
    """Raised when an event mutation targets an unknown event."""


class EmptySourceIdsError(ValueError):
    """Raised when collection receives an explicitly empty source list."""


class EventBatchData(Protocol):
    event_ids: list[str]


class CollectData(Protocol):
    source_ids: list[str] | None


def _delete_artifacts(event_id, row, *, safe_unlink_fn, ingest_root) -> None:
    safe_unlink_fn(str(ingest_root / "transcripts" / f"{event_id}.md"), ingest_root)
    safe_unlink_fn(str(ingest_root / "summaries" / f"{event_id}.md"), ingest_root)
    for path_column in ("video_path", "audio_path", "document_path"):
        path = row[path_column]
        if path:
            safe_unlink_fn(str(path), ingest_root)


def _delete_event_record(conn, event_id: str):
    row = conn.execute(
        "SELECT id, video_path, audio_path, document_path FROM events WHERE id = ?",
        (event_id,),
    ).fetchone()
    if row is None:
        return None

    question_params = (event_id,)
    conn.execute(
        "DELETE FROM brainstorm_messages WHERE question_id IN "
        "(SELECT id FROM brainstorm_questions WHERE event_id = ?)",
        question_params,
    )
    conn.execute(
        "DELETE FROM brainstorm_contemplate_cache WHERE event_id = ? OR question_id IN "
        "(SELECT id FROM brainstorm_questions WHERE event_id = ?)",
        (event_id, event_id),
    )
    conn.execute(
        "DELETE FROM brainstorm_event_links WHERE event_id = ? OR question_id IN "
        "(SELECT id FROM brainstorm_questions WHERE event_id = ?)",
        (event_id, event_id),
    )
    conn.execute("DELETE FROM brainstorm_questions WHERE event_id = ?", question_params)
    conn.execute("DELETE FROM chain_data_hints WHERE event_id = ?", (event_id,))
    conn.execute("DELETE FROM chain_suggestions WHERE event_id = ?", (event_id,))
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    return row


def delete_event(
    event_id: str, *, connect_fn, safe_unlink_fn, ingest_root
) -> dict[str, object]:
    with connect_fn() as conn:
        row = _delete_event_record(conn, event_id)
    if row is None:
        raise EventNotFoundError

    _delete_artifacts(
        event_id, row, safe_unlink_fn=safe_unlink_fn, ingest_root=ingest_root
    )
    return {"ok": True, "deleted": event_id}


def batch_delete_events(
    payload: EventBatchData, *, connect_fn, safe_unlink_fn, ingest_root
) -> dict[str, object]:
    deleted = 0
    for event_id in payload.event_ids:
        with connect_fn() as conn:
            row = _delete_event_record(conn, event_id)
        if row is None:
            continue
        _delete_artifacts(
            event_id, row, safe_unlink_fn=safe_unlink_fn, ingest_root=ingest_root
        )
        deleted += 1
    return {"ok": True, "deleted": deleted}


def collect(
    request: CollectData, *, seed_default_sources_fn, collect_once_fn, fetch_url_fn
) -> dict[str, object]:
    if request.source_ids is not None and not request.source_ids:
        raise EmptySourceIdsError
    seed_default_sources_fn()
    return collect_once_fn(source_ids=request.source_ids, fetcher=fetch_url_fn)
