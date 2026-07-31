from __future__ import annotations

import importlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from zhiji_backend import db
from zhiji_backend import transcript_revision_service as transcript_revisions


class Cursor:
    def __init__(self, *, row: Any = None, rows: list[Any] | None = None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


def test_list_events_preserves_filtered_query_and_count_order() -> None:
    service = importlib.import_module("zhiji_backend.event_query_service")
    trace: list[Any] = []
    parses: list[str | None] = []

    class Connection:
        def __init__(self, index: int):
            self.index = index

        def execute(self, sql, params=()):
            trace.append((self.index, sql, params))
            if self.index == 0:
                return Cursor(rows=[{"id": "event-1"}])
            return Cursor(row=(1,))

    connection_index = 0

    @contextmanager
    def connect_fn():
        nonlocal connection_index
        current = connection_index
        connection_index += 1
        trace.append(("enter", current))
        yield Connection(current)
        trace.append(("exit", current))

    def parse_ids(value):
        parses.append(value)
        return ["npr", "bbc"]

    result = service.list_events(
        "world",
        "new",
        "npr,bbc",
        "article",
        None,
        2,
        3,
        1,
        connect_fn=connect_fn,
        parse_bounded_identifier_csv_fn=parse_ids,
    )

    assert result == {"items": [{"id": "event-1"}], "total": 1}
    assert parses == ["npr,bbc", "npr,bbc"]
    assert trace == [
        ("enter", 0),
        (
            0,
            "SELECT id, source_id, title, url, published_at,\n"
            "       title_cn, summary_cn, translation_status, translation_error,\n"
            "       topic, importance, actionability, decision, status,\n"
            "       video_path, content_type, created_at\n"
            "FROM events\n"
            "WHERE 1=1\n"
            " AND topic = :topic AND status = :status AND source_id IN "
            "(:sid0,:sid1) AND content_type = :content_type ORDER BY created_at "
            "DESC, id DESC LIMIT :limit OFFSET :offset",
            {
                "topic": "world",
                "status": "new",
                "sid0": "npr",
                "sid1": "bbc",
                "content_type": "article",
                "limit": 3,
                "offset": 2,
            },
        ),
        ("exit", 0),
        ("enter", 1),
        (
            1,
            "SELECT COUNT(*) FROM events WHERE 1=1 AND topic = :topic AND "
            "status = :status AND content_type = :content_type AND source_id "
            "IN (:sid0,:sid1)",
            {
                "topic": "world",
                "status": "new",
                "content_type": "article",
                "sid0": "npr",
                "sid1": "bbc",
            },
        ),
        ("exit", 1),
    ]


def test_get_event_preserves_detail_queries_and_media_enrichment(
    tmp_path: Path,
) -> None:
    service = importlib.import_module("zhiji_backend.event_query_service")
    trace: list[Any] = []
    rows = iter(
        [
            Cursor(row={"id": "event-1", "video_path": "video.mp4"}),
            Cursor(rows=[{"id": "question-1"}]),
        ]
    )

    class Connection:
        def execute(self, sql, params=()):
            trace.append((sql, params))
            return next(rows)

    @contextmanager
    def connect_fn():
        yield Connection()

    def add_video_url(result, ingest_root):
        trace.append(("video", result, ingest_root))
        result["video_url"] = "/signed/video"

    result = service.get_event(
        "event-1",
        connect_fn=connect_fn,
        add_video_url_fn=add_video_url,
        ingest_root=tmp_path,
    )

    assert result["video_url"] == "/signed/video"
    assert result["transcript_path"] == str(tmp_path / "transcripts/event-1.md")
    assert result["summary_path"] == str(tmp_path / "summaries/event-1.md")
    assert result["associated_questions"] == [{"id": "question-1"}]
    assert trace[0] == (
        "SELECT id, source_id, title, url, published_at, raw_summary, ai_summary,\n"
        "               title_cn, summary_cn, translation_status, translation_error,\n"
        "               topic, importance, actionability, decision, status, tags_json,\n"
        "               last_error, progress_stages, video_path, created_at, overview, chain_analysis\n"
        "               FROM events WHERE id = ?",
        ("event-1",),
    )
    assert trace[-1] == (
        "SELECT bq.id, bq.question, bq.status, bq.created_at, "
        "(SELECT json_group_array(bel2.event_id) FROM brainstorm_event_links bel2 "
        "WHERE bel2.question_id = bq.id) as answered_event_ids FROM "
        "brainstorm_questions bq INNER JOIN brainstorm_event_links bel ON "
        "bel.question_id = bq.id WHERE bel.event_id = ? ORDER BY bq.created_at DESC",
        ("event-1",),
    )


def test_delete_event_preserves_safe_cleanup_and_database_order(tmp_path: Path) -> None:
    service = importlib.import_module("zhiji_backend.event_mutation_service")
    trace: list[Any] = []

    class Connection:
        def execute(self, sql, params=()):
            trace.append(("sql", sql, params))
            if sql.startswith("SELECT"):
                return Cursor(
                    row={
                        "id": "event-1",
                        "video_path": str(tmp_path / "video.mp4"),
                        "audio_path": None,
                        "document_path": str(tmp_path / "document.pdf"),
                    }
                )
            return Cursor()

    @contextmanager
    def connect_fn():
        trace.append("enter")
        yield Connection()
        trace.append("exit")

    result = service.delete_event(
        "event-1",
        connect_fn=connect_fn,
        safe_unlink_fn=lambda path, root: trace.append(("unlink", path, root)),
        ingest_root=tmp_path,
    )

    assert result == {"ok": True, "deleted": "event-1"}
    assert trace == [
        "enter",
        (
            "sql",
            "SELECT id, video_path, audio_path, document_path FROM events WHERE id = ?",
            ("event-1",),
        ),
        "exit",
        ("unlink", str(tmp_path / "transcripts/event-1.md"), tmp_path),
        ("unlink", str(tmp_path / "summaries/event-1.md"), tmp_path),
        ("unlink", str(tmp_path / "video.mp4"), tmp_path),
        ("unlink", str(tmp_path / "document.pdf"), tmp_path),
        "enter",
        ("sql", "DELETE FROM events WHERE id = ?", ("event-1",)),
        "exit",
    ]


def test_collect_preserves_validation_and_collector_arguments() -> None:
    service = importlib.import_module("zhiji_backend.event_mutation_service")
    trace: list[Any] = []
    request = SimpleNamespace(source_ids=["npr"])
    fetcher = object()

    result = service.collect(
        request,
        seed_default_sources_fn=lambda: trace.append("seed"),
        collect_once_fn=lambda **kwargs: trace.append(kwargs) or {"collected": 1},
        fetch_url_fn=fetcher,
    )

    assert result == {"collected": 1}
    assert trace == ["seed", {"source_ids": ["npr"], "fetcher": fetcher}]
    with pytest.raises(service.EmptySourceIdsError):
        service.collect(
            SimpleNamespace(source_ids=[]),
            seed_default_sources_fn=lambda: None,
            collect_once_fn=lambda **kwargs: {},
            fetch_url_fn=fetcher,
        )


def test_summarize_event_preserves_background_workflow_and_logger(
    tmp_path: Path,
) -> None:
    service = importlib.import_module("zhiji_backend.event_ai_service")
    trace: list[Any] = []
    connection_index = 0

    class Connection:
        def __init__(self, index):
            self.index = index

        def execute(self, sql, params=()):
            trace.append(("sql", self.index, sql, params))
            if self.index == 0:
                return Cursor(
                    row={
                        "id": "event-1",
                        "title": "Title",
                        "raw_summary": "Transcript",
                        "ai_summary": "Old",
                    }
                )
            return Cursor()

    @contextmanager
    def connect_fn():
        nonlocal connection_index
        current = connection_index
        connection_index += 1
        trace.append(("enter", current))
        yield Connection(current)
        trace.append(("exit", current))

    def resolve_under_fn(root, *parts, **kwargs):
        trace.append(("resolve", root, parts, kwargs))
        return root.joinpath(*parts)

    transcript_service = SimpleNamespace(
        ensure_initialized=lambda event_id, **_kwargs: SimpleNamespace(
            event_id=event_id,
            active_content="Transcript",
            active_revision_id="revision-1",
        ),
        mark_summary_revision=lambda event_id, revision_id, **_kwargs: trace.append(
            ("summary-revision", event_id, revision_id)
        ),
    )

    response, summary_task = service.summarize_event(
        "event-1",
        True,
        connect_fn=connect_fn,
        summarize_transcript_fn=lambda transcript, **kwargs: {
            "summary": "Summary",
            "overview": "Overview",
        },
        resolve_under_fn=resolve_under_fn,
        ingest_root=tmp_path,
        logger=service.logger,
        transcript_service=transcript_service,
    )
    assert response == {
        "event_id": "event-1",
        "status": "processing",
        "cached": False,
    }
    assert callable(summary_task)
    summary_task()

    sql = [entry for entry in trace if isinstance(entry, tuple) and entry[0] == "sql"]
    assert sql == [
        (
            "sql",
            0,
            "SELECT id, title, raw_summary, ai_summary FROM events WHERE id = ?",
            ("event-1",),
        ),
        (
            "sql",
            1,
            "UPDATE events SET ai_summary = ?, overview = COALESCE(?, overview) WHERE id = ?",
            ("Summary", "Overview", "event-1"),
        ),
    ]
    assert ("summary-revision", "event-1", "revision-1") in trace
    assert (tmp_path / "summaries/event-1.md").read_text() == "Summary"
    assert service.logger.name == "zhiji_backend.routes.event_routes"


def test_summary_lineage_uses_starting_revision_across_manual_edit_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = importlib.import_module("zhiji_backend.event_ai_service")
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "summary-lineage.sqlite"))
    db.init_db()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, url) VALUES (?, ?, ?, ?)",
            ("source", "Source", "manual", ""),
        )
        conn.execute(
            """INSERT INTO events
               (id, source_id, title, url, raw_summary, ai_summary, overview)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("evt-race", "source", "Title", "", "原始正文", "旧总结", "旧概览"),
        )

    response, run_summary = service.summarize_event(
        "evt-race",
        True,
        connect_fn=db.connect,
        summarize_transcript_fn=lambda transcript, **_kwargs: {
            "summary": f"新总结:{transcript}",
            "overview": "新概览",
        },
        resolve_under_fn=lambda root, *parts, **_kwargs: root.joinpath(*parts),
        ingest_root=tmp_path,
        logger=service.logger,
    )
    assert response["status"] == "processing"
    assert callable(run_summary)
    with db.connect() as conn:
        assert (
            conn.execute(
                "SELECT ai_summary FROM events WHERE id = 'evt-race'"
            ).fetchone()[0]
            == "旧总结"
        )

    original = transcript_revisions.get_transcript("evt-race", connect_fn=db.connect)
    manual = transcript_revisions.save_manual(
        "evt-race",
        "人工修正文",
        original.active_revision_id,
        connect_fn=db.connect,
        transcripts_dir=tmp_path / "transcripts",
    )
    run_summary()

    state = transcript_revisions.get_transcript("evt-race", connect_fn=db.connect)
    with db.connect() as conn:
        summary = conn.execute(
            "SELECT ai_summary FROM events WHERE id = 'evt-race'"
        ).fetchone()[0]
    assert state.summary_revision_id == original.active_revision_id
    assert state.active_revision_id == manual.state.active_revision_id
    assert state.summary_stale is True
    assert summary == "新总结:原始正文"


def test_summary_lineage_matches_active_revision_without_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = importlib.import_module("zhiji_backend.event_ai_service")
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "summary-current.sqlite"))
    db.init_db()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, url) VALUES (?, ?, ?, ?)",
            ("source", "Source", "manual", ""),
        )
        conn.execute(
            """INSERT INTO events
               (id, source_id, title, url, raw_summary)
               VALUES (?, ?, ?, ?, ?)""",
            ("evt-current", "source", "Title", "", "当前正文"),
        )

    _response, run_summary = service.summarize_event(
        "evt-current",
        True,
        connect_fn=db.connect,
        summarize_transcript_fn=lambda _text, **_kwargs: {
            "summary": "新总结",
            "overview": "概览",
        },
        resolve_under_fn=lambda root, *parts, **_kwargs: root.joinpath(*parts),
        ingest_root=tmp_path,
        logger=service.logger,
    )
    assert callable(run_summary)
    run_summary()

    state = transcript_revisions.get_transcript("evt-current", connect_fn=db.connect)
    assert state.summary_revision_id == state.active_revision_id
    assert state.summary_stale is False


def test_tag_and_classify_workflows_preserve_ai_arguments_and_json() -> None:
    service = importlib.import_module("zhiji_backend.event_ai_service")
    trace: list[Any] = []
    row = {
        "id": "event-1",
        "title": "Title",
        "title_cn": "标题",
        "raw_summary": "Raw",
        "ai_summary": "AI",
    }

    class Connection:
        def execute(self, sql, params=()):
            trace.append((sql, params))
            if sql.startswith("SELECT"):
                return Cursor(row=row)
            return Cursor()

    @contextmanager
    def connect_fn():
        yield Connection()

    result = service.tag_single_event(
        "event-1",
        connect_fn=connect_fn,
        tag_event_fn=lambda *args, **kwargs: trace.append((args, kwargs)) or ["tag"],
        json_module=json,
    )
    assert result == {"event_id": "event-1", "tags": ["tag"]}
    assert trace[-2:] == [
        (("Title", "AI"), {"title_cn": "标题"}),
        (
            "UPDATE events SET tags_json = ? WHERE id = ?",
            ('["tag"]', "event-1"),
        ),
    ]

    parsed: list[str | None] = []
    classified: list[Any] = []
    assert service.batch_classify(
        "npr,npr",
        7,
        classify_batch_fn=lambda **kwargs: classified.append(kwargs) or {"ok": 1},
        parse_bounded_identifier_csv_fn=lambda value: parsed.append(value) or ["npr"],
    ) == {"ok": 1}
    assert parsed == ["npr,npr"]
    assert classified == [{"source_ids": ["npr"], "limit": 7}]
    assert service.classify_single(
        "event-1", classify_event_fn=lambda event_id: "格局"
    ) == {"event_id": "event-1", "classified_as": "格局"}
