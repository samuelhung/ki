from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from threading import Barrier, Event, Lock

import pytest

from zhiji_backend import db
from zhiji_backend import transcript_revision_service as service


@pytest.fixture
def transcript_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "transcripts.sqlite"))
    db.init_db()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, url) VALUES (?, ?, ?, ?)",
            ("source", "Source", "manual", ""),
        )
        conn.execute(
            "INSERT INTO events (id, source_id, title, url, raw_summary, ai_summary) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("evt-1", "source", "Title", "", "原始文本ABC123🙂", "旧总结"),
        )
    return db.connect, tmp_path / "transcripts"


@pytest.mark.parametrize(
    "candidate",
    [
        "你好，世界！\n\n第二段。ABC 123🙂",
        "你好世界。\n第二段；ABC 123🙂",
    ],
)
def test_body_sequence_allows_only_punctuation_and_whitespace(candidate: str):
    service.assert_same_body("你好世界第二段ABC123🙂", candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        "您好世界第二段ABC123🙂",
        "你好世界第二段abc123🙂",
        "你好世界第二段ABC124🙂",
        "世界你好第二段ABC123🙂",
    ],
)
def test_body_sequence_rejects_body_changes(candidate: str):
    with pytest.raises(service.BodyCharacterMismatchError):
        service.assert_same_body("你好世界第二段ABC123🙂", candidate)


def test_lazy_initialization_uses_legacy_text_and_summary_lineage(transcript_db):
    connect_fn, _ = transcript_db

    state = service.ensure_initialized("evt-1", connect_fn=connect_fn)

    assert state.active_kind == "original"
    assert state.active_content == "原始文本ABC123🙂"
    assert state.original_revision_id == state.active_revision_id
    assert state.summary_revision_id == state.active_revision_id
    assert state.summary_stale is False


def test_list_revisions_lazily_initializes_historical_event(transcript_db):
    connect_fn, _ = transcript_db

    revisions = service.list_revisions("evt-1", connect_fn=connect_fn)

    assert len(revisions) == 1
    assert revisions[0].kind == "original"
    assert revisions[0].content == "原始文本ABC123🙂"


def test_lazy_initialization_is_idempotent_under_concurrent_first_reads(transcript_db):
    connect_fn, _ = transcript_db
    barrier = Barrier(2)
    winner_done = Event()
    rank_lock = Lock()
    next_rank = 0

    class SynchronizedConnection:
        def __init__(self, conn, rank: int):
            self._conn = conn
            self._rank = rank
            self._synchronized = False

        def execute(self, sql, parameters=()):
            cursor = self._conn.execute(sql, parameters)
            if (
                self._rank < 2
                and not self._synchronized
                and "FROM transcript_revision_state" in sql
            ):
                self._synchronized = True
                barrier.wait(timeout=2)
                if self._rank == 1:
                    assert winner_done.wait(timeout=2)
            return cursor

    @contextmanager
    def synchronized_connect():
        nonlocal next_rank
        with rank_lock:
            rank = next_rank
            next_rank += 1
        proxy = None
        try:
            with connect_fn() as conn:
                proxy = SynchronizedConnection(conn, rank)
                yield proxy
        finally:
            if proxy is not None and rank == 0:
                winner_done.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        states = list(
            executor.map(
                lambda _: service.ensure_initialized(
                    "evt-1", connect_fn=synchronized_connect
                ),
                range(2),
            )
        )

    assert states[0].original_revision_id == states[1].original_revision_id
    assert states[0].active_revision_id == states[1].active_revision_id
    with connect_fn() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM transcript_revisions WHERE event_id = 'evt-1'"
            ).fetchone()[0]
            == 1
        )


def test_lazy_initialization_respects_explicit_empty_content(transcript_db):
    connect_fn, _ = transcript_db

    state = service.ensure_initialized(
        "evt-1", connect_fn=connect_fn, initial_content=""
    )

    assert state.active_content == ""
    assert state.summary_revision_id is None
    assert state.summary_stale is True
    with connect_fn() as conn:
        assert (
            conn.execute(
                "SELECT raw_summary FROM events WHERE id = 'evt-1'"
            ).fetchone()[0]
            == ""
        )


