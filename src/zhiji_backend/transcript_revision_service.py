"""Append-only transcript revisions and compatibility artifact publication."""

from __future__ import annotations

import os
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from .security.constraints import safe_identifier
from .security.paths import PathSecurityError, resolve_under


class EventNotFoundError(LookupError):
    pass


class RevisionNotFoundError(LookupError):
    pass


class RevisionConflictError(RuntimeError):
    pass


class BodyCharacterMismatchError(ValueError):
    pass


class ManualRevisionRequiredError(ValueError):
    pass


@dataclass(frozen=True)
class TranscriptRevision:
    id: str
    event_id: str
    parent_revision_id: str | None
    source_revision_id: str | None
    kind: str
    content: str
    created_at: str


@dataclass(frozen=True)
class TranscriptState:
    event_id: str
    original_revision_id: str
    active_revision_id: str
    artifact_revision_id: str | None
    summary_revision_id: str | None
    active_kind: str
    active_content: str
    active_created_at: str

    @property
    def summary_stale(self) -> bool:
        return self.summary_revision_id != self.active_revision_id


@dataclass(frozen=True)
class ActivationResult:
    state: TranscriptState
    artifact_synced: bool


def body_sequence(value: str) -> str:
    return "".join(
        char
        for char in value
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def assert_same_body(source: str, candidate: str) -> None:
    if body_sequence(source) != body_sequence(candidate):
        raise BodyCharacterMismatchError("AI result changed transcript body characters")


def _revision(row) -> TranscriptRevision:
    return TranscriptRevision(
        id=row["id"],
        event_id=row["event_id"],
        parent_revision_id=row["parent_revision_id"],
        source_revision_id=row["source_revision_id"],
        kind=row["kind"],
        content=row["content"],
        created_at=row["created_at"],
    )


def _state_from_row(row) -> TranscriptState:
    return TranscriptState(
        event_id=row["event_id"],
        original_revision_id=row["original_revision_id"],
        active_revision_id=row["active_revision_id"],
        artifact_revision_id=row["artifact_revision_id"],
        summary_revision_id=row["summary_revision_id"],
        active_kind=row["active_kind"],
        active_content=row["active_content"],
        active_created_at=row["active_created_at"],
    )


def _load_state(conn, event_id: str) -> TranscriptState | None:
    row = conn.execute(
        """SELECT s.event_id, s.original_revision_id, s.active_revision_id,
                  s.artifact_revision_id, s.summary_revision_id,
                  r.kind AS active_kind, r.content AS active_content,
                  r.created_at AS active_created_at
           FROM transcript_revision_state s
           INNER JOIN transcript_revisions r ON r.id = s.active_revision_id
           WHERE s.event_id = ?""",
        (event_id,),
    ).fetchone()
    return _state_from_row(row) if row else None


def ensure_initialized(
    event_id: str,
    *,
    connect_fn,
    initial_content: str | None = None,
    artifact_published: bool = False,
    summary_published: bool | None = None,
) -> TranscriptState:
    safe_identifier(event_id)
    try:
        with connect_fn() as conn:
            state = _load_state(conn, event_id)
            if state is not None:
                return state
            event = conn.execute(
                "SELECT raw_summary, ai_summary FROM events WHERE id = ?", (event_id,)
            ).fetchone()
            if event is None:
                raise EventNotFoundError(event_id)
            legacy_content = event["raw_summary"] or ""
            content = legacy_content if initial_content is None else initial_content
            content_changed = initial_content is not None and content != legacy_content
            revision_id = f"tr-{uuid.uuid4().hex}"
            conn.execute(
                """INSERT INTO transcript_revisions
                   (id, event_id, kind, content) VALUES (?, ?, 'original', ?)""",
                (revision_id, event_id, content),
            )
            has_summary = (
                bool(event["ai_summary"]) and not content_changed
                if summary_published is None
                else summary_published
            )
            if initial_content is not None:
                conn.execute(
                    "UPDATE events SET raw_summary = ? WHERE id = ?",
                    (content, event_id),
                )
            conn.execute(
                """INSERT INTO transcript_revision_state
                   (event_id, original_revision_id, active_revision_id,
                    artifact_revision_id, summary_revision_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    event_id,
                    revision_id,
                    revision_id,
                    revision_id if artifact_published else None,
                    revision_id if has_summary else None,
                ),
            )
            state = _load_state(conn, event_id)
            assert state is not None
            return state
    except sqlite3.IntegrityError:
        with connect_fn() as conn:
            state = _load_state(conn, event_id)
        if state is not None:
            return state
        raise


def get_transcript(
    event_id: str, *, connect_fn, transcripts_dir: Path | None = None
) -> TranscriptState:
    state = ensure_initialized(event_id, connect_fn=connect_fn)
    if (
        transcripts_dir is not None
        and state.artifact_revision_id != state.active_revision_id
    ):
        if _publish_and_mark(
            state, connect_fn=connect_fn, transcripts_dir=transcripts_dir
        ):
            with connect_fn() as conn:
                refreshed = _load_state(conn, event_id)
                assert refreshed is not None
                return refreshed
    return state


def get_revision(event_id: str, revision_id: str, *, connect_fn) -> TranscriptRevision:
    safe_identifier(event_id)
    safe_identifier(revision_id)
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT * FROM transcript_revisions WHERE event_id = ? AND id = ?",
            (event_id, revision_id),
        ).fetchone()
    if row is None:
        raise RevisionNotFoundError(revision_id)
    return _revision(row)


def list_revisions(event_id: str, *, connect_fn) -> list[TranscriptRevision]:
    ensure_initialized(event_id, connect_fn=connect_fn)
    with connect_fn() as conn:
        rows = conn.execute(
            """SELECT * FROM transcript_revisions WHERE event_id = ?
               ORDER BY created_at DESC, rowid DESC""",
            (event_id,),
        ).fetchall()
    return [_revision(row) for row in rows]


def publish_transcript_artifact(
    event_id: str, content: str, *, transcripts_dir: Path
) -> None:
    safe_identifier(event_id)
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    target = resolve_under(transcripts_dir, f"{event_id}.md", must_exist=False)
    stage = resolve_under(
        transcripts_dir, f".{event_id}.{uuid.uuid4().hex}.tmp", must_exist=False
    )
    try:
        stage.write_text(content, encoding="utf-8")
        os.replace(stage, target)
    finally:
        if stage.exists():
            stage.unlink()


def _publish_and_mark(
    state: TranscriptState, *, connect_fn, transcripts_dir: Path
) -> bool:
    try:
        publish_transcript_artifact(
            state.event_id, state.active_content, transcripts_dir=transcripts_dir
        )
    except (OSError, PathSecurityError):
        return False
    try:
        with connect_fn() as conn:
            updated = conn.execute(
                """UPDATE transcript_revision_state SET artifact_revision_id = ?,
                   updated_at = CURRENT_TIMESTAMP
                   WHERE event_id = ? AND active_revision_id = ?""",
                (state.active_revision_id, state.event_id, state.active_revision_id),
            )
            if updated.rowcount != 1:
                conn.execute(
                    """UPDATE transcript_revision_state SET artifact_revision_id = NULL,
                       updated_at = CURRENT_TIMESTAMP
                       WHERE event_id = ? AND active_revision_id != ?""",
                    (state.event_id, state.active_revision_id),
                )
                return False
    except sqlite3.Error:
        return False
    return True


def _activate(
    event_id: str,
    content: str,
    base_revision_id: str,
    *,
    kind: str,
    connect_fn,
    transcripts_dir: Path | None,
    source_revision_id: str | None = None,
) -> ActivationResult:
    safe_identifier(event_id)
    safe_identifier(base_revision_id)
    revision_id = f"tr-{uuid.uuid4().hex}"
    with connect_fn() as conn:
        state = _load_state(conn, event_id)
        if state is None:
            raise EventNotFoundError(event_id)
        if state.active_revision_id != base_revision_id:
            raise RevisionConflictError(base_revision_id)
        conn.execute(
            """INSERT INTO transcript_revisions
               (id, event_id, parent_revision_id, source_revision_id, kind, content)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                revision_id,
                event_id,
                base_revision_id,
                source_revision_id,
                kind,
                content,
            ),
        )
        updated = conn.execute(
            """UPDATE transcript_revision_state
               SET active_revision_id = ?, updated_at = CURRENT_TIMESTAMP
               WHERE event_id = ? AND active_revision_id = ?""",
            (revision_id, event_id, base_revision_id),
        )
        if updated.rowcount != 1:
            raise RevisionConflictError(base_revision_id)
        conn.execute(
            "UPDATE events SET raw_summary = ? WHERE id = ?", (content, event_id)
        )
        state = _load_state(conn, event_id)
        assert state is not None
    synced = transcripts_dir is not None and _publish_and_mark(
        state,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )
    return ActivationResult(state=state, artifact_synced=synced)


