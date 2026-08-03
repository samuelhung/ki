"""Contracts for the ingest application service extraction."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from zhiji_backend import db
from zhiji_backend import transcript_revision_service as transcript_revisions
from zhiji_backend.routes import ingest_routes


def _service():
    return importlib.import_module("zhiji_backend.ingest_service")


def test_service_detects_supported_types_and_hashes_files(tmp_path: Path):
    service = _service()
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"contract")

    assert service.detect_ingest_type("notes.PDF") == "document"
    assert service.detect_ingest_type("recording.OpUs") == "audio_file"
    assert service.detect_ingest_type("clip.MP4") == "video_file"
    assert service.detect_ingest_type("archive.zip") is None
    assert service.detect_ingest_type(None) is None
    assert service.md5_file(payload) == "800c327aefb3f9241513cbf551abbfda"
    assert service.md5_file(tmp_path / "missing") is None


def test_route_helper_facades_resolve_service_functions_at_call_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    service = _service()
    calls: list[tuple[str, tuple, dict]] = []
    sentinel = object()

    def replacement(name: str):
        def call(*args, **kwargs):
            calls.append((name, args, kwargs))
            return sentinel

        return call

    monkeypatch.setattr(service, "detect_ingest_type", replacement("detect"))
    monkeypatch.setattr(service, "md5_file", replacement("md5"))
    monkeypatch.setattr(service, "set_progress", replacement("progress"))
    monkeypatch.setattr(service, "create_event", replacement("event"))
    monkeypatch.setattr(service, "create_concept", replacement("concept"))
    monkeypatch.setattr(service, "process_ingest", replacement("process"))

    stages = [{"key": "parse"}]
    assert ingest_routes._detect_ingest_type("notes.txt") is sentinel
    assert ingest_routes._md5_file(tmp_path / "video.mp4") is sentinel
    assert ingest_routes._set_progress("evt-1", stages) is sentinel
    assert ingest_routes._create_event("document", "body", "topic") is sentinel
    assert ingest_routes._create_concept("Title", "topic") is sentinel
    assert (
        ingest_routes._process_ingest("evt-1", "document", "body", "topic", "Title")
        is sentinel
    )

    assert calls[0] == (
        "detect",
        ("notes.txt",),
        {"file_type_map": ingest_routes._FILE_TYPE_MAP},
    )
    assert calls[1] == ("md5", (tmp_path / "video.mp4",), {})
    assert calls[2] == (
        "progress",
        ("evt-1", stages),
        {"connect_fn": ingest_routes.connect},
    )
    assert calls[3] == (
        "event",
        ("document", "body", "topic", "", "event"),
        {
            "dependencies": {
                "init_db_fn": ingest_routes.init_db,
                "connect_fn": ingest_routes.connect,
                "enqueue_fn": ingest_routes.enqueue_task,
            }
        },
    )
    assert calls[4] == (
        "concept",
        ("Title", "topic", "", False, None),
        {
            "dependencies": {
                "init_db_fn": ingest_routes.init_db,
                "connect_fn": ingest_routes.connect,
                "ingest_root": ingest_routes.INGEST_ROOT,
                "logger": ingest_routes.logger,
            }
        },
    )
    assert calls[5] == (
        "process",
        ("evt-1", "document", "body", "topic", "Title"),
        {
            "dependencies": {
                "connect_fn": ingest_routes.connect,
                "transcripts_dir": ingest_routes.TRANSCRIPTS_DIR,
                "summaries_dir": ingest_routes.SUMMARIES_DIR,
                "videos_dir": ingest_routes.VIDEOS_DIR,
                "audio_dir": ingest_routes.AUDIO_DIR,
                "documents_dir": ingest_routes.DOCUMENTS_DIR,
                "resolve_under_fn": ingest_routes.resolve_under,
                "set_progress_fn": ingest_routes._set_progress,
                "md5_file_fn": ingest_routes._md5_file,
                "safe_identifier_fn": ingest_routes.safe_identifier,
                "sanitize_task_error_fn": ingest_routes.sanitize_task_error,
                "classify_task_error_fn": ingest_routes.classify_task_error,
                "logger": ingest_routes.logger,
                "module_name": ingest_routes.__name__,
            }
        },
    )


def test_route_facades_forward_monkeypatched_dependencies(
    monkeypatch: pytest.MonkeyPatch,
):
    service = _service()
    observed: dict[str, dict] = {}
    replacements = {
        "connect": object(),
        "init_db": object(),
        "enqueue_task": object(),
        "INGEST_ROOT": Path("/tmp/contract-ingest"),
        "TRANSCRIPTS_DIR": Path("/tmp/contract-transcripts"),
        "SUMMARIES_DIR": Path("/tmp/contract-summaries"),
        "VIDEOS_DIR": Path("/tmp/contract-videos"),
        "AUDIO_DIR": Path("/tmp/contract-audio"),
        "DOCUMENTS_DIR": Path("/tmp/contract-documents"),
        "resolve_under": object(),
        "safe_identifier": object(),
        "sanitize_task_error": object(),
        "classify_task_error": object(),
        "logger": object(),
    }
    for name, value in replacements.items():
        monkeypatch.setattr(ingest_routes, name, value)

    def capture_event(*_args, **kwargs):
        observed["event"] = kwargs

    def capture_concept(*_args, **kwargs):
        observed["concept"] = kwargs

    def capture_process(*_args, **kwargs):
        observed["process"] = kwargs

    monkeypatch.setattr(service, "create_event", capture_event)
    monkeypatch.setattr(service, "create_concept", capture_concept)
    monkeypatch.setattr(service, "process_ingest", capture_process)

    ingest_routes._create_event("document", "body", "topic")
    ingest_routes._create_concept("Title", "topic")
    ingest_routes._process_ingest("evt-1", "document", "body", "topic", "Title")

    assert observed["event"] == {
        "dependencies": {
            "init_db_fn": replacements["init_db"],
            "connect_fn": replacements["connect"],
            "enqueue_fn": replacements["enqueue_task"],
        }
    }
    assert observed["concept"] == {
        "dependencies": {
            "init_db_fn": replacements["init_db"],
            "connect_fn": replacements["connect"],
            "ingest_root": replacements["INGEST_ROOT"],
            "logger": replacements["logger"],
        }
    }
    assert observed["process"] == {
        "dependencies": {
            "connect_fn": replacements["connect"],
            "transcripts_dir": replacements["TRANSCRIPTS_DIR"],
            "summaries_dir": replacements["SUMMARIES_DIR"],
            "videos_dir": replacements["VIDEOS_DIR"],
            "audio_dir": replacements["AUDIO_DIR"],
            "documents_dir": replacements["DOCUMENTS_DIR"],
            "resolve_under_fn": replacements["resolve_under"],
            "set_progress_fn": ingest_routes._set_progress,
            "md5_file_fn": ingest_routes._md5_file,
            "safe_identifier_fn": replacements["safe_identifier"],
            "sanitize_task_error_fn": replacements["sanitize_task_error"],
            "classify_task_error_fn": replacements["classify_task_error"],
            "logger": replacements["logger"],
            "module_name": ingest_routes.__name__,
        }
    }


class _Connection:
    def __init__(self):
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, statement, values):
        self.executions.append((statement, values))


class _NameLessLogger:
    def __init__(self):
        self.errors = []

    def error(self, *args, **kwargs):
        self.errors.append((args, kwargs))


def test_process_error_log_preserves_facade_module_and_original_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    logger = _NameLessLogger()
    connection = _Connection()
    monkeypatch.setattr(ingest_routes, "logger", logger)
    monkeypatch.setattr(ingest_routes, "connect", lambda: connection)

    with pytest.raises(ValueError, match="Unknown ingest type: unsupported"):
        ingest_routes._process_ingest(
            "evt-contract", "unsupported", "body", "topic", "Title"
        )

    assert logger.errors == [
        (
            (
                _service()._ERROR_LOG,
                "zhiji_backend.routes.ingest_routes",
                "evt-contract",
                "ValueError",
                "unsupported_input",
            ),
            {},
        )
    ]
    assert connection.executions[-1][1] == (
        "不支持的输入格式。",
        "evt-contract",
    )


def test_degraded_log_uses_facade_module_not_injected_logger_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    source = tmp_path / "source.txt"
    source.write_text("body", encoding="utf-8")
    connection = _Connection()
    different_logger = logging.getLogger("different.ingest.logger")
    monkeypatch.setattr(ingest_routes, "logger", different_logger)
    monkeypatch.setattr(ingest_routes, "connect", lambda: connection)
    monkeypatch.setattr(ingest_routes, "TRANSCRIPTS_DIR", tmp_path / "transcripts")
    monkeypatch.setattr(ingest_routes, "SUMMARIES_DIR", tmp_path / "summaries")
    monkeypatch.setattr(ingest_routes, "DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr(
        "zhiji_backend.summarizer.summarize_transcript",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    monkeypatch.setattr(
        "zhiji_backend.classifier.classify_event", lambda _event_id: None
    )
    monkeypatch.setattr(
        _service(),
        "transcript_revision_service",
        SimpleNamespace(
            ensure_initialized=lambda *_args, **_kwargs: SimpleNamespace(
                active_revision_id="revision-1"
            ),
            mark_artifact_revision=lambda *_args, **_kwargs: True,
            mark_summary_revision=lambda *_args, **_kwargs: None,
        ),
    )

    with caplog.at_level(logging.WARNING, logger=different_logger.name):
        ingest_routes._process_ingest(
            "evt-contract", "document", source, "topic", "Title"
        )

    [record] = [
        record for record in caplog.records if record.msg == _service()._DEGRADED_LOG
    ]
    assert record.args == (
        "zhiji_backend.routes.ingest_routes",
        "evt-contract",
        "RuntimeError",
        "task_failed",
    )


@pytest.mark.parametrize(
    ("summary_result", "has_summary_lineage"),
    [
        ({"summary": "初始总结", "overview": "概览"}, True),
        (None, False),
    ],
)
def test_completed_ingest_creates_original_revision_and_exact_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    summary_result,
    has_summary_lineage: bool,
):
    service = _service()
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "ingest-revisions.sqlite"))
    db.init_db()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, url) VALUES (?, ?, ?, ?)",
            ("source", "Source", "manual", ""),
        )
        conn.execute(
            """INSERT INTO events
               (id, source_id, title, url, status, content_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("evt-ingest-test", "source", "Title", "", "processing", "event"),
        )

    source = tmp_path / "source.txt"
    source.write_text("上传内容", encoding="utf-8")
    stages = [{"key": "complete", "status": "pending"}]
    monkeypatch.setattr(
        service,
        "_document_content",
        lambda *_args, **_kwargs: ("新采集正文ABC123", "Title", stages, None),
    )
    monkeypatch.setattr(
        "zhiji_backend.summarizer.summarize_transcript",
        lambda *_args, **_kwargs: summary_result,
    )
    monkeypatch.setattr("zhiji_backend.classifier.classify_event", lambda _event: None)

    transcripts_dir = tmp_path / "transcripts"
    service.process_ingest(
        "evt-ingest-test",
        "document",
        source,
        "topic",
        "Title",
        dependencies={
            "connect_fn": db.connect,
            "transcripts_dir": transcripts_dir,
            "summaries_dir": tmp_path / "summaries",
            "videos_dir": tmp_path / "videos",
            "audio_dir": tmp_path / "audio",
            "documents_dir": tmp_path / "documents",
            "resolve_under_fn": lambda root, name, **_kwargs: root / name,
            "set_progress_fn": lambda _event, _stages: None,
            "md5_file_fn": lambda _path: None,
            "safe_identifier_fn": lambda value: value,
            "sanitize_task_error_fn": str,
            "classify_task_error_fn": lambda _exc: "task_failed",
            "logger": logging.getLogger("test.ingest.revisions"),
            "module_name": "test.ingest.revisions",
        },
    )

    state = transcript_revisions.get_transcript(
        "evt-ingest-test", connect_fn=db.connect
    )
    with db.connect() as conn:
        row = conn.execute(
            "SELECT raw_summary, ai_summary, status FROM events WHERE id = ?",
            ("evt-ingest-test",),
        ).fetchone()

    assert state.active_kind == "original"
    assert state.active_content == row["raw_summary"] == "新采集正文ABC123"
    assert state.original_revision_id == state.active_revision_id
    assert state.artifact_revision_id == state.active_revision_id
    assert (transcripts_dir / "evt-ingest-test.md").read_text(
        encoding="utf-8"
    ) == state.active_content
    assert (
        state.summary_revision_id == state.active_revision_id
    ) is has_summary_lineage
    assert bool(row["ai_summary"]) is has_summary_lineage
    assert row["status"] == "completed"


