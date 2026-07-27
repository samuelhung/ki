"""Event CRUD, collection, summarization, tagging, similar, and classification endpoints."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from .. import event_ai_service as _ai
from .. import event_mutation_service as _mutation
from .. import event_query_service as _query
from ..classifier import classify_batch, classify_event
from ..collector import collect_once, fetch_url
from ..db import connect, seed_default_sources
from ..event_media import add_video_url, safe_unlink
from ..models import CollectRequest
from ..security.constraints import (
    MAX_OFFSET,
    MAX_PAGE_SIZE,
    SafeIdentifier,
    SafeIdentifierList,
    parse_bounded_identifier_csv,
)
from ..security.paths import resolve_under
from ..summarizer import summarize_transcript
from ..tagger import tag_event

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/events")
def list_events(
    topic: str | None = None,
    status: str | None = None,
    source_id: str | None = None,
    content_type: str | None = None,
    search: str | None = None,
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    count: int = 0,
) -> list[dict[str, object]] | dict[str, object]:
    try:
        return _query.list_events(
            topic,
            status,
            source_id,
            content_type,
            search,
            offset,
            limit,
            count,
            connect_fn=connect,
            parse_bounded_identifier_csv_fn=parse_bounded_identifier_csv,
        )
    except _query.InvalidSourceFilterError as exc:
        raise HTTPException(status_code=422, detail="Invalid source filter") from exc


@router.get("/api/events/topic-counts")
def event_topic_counts() -> dict[str, int]:
    """Return event counts per topic for content ingest tabs."""
    return _query.event_topic_counts(connect_fn=connect)


@router.get("/api/events/{event_id}")
def get_event(event_id: SafeIdentifier) -> dict[str, object]:
    """Get full event detail including complete transcript."""
    from ..paths import INGEST_ROOT as ingest_root

    try:
        return _query.get_event(
            event_id,
            connect_fn=connect,
            add_video_url_fn=add_video_url,
            ingest_root=ingest_root,
        )
    except _query.EventNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Event not found") from exc


@router.delete("/api/events/{event_id}")
def delete_event(event_id: SafeIdentifier) -> dict[str, object]:
    """Delete an event and its associated ingest files."""
    from ..paths import INGEST_ROOT as ingest_root

    try:
        return _mutation.delete_event(
            event_id,
            connect_fn=connect,
            safe_unlink_fn=safe_unlink,
            ingest_root=ingest_root,
        )
    except _mutation.EventNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Event not found") from exc


class EventBatchRequest(BaseModel):
    event_ids: SafeIdentifierList


@router.post("/api/events/batch-delete")
def batch_delete_events(payload: EventBatchRequest) -> dict[str, object]:
    """Delete multiple events and their associated ingest files."""
    from ..paths import INGEST_ROOT as ingest_root

    return _mutation.batch_delete_events(
        payload,
        connect_fn=connect,
        safe_unlink_fn=safe_unlink,
        ingest_root=ingest_root,
    )


@router.post("/api/events/{event_id}/summarize")
def summarize_event(
    event_id: SafeIdentifier,
    background_tasks: BackgroundTasks,
    force: bool = False,
) -> dict[str, object]:
    """Generate an AI summary for a douyin event using the Knowledge template.

    Set ?force=true to bypass the cache and regenerate from scratch.
    """
    from ..paths import INGEST_ROOT as ingest_root

    try:
        return _ai.summarize_event(
            event_id,
            background_tasks,
            force,
            connect_fn=connect,
            summarize_transcript_fn=summarize_transcript,
            resolve_under_fn=resolve_under,
            ingest_root=ingest_root,
            logger=logger,
        )
    except _ai.EventNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Event not found") from exc
    except _ai.EventHasNoTranscriptError as exc:
        raise HTTPException(
            status_code=400, detail="Event has no transcript content"
        ) from exc


@router.post("/api/collect")
def collect(request: CollectRequest) -> dict[str, object]:
    try:
        return _mutation.collect(
            request,
            seed_default_sources_fn=seed_default_sources,
            collect_once_fn=collect_once,
            fetch_url_fn=fetch_url,
        )
    except _mutation.EmptySourceIdsError as exc:
        raise HTTPException(
            status_code=400, detail="source_ids must not be empty"
        ) from exc


class TagRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)


@router.post("/api/events/{event_id}/tag")
def tag_single_event(event_id: SafeIdentifier) -> dict[str, object]:
    """Extract tags for a single event using AI NER."""
    try:
        return _ai.tag_single_event(
            event_id,
            connect_fn=connect,
            tag_event_fn=tag_event,
            json_module=json,
        )
    except _ai.EventNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Event not found") from exc


@router.post("/api/tag/batch")
def tag_batch(request: TagRequest | None = None) -> dict[str, object]:
    """Batch-tag untagged events (max N at a time)."""
    return _ai.tag_batch(
        request,
        connect_fn=connect,
        tag_event_fn=tag_event,
        json_module=json,
    )


@router.get("/api/events/{event_id}/similar")
def similar_events(
    event_id: SafeIdentifier,
    limit: int = Query(5, ge=1, le=MAX_PAGE_SIZE),
) -> list[dict[str, object]]:
    """Find events similar to the given event by FTS5 + title/content overlap."""
    try:
        return _query.similar_events(event_id, limit, connect_fn=connect)
    except _query.EventNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Event not found") from exc


@router.post("/api/classify/batch")
def batch_classify(
    source_ids: str | None = Query(None, max_length=12_900),
    limit: int = Query(100, ge=1, le=100),
) -> dict[str, int]:
    """Classify all unclassified non-RSS events into 4 cognitive layers."""
    try:
        return _ai.batch_classify(
            source_ids,
            limit,
            classify_batch_fn=classify_batch,
            parse_bounded_identifier_csv_fn=parse_bounded_identifier_csv,
        )
    except _ai.InvalidSourceFilterError as exc:
        raise HTTPException(status_code=422, detail="Invalid source filter") from exc


@router.post("/api/classify/event/{event_id}")
def classify_single(event_id: SafeIdentifier) -> dict[str, object]:
    """Classify a single event."""
    return _ai.classify_single(event_id, classify_event_fn=classify_event)
