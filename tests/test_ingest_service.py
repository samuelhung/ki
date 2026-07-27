"""Contracts for the ingest application service extraction."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

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
        }
    }