def save_manual(
    event_id: str,
    content: str,
    base_revision_id: str,
    *,
    connect_fn,
    transcripts_dir: Path | None = None,
) -> ActivationResult:
    ensure_initialized(event_id, connect_fn=connect_fn)
    return _activate(
        event_id,
        content,
        base_revision_id,
        kind="manual",
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )


def activate_segmented(
    event_id: str,
    content: str,
    base_revision_id: str,
    *,
    connect_fn,
    transcripts_dir: Path | None = None,
) -> ActivationResult:
    state = get_transcript(event_id, connect_fn=connect_fn)
    if state.active_revision_id != base_revision_id:
        raise RevisionConflictError(base_revision_id)
    if state.active_kind != "manual":
        raise ManualRevisionRequiredError
    assert_same_body(state.active_content, content)
    return _activate(
        event_id,
        content,
        base_revision_id,
        kind="segmented",
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )


def restore_revision(
    event_id: str,
    source_revision_id: str,
    base_revision_id: str,
    *,
    connect_fn,
    transcripts_dir: Path | None = None,
) -> ActivationResult:
    source = get_revision(event_id, source_revision_id, connect_fn=connect_fn)
    return _activate(
        event_id,
        source.content,
        base_revision_id,
        kind="restored",
        source_revision_id=source_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )


def mark_summary_revision(event_id: str, revision_id: str, *, connect_fn) -> None:
    get_revision(event_id, revision_id, connect_fn=connect_fn)
    with connect_fn() as conn:
        conn.execute(
            """UPDATE transcript_revision_state SET summary_revision_id = ?,
               updated_at = CURRENT_TIMESTAMP WHERE event_id = ?""",
            (revision_id, event_id),
        )


def mark_artifact_revision(
    event_id: str,
    revision_id: str,
    *,
    connect_fn,
    transcripts_dir: Path,
) -> bool:
    revision = get_revision(event_id, revision_id, connect_fn=connect_fn)
    try:
        target = resolve_under(transcripts_dir, f"{event_id}.md", must_exist=True)
        if target.read_text(encoding="utf-8") != revision.content:
            return False
    except (OSError, PathSecurityError):
        return False
    with connect_fn() as conn:
        updated = conn.execute(
            """UPDATE transcript_revision_state SET artifact_revision_id = ?,
               updated_at = CURRENT_TIMESTAMP WHERE event_id = ?""",
            (revision_id, event_id),
        )
    return updated.rowcount == 1
