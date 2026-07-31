"""AI-backed event workflows for event route adapters."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from . import transcript_revision_service

logger = logging.getLogger("zhiji_backend.routes.event_routes")


class EventNotFoundError(LookupError):
    """Raised when an AI workflow targets an unknown event."""


class EventHasNoTranscriptError(ValueError):
    """Raised when summarization has no transcript content."""


class InvalidSourceFilterError(ValueError):
    """Raised when a classification source filter cannot be parsed safely."""


class TagData(Protocol):
    limit: int


def summarize_event(
    event_id: str,
    force: bool,
    *,
    connect_fn,
    summarize_transcript_fn,
    resolve_under_fn,
    ingest_root,
    logger,
    transcript_service=transcript_revision_service,
) -> tuple[dict[str, object], Callable[[], None] | None]:
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id, title, raw_summary, ai_summary FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()

    if row is None:
        raise EventNotFoundError

    state = transcript_service.ensure_initialized(event_id, connect_fn=connect_fn)
    title = row["title"] or ""
    transcript = state.active_content
    summary_input_revision_id = state.active_revision_id
    if not transcript.strip():
        raise EventHasNoTranscriptError
    if row["ai_summary"] and not force:
        return (
            {"event_id": event_id, "summary": row["ai_summary"], "cached": True},
            None,
        )

    def _run_summary():
        try:
            result = summarize_transcript_fn(transcript, title=title)
            if result:
                summary = result.get("summary", "")
                overview = result.get("overview", "")
                with connect_fn() as conn:
                    conn.execute(
                        "UPDATE events SET ai_summary = ?, overview = COALESCE(?, overview) WHERE id = ?",
                        (summary, overview, event_id),
                    )
                summaries_dir = resolve_under_fn(
                    ingest_root, "summaries", must_exist=False
                )
                summaries_dir.mkdir(parents=True, exist_ok=True)
                summaries_dir = resolve_under_fn(
                    ingest_root, "summaries", expected="dir"
                )
                summary_path = resolve_under_fn(
                    summaries_dir, f"{event_id}.md", must_exist=False
                )
                summary_path.write_text(summary, encoding="utf-8")
                transcript_service.mark_summary_revision(
                    event_id,
                    summary_input_revision_id,
                    connect_fn=connect_fn,
                )
                try:
                    from .chain_detector import detect_new_chains

                    detect_new_chains(event_id)
                except Exception:
                    logger.warning(
                        "detect_new_chains failed for %s during summarize",
                        event_id,
                        exc_info=True,
                    )
        except Exception as exc:
            logger.exception("Background summary failed for %s: %s", event_id, exc)

    return (
        {"event_id": event_id, "status": "processing", "cached": False},
        _run_summary,
    )


def tag_single_event(
    event_id: str, *, connect_fn, tag_event_fn, json_module
) -> dict[str, object]:
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id, title, title_cn, raw_summary, ai_summary FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
    if not row:
        raise EventNotFoundError

    title = row["title"] or ""
    title_cn = row["title_cn"]
    text = row["ai_summary"] or row["raw_summary"] or ""
    tags = tag_event_fn(title, text, title_cn=title_cn)
    with connect_fn() as conn:
        conn.execute(
            "UPDATE events SET tags_json = ? WHERE id = ?",
            (json_module.dumps(tags, ensure_ascii=False), event_id),
        )
    return {"event_id": event_id, "tags": tags}


def tag_batch(
    request: TagData | None, *, connect_fn, tag_event_fn, json_module
) -> dict[str, object]:
    limit = request.limit if request else 50
    with connect_fn() as conn:
        rows = conn.execute(
            """SELECT id, title, title_cn, raw_summary, ai_summary
               FROM events
               WHERE (tags_json IS NULL OR tags_json = '[]')
               AND raw_summary IS NOT NULL
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    tagged = 0
    failed = 0
    for row in rows:
        try:
            title = row["title"] or ""
            title_cn = row["title_cn"]
            text = row["ai_summary"] or row["raw_summary"] or ""
            tags = tag_event_fn(title, text, title_cn=title_cn)
            with connect_fn() as conn:
                conn.execute(
                    "UPDATE events SET tags_json = ? WHERE id = ?",
                    (json_module.dumps(tags, ensure_ascii=False), row["id"]),
                )
            tagged += 1
        except Exception:
            failed += 1
    return {"tagged": tagged, "failed": failed, "total_pending": len(rows)}


def batch_classify(
    source_ids: str | None,
    limit: int,
    *,
    classify_batch_fn,
    parse_bounded_identifier_csv_fn,
) -> dict[str, int]:
    try:
        ids = parse_bounded_identifier_csv_fn(source_ids)
    except ValueError as exc:
        raise InvalidSourceFilterError from exc
    return classify_batch_fn(source_ids=ids, limit=limit)


def classify_single(event_id: str, *, classify_event_fn) -> dict[str, object]:
    result = classify_event_fn(event_id)
    return {"event_id": event_id, "classified_as": result}
