"""Event-scoped transcript revision and semantic segmentation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from pydantic import BaseModel, Field

from .. import ai_client
from .. import transcript_revision_service as revisions
from .. import transcript_segmentation_service as segmentation
from ..db import connect
from ..paths import INGEST_ROOT
from ..security.constraints import SafeIdentifier

router = APIRouter()
TRANSCRIPTS_DIR = INGEST_ROOT / "transcripts"
chat = ai_client.chat


class ManualTranscriptRequest(BaseModel):
    content: str = Field(max_length=2_000_000)
    base_revision_id: SafeIdentifier


class RevisionBaseRequest(BaseModel):
    base_revision_id: SafeIdentifier


class RestoreTranscriptRequest(BaseModel):
    base_revision_id: SafeIdentifier


def _revision_meta(revision: revisions.TranscriptRevision) -> dict[str, object]:
    return {
        "id": revision.id,
        "kind": revision.kind,
        "parent_revision_id": revision.parent_revision_id,
        "source_revision_id": revision.source_revision_id,
        "created_at": revision.created_at,
    }


def _snapshot(
    state: revisions.TranscriptState, *, artifact_synced: bool | None = None
) -> dict[str, object]:
    history = revisions.list_revisions(state.event_id, connect_fn=connect)
    active = next(item for item in history if item.id == state.active_revision_id)
    return {
        "event_id": state.event_id,
        "content": state.active_content,
        "active_revision": _revision_meta(active),
        "revisions": [_revision_meta(item) for item in history],
        "can_segment": state.active_kind == "manual",
        "summary_stale": state.summary_stale,
        "artifact_synced": (
            state.artifact_revision_id == state.active_revision_id
            if artifact_synced is None
            else artifact_synced
        ),
    }


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, revisions.EventNotFoundError):
        raise HTTPException(status_code=404, detail="Event not found") from exc
    if isinstance(exc, revisions.RevisionNotFoundError):
        raise HTTPException(status_code=404, detail="Revision not found") from exc
    if isinstance(exc, segmentation.TaskNotFoundError):
        raise HTTPException(status_code=404, detail="Task not found") from exc
    if isinstance(exc, segmentation.TaskExpiredError):
        raise HTTPException(status_code=410, detail="Task expired") from exc
    if isinstance(exc, revisions.RevisionConflictError):
        raise HTTPException(status_code=409, detail="Transcript changed") from exc
    if isinstance(exc, segmentation.TaskNotReadyError):
        raise HTTPException(status_code=409, detail="Task is not ready") from exc
    if isinstance(exc, revisions.ManualRevisionRequiredError):
        raise HTTPException(
            status_code=422, detail="Manual transcript revision required"
        ) from exc
    if isinstance(exc, revisions.BodyCharacterMismatchError):
        raise HTTPException(
            status_code=422, detail="Segmentation changed body characters"
        ) from exc
    raise exc


@router.get("/api/events/{event_id}/transcript")
def get_transcript(event_id: SafeIdentifier) -> dict[str, object]:
    try:
        state = revisions.get_transcript(
            event_id, connect_fn=connect, transcripts_dir=TRANSCRIPTS_DIR
        )
        return _snapshot(state)
    except Exception as exc:
        _raise_http(exc)
        raise


@router.get("/api/events/{event_id}/transcript/revisions/{revision_id}")
def get_revision(
    event_id: SafeIdentifier, revision_id: SafeIdentifier
) -> dict[str, object]:
    try:
        revision = revisions.get_revision(event_id, revision_id, connect_fn=connect)
        return {
            **_revision_meta(revision),
            "event_id": event_id,
            "content": revision.content,
        }
    except Exception as exc:
        _raise_http(exc)
        raise


@router.put("/api/events/{event_id}/transcript/manual")
def save_manual(
    event_id: SafeIdentifier,
    payload: ManualTranscriptRequest,
    response: Response,
) -> dict[str, object]:
    try:
        result = revisions.save_manual(
            event_id,
            payload.content,
            payload.base_revision_id,
            connect_fn=connect,
            transcripts_dir=TRANSCRIPTS_DIR,
        )
        if not result.artifact_synced:
            response.status_code = status.HTTP_202_ACCEPTED
        return _snapshot(result.state, artifact_synced=result.artifact_synced)
    except Exception as exc:
        _raise_http(exc)
        raise


@router.post(
    "/api/events/{event_id}/transcript/segment",
    status_code=status.HTTP_202_ACCEPTED,
)
def start_segmentation(
    event_id: SafeIdentifier,
    payload: RevisionBaseRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, object]:
    try:
        state = revisions.get_transcript(event_id, connect_fn=connect)
        if state.active_revision_id != payload.base_revision_id:
            raise revisions.RevisionConflictError(payload.base_revision_id)
        if state.active_kind != "manual":
            raise revisions.ManualRevisionRequiredError
        task = segmentation.create_task(
            None,
            event_id,
            payload.base_revision_id,
            state.active_content,
        )
        background_tasks.add_task(segmentation.run_task, task.id, chat_fn=chat)
        return _task_payload(task)
    except Exception as exc:
        _raise_http(exc)
        raise


def _task_for_event(event_id: str, task_id: str) -> segmentation.SegmentationTask:
    task = segmentation.get_task(task_id)
    if task.event_id != event_id:
        raise segmentation.TaskNotFoundError(task_id)
    return task


def _task_payload(task: segmentation.SegmentationTask) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": task.id,
        "status": task.status,
        "base_revision_id": task.base_revision_id,
        "completed_chunks": task.completed_chunks,
        "total_chunks": task.total_chunks,
    }
    if task.status in {"ready", "confirmed"}:
        payload["preview"] = task.preview
    if task.status == "failed":
        payload["error_code"] = task.error_code
    if task.confirmed_revision_id is not None:
        payload["confirmed_revision_id"] = task.confirmed_revision_id
    return payload


@router.get("/api/events/{event_id}/transcript/segment/{task_id}")
def get_segmentation_status(
    event_id: SafeIdentifier, task_id: SafeIdentifier
) -> dict[str, object]:
    try:
        return _task_payload(_task_for_event(event_id, task_id))
    except Exception as exc:
        _raise_http(exc)
        raise


@router.post("/api/events/{event_id}/transcript/segment/{task_id}/confirm")
def confirm_segmentation(
    event_id: SafeIdentifier,
    task_id: SafeIdentifier,
    response: Response,
) -> dict[str, object]:
    try:
        task = _task_for_event(event_id, task_id)
        state = revisions.get_transcript(event_id, connect_fn=connect)
        activation: list[revisions.ActivationResult] = []

        def activate(preview: str, base_revision_id: str) -> str:
            result = revisions.activate_segmented(
                event_id,
                preview,
                base_revision_id,
                connect_fn=connect,
                transcripts_dir=TRANSCRIPTS_DIR,
            )
            activation.append(result)
            return result.state.active_revision_id

        confirmed_id = segmentation.mark_confirmed(
            task.id,
            active_revision_id=state.active_revision_id,
            confirm_fn=activate,
        )
        current = revisions.get_transcript(event_id, connect_fn=connect)
        artifact_synced = (
            activation[0].artifact_synced
            if activation
            else current.artifact_revision_id == current.active_revision_id
        )
        if not artifact_synced:
            response.status_code = status.HTTP_202_ACCEPTED
        return {
            **_snapshot(current, artifact_synced=artifact_synced),
            "confirmed_revision_id": confirmed_id,
        }
    except Exception as exc:
        _raise_http(exc)
        raise


@router.post("/api/events/{event_id}/transcript/revisions/{revision_id}/restore")
def restore_revision(
    event_id: SafeIdentifier,
    revision_id: SafeIdentifier,
    payload: RestoreTranscriptRequest,
    response: Response,
) -> dict[str, object]:
    try:
        result = revisions.restore_revision(
            event_id,
            revision_id,
            payload.base_revision_id,
            connect_fn=connect,
            transcripts_dir=TRANSCRIPTS_DIR,
        )
        if not result.artifact_synced:
            response.status_code = status.HTTP_202_ACCEPTED
        return _snapshot(result.state, artifact_synced=result.artifact_synced)
    except Exception as exc:
        _raise_http(exc)
        raise