def test_completed_douyin_ingest_marks_every_progress_stage_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    service = _service()
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "douyin-progress.sqlite"))
    db.init_db()
    event_id = "evt-ingest-progress"
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, url) VALUES (?, ?, ?, ?)",
            ("douyin", "Douyin", "manual", ""),
        )
        conn.execute(
            """INSERT INTO events
               (id, source_id, title, url, status, content_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event_id, "douyin", "Title", "", "processing", "event"),
        )

    stages = service._stages(
        "parse:解析链接,download:下载视频,persist:保存视频,extract:提取音频,"
        "tos:上传 TOS,transcribe:语音转写,summarize:AI 总结,writedb:写入数据库,"
        "classify:自动分类,done:完成"
    )
    for index in range(6):
        stages[index]["status"] = "done"
    stages[6]["status"] = "active"
    monkeypatch.setattr(
        service,
        "_douyin_content",
        lambda *_args, **_kwargs: ("转写正文", "Title", stages, "video-md5"),
    )
    monkeypatch.setattr(
        "zhiji_backend.summarizer.summarize_transcript",
        lambda *_args, **_kwargs: {"summary": "总结", "overview": "概览"},
    )
    monkeypatch.setattr("zhiji_backend.classifier.classify_event", lambda _event: None)
    monkeypatch.setattr(
        service,
        "transcript_revision_service",
        SimpleNamespace(
            ensure_initialized=lambda *_args, **_kwargs: SimpleNamespace(
                active_revision_id="revision-1"
            ),
            mark_artifact_revision=lambda *_args, **_kwargs: True,
            mark_summary_revision=lambda *_args, **_kwargs: None,
        ),
    )

    progress_updates: list[list[dict]] = []
    service.process_ingest(
        event_id,
        "douyin_share",
        "share text",
        "topic",
        "Title",
        dependencies={
            "connect_fn": db.connect,
            "transcripts_dir": tmp_path / "transcripts",
            "summaries_dir": tmp_path / "summaries",
            "videos_dir": tmp_path / "videos",
            "audio_dir": tmp_path / "audio",
            "documents_dir": tmp_path / "documents",
            "resolve_under_fn": lambda root, name, **_kwargs: root / name,
            "set_progress_fn": lambda _event, value: progress_updates.append(
                [dict(stage) for stage in value]
            ),
            "md5_file_fn": lambda _path: None,
            "safe_identifier_fn": lambda value: value,
            "sanitize_task_error_fn": str,
            "classify_task_error_fn": lambda _exc: "task_failed",
            "logger": logging.getLogger("test.ingest.douyin-progress"),
            "module_name": "test.ingest.douyin-progress",
        },
    )

    assert progress_updates
    assert {stage["status"] for stage in progress_updates[-1]} == {"done"}