def test_public_revision_values_are_immutable(transcript_db):
    connect_fn, _ = transcript_db
    state = service.ensure_initialized("evt-1", connect_fn=connect_fn)
    revision = service.get_revision(
        "evt-1", state.active_revision_id, connect_fn=connect_fn
    )

    with pytest.raises(FrozenInstanceError):
        state.active_content = "被修改"
    with pytest.raises(FrozenInstanceError):
        revision.content = "被修改"


def test_unchanged_manual_save_is_versioned_and_marks_summary_stale(transcript_db):
    connect_fn, transcripts_dir = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)

    result = service.save_manual(
        "evt-1",
        original.active_content,
        original.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )

    assert result.state.active_kind == "manual"
    assert result.state.active_revision_id != original.active_revision_id
    assert result.state.summary_stale is True
    assert result.artifact_synced is True
    assert (transcripts_dir / "evt-1.md").read_text(
        encoding="utf-8"
    ) == original.active_content
    with connect_fn() as conn:
        assert (
            conn.execute(
                "SELECT raw_summary FROM events WHERE id = 'evt-1'"
            ).fetchone()[0]
            == original.active_content
        )


def test_restore_appends_revision_without_mutating_history(transcript_db):
    connect_fn, transcripts_dir = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)
    manual = service.save_manual(
        "evt-1",
        "人工修正文ABC123🙂",
        original.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )

    restored = service.restore_revision(
        "evt-1",
        original.active_revision_id,
        manual.state.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )
    revisions = service.list_revisions("evt-1", connect_fn=connect_fn)

    assert [revision.kind for revision in revisions] == [
        "restored",
        "manual",
        "original",
    ]
    assert restored.state.active_content == original.active_content
    assert revisions[0].source_revision_id == original.active_revision_id
    assert revisions[1].content == "人工修正文ABC123🙂"
    assert revisions[2].content == "原始文本ABC123🙂"


def test_stale_base_rolls_back_candidate_revision(transcript_db):
    connect_fn, transcripts_dir = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)
    service.save_manual(
        "evt-1",
        "第一版ABC123🙂",
        original.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )

    with pytest.raises(service.RevisionConflictError):
        service.save_manual(
            "evt-1",
            "冲突版ABC123🙂",
            original.active_revision_id,
            connect_fn=connect_fn,
            transcripts_dir=transcripts_dir,
        )

    assert [
        item.content for item in service.list_revisions("evt-1", connect_fn=connect_fn)
    ] == [
        "第一版ABC123🙂",
        "原始文本ABC123🙂",
    ]


def test_raw_summary_failure_rolls_back_revision_and_state(transcript_db):
    connect_fn, transcripts_dir = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)
    with connect_fn() as conn:
        conn.execute(
            """CREATE TRIGGER reject_transcript_update
               BEFORE UPDATE OF raw_summary ON events
               WHEN NEW.raw_summary = '拒绝保存ABC123🙂'
               BEGIN
                   SELECT RAISE(ABORT, 'rejected transcript');
               END"""
        )

    with pytest.raises(sqlite3.IntegrityError, match="rejected transcript"):
        service.save_manual(
            "evt-1",
            "拒绝保存ABC123🙂",
            original.active_revision_id,
            connect_fn=connect_fn,
            transcripts_dir=transcripts_dir,
        )

    state = service.get_transcript("evt-1", connect_fn=connect_fn)
    assert state.active_revision_id == original.active_revision_id
    assert [
        item.kind for item in service.list_revisions("evt-1", connect_fn=connect_fn)
    ] == ["original"]


def test_segmented_activation_revalidates_body_characters(transcript_db):
    connect_fn, transcripts_dir = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)
    manual = service.save_manual(
        "evt-1",
        "你好世界ABC123🙂",
        original.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )

    with pytest.raises(service.BodyCharacterMismatchError):
        service.activate_segmented(
            "evt-1",
            "您好，世界。ABC123🙂",
            manual.state.active_revision_id,
            connect_fn=connect_fn,
            transcripts_dir=transcripts_dir,
        )


