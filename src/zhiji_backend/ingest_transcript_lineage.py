"""Initialize transcript revision lineage after a completed ingest."""

from __future__ import annotations


def initialize_ingest_transcript(
    event_id: str,
    content: str,
    *,
    has_summary: bool,
    transcript_service,
    connect_fn,
    transcripts_dir,
) -> None:
    state = transcript_service.ensure_initialized(
        event_id,
        connect_fn=connect_fn,
        initial_content=content,
        summary_published=False,
    )
    artifact_marked = transcript_service.mark_artifact_revision(
        event_id,
        state.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )
    if not artifact_marked:
        raise RuntimeError("transcript artifact publication was not verified")
    if has_summary:
        transcript_service.mark_summary_revision(
            event_id,
            state.active_revision_id,
            connect_fn=connect_fn,
        )