def test_segmented_activation_rejects_stale_manual_base(transcript_db):
    connect_fn, transcripts_dir = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)
    first_manual = service.save_manual(
        "evt-1",
        "第一版ABC123🙂",
        original.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )
    service.save_manual(
        "evt-1",
        "第二版ABC123🙂",
        first_manual.state.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )

    with pytest.raises(service.RevisionConflictError):
        service.activate_segmented(
            "evt-1",
            "第一版，ABC123🙂",
            first_manual.state.active_revision_id,
            connect_fn=connect_fn,
            transcripts_dir=transcripts_dir,
        )


def test_segmented_activation_requires_manual_revision(transcript_db):
    connect_fn, transcripts_dir = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)

    with pytest.raises(service.ManualRevisionRequiredError):
        service.activate_segmented(
            "evt-1",
            original.active_content,
            original.active_revision_id,
            connect_fn=connect_fn,
            transcripts_dir=transcripts_dir,
        )


def test_failed_artifact_publish_is_retried_on_read(transcript_db, monkeypatch):
    connect_fn, transcripts_dir = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)
    real_publish = service.publish_transcript_artifact
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("disk unavailable")
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(service, "publish_transcript_artifact", fail_once)
    saved = service.save_manual(
        "evt-1",
        "待同步ABC123🙂",
        original.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )
    refreshed = service.get_transcript(
        "evt-1", connect_fn=connect_fn, transcripts_dir=transcripts_dir
    )

    assert saved.artifact_synced is False
    assert refreshed.artifact_revision_id == refreshed.active_revision_id
    assert (transcripts_dir / "evt-1.md").read_text(
        encoding="utf-8"
    ) == "待同步ABC123🙂"


def test_path_security_publish_failure_keeps_committed_revision_unsynced(
    transcript_db, tmp_path: Path
):
    connect_fn, _ = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)
    actual_dir = tmp_path / "actual-transcripts"
    actual_dir.mkdir()
    unsafe_dir = tmp_path / "linked-transcripts"
    unsafe_dir.symlink_to(actual_dir, target_is_directory=True)

    saved = service.save_manual(
        "evt-1",
        "已提交但未发布ABC123🙂",
        original.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=unsafe_dir,
    )
    persisted = service.get_transcript("evt-1", connect_fn=connect_fn)

    assert saved.artifact_synced is False
    assert persisted.active_revision_id == saved.state.active_revision_id
    assert persisted.active_content == "已提交但未发布ABC123🙂"
    assert persisted.artifact_revision_id is None
    assert not (actual_dir / "evt-1.md").exists()


def test_artifact_marker_failure_keeps_committed_revision_unsynced(transcript_db):
    connect_fn, transcripts_dir = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)
    with connect_fn() as conn:
        conn.execute(
            """CREATE TRIGGER reject_artifact_marker
               BEFORE UPDATE OF artifact_revision_id ON transcript_revision_state
               WHEN NEW.artifact_revision_id IS NOT NULL
               BEGIN
                   SELECT RAISE(ABORT, 'rejected artifact marker');
               END"""
        )

    saved = service.save_manual(
        "evt-1",
        "正文已提交ABC123🙂",
        original.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )
    persisted = service.get_transcript("evt-1", connect_fn=connect_fn)

    assert saved.artifact_synced is False
    assert persisted.active_revision_id == saved.state.active_revision_id
    assert persisted.artifact_revision_id is None
    assert (transcripts_dir / "evt-1.md").read_text(
        encoding="utf-8"
    ) == "正文已提交ABC123🙂"


def test_late_stale_publish_invalidates_artifact_marker_and_read_repairs(transcript_db):
    connect_fn, transcripts_dir = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)
    first = service.save_manual(
        "evt-1",
        "第一版ABC123🙂",
        original.active_revision_id,
        connect_fn=connect_fn,
    )
    second = service.save_manual(
        "evt-1",
        "第二版ABC123🙂",
        first.state.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )

    assert (
        service._publish_and_mark(
            first.state, connect_fn=connect_fn, transcripts_dir=transcripts_dir
        )
        is False
    )
    stale = service.get_transcript("evt-1", connect_fn=connect_fn)
    assert stale.active_revision_id == second.state.active_revision_id
    assert stale.artifact_revision_id is None

    repaired = service.get_transcript(
        "evt-1", connect_fn=connect_fn, transcripts_dir=transcripts_dir
    )
    assert repaired.artifact_revision_id == second.state.active_revision_id
    assert (transcripts_dir / "evt-1.md").read_text(
        encoding="utf-8"
    ) == "第二版ABC123🙂"


def test_revision_markers_require_event_owned_revision(transcript_db):
    connect_fn, transcripts_dir = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)
    manual = service.save_manual(
        "evt-1",
        "人工修正ABC123🙂",
        original.active_revision_id,
        connect_fn=connect_fn,
    )

    assert manual.artifact_synced is False
    assert manual.state.artifact_revision_id != manual.state.active_revision_id

    service.mark_summary_revision(
        "evt-1", manual.state.active_revision_id, connect_fn=connect_fn
    )
    transcripts_dir.mkdir(parents=True)
    (transcripts_dir / "evt-1.md").write_text(original.active_content, encoding="utf-8")
    assert service.mark_artifact_revision(
        "evt-1",
        original.active_revision_id,
        connect_fn=connect_fn,
        transcripts_dir=transcripts_dir,
    )
    marked = service.get_transcript("evt-1", connect_fn=connect_fn)

    assert marked.summary_stale is False
    assert marked.artifact_revision_id == original.active_revision_id

    with connect_fn() as conn:
        conn.execute(
            "INSERT INTO events (id, source_id, title, url, raw_summary) "
            "VALUES (?, ?, ?, ?, ?)",
            ("evt-2", "source", "Other", "", "其他正文"),
        )
    foreign = service.ensure_initialized("evt-2", connect_fn=connect_fn)

    with pytest.raises(service.RevisionNotFoundError):
        service.mark_summary_revision(
            "evt-1", foreign.active_revision_id, connect_fn=connect_fn
        )
    with pytest.raises(service.RevisionNotFoundError):
        service.mark_artifact_revision(
            "evt-1",
            foreign.active_revision_id,
            connect_fn=connect_fn,
            transcripts_dir=transcripts_dir,
        )


def test_artifact_marker_requires_matching_published_content(transcript_db):
    connect_fn, transcripts_dir = transcript_db
    original = service.ensure_initialized("evt-1", connect_fn=connect_fn)

    assert (
        service.mark_artifact_revision(
            "evt-1",
            original.active_revision_id,
            connect_fn=connect_fn,
            transcripts_dir=transcripts_dir,
        )
        is False
    )

    transcripts_dir.mkdir(parents=True)
    (transcripts_dir / "evt-1.md").write_text("陈旧正文", encoding="utf-8")
    assert (
        service.mark_artifact_revision(
            "evt-1",
            original.active_revision_id,
            connect_fn=connect_fn,
            transcripts_dir=transcripts_dir,
        )
        is False
    )
    assert (
        service.get_transcript("evt-1", connect_fn=connect_fn).artifact_revision_id
        is None
    )


def test_unknown_event_and_foreign_revision_are_rejected(transcript_db):
    connect_fn, transcripts_dir = transcript_db
    with pytest.raises(service.EventNotFoundError):
        service.ensure_initialized("missing", connect_fn=connect_fn)

    state = service.ensure_initialized("evt-1", connect_fn=connect_fn)
    with pytest.raises(service.RevisionNotFoundError):
        service.restore_revision(
            "evt-1",
            "tr-missing",
            state.active_revision_id,
            connect_fn=connect_fn,
            transcripts_dir=transcripts_dir,
        )
