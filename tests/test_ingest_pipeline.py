"""Tests for the ingest pipeline orchestration."""

from __future__ import annotations

import pytest

from zhiji_backend.db import connect, init_db
from zhiji_backend.ingest.pipeline import PIPELINES, Step
from zhiji_backend.routes import ingest_routes


def test_douyin_share_pipeline_steps():
    """Douyin share links go through full pipeline: parse → download → extract → upload → transcribe."""
    steps = PIPELINES["douyin_share"]
    assert steps == [
        Step.PARSE_DOUYIN,
        Step.DOWNLOAD_VIDEO,
        Step.EXTRACT_AUDIO,
        Step.UPLOAD_TOS,
        Step.TRANSCRIBE,
    ]


def test_video_file_pipeline_steps():
    """Local video files skip douyin parsing and video download."""
    steps = PIPELINES["video_file"]
    assert steps == [
        Step.EXTRACT_AUDIO,
        Step.UPLOAD_TOS,
        Step.TRANSCRIBE,
    ]


def test_audio_file_pipeline_steps():
    """Local audio files only need upload + transcribe."""
    steps = PIPELINES["audio_file"]
    assert steps == [
        Step.UPLOAD_TOS,
        Step.TRANSCRIBE,
    ]


def test_document_pipeline_steps():
    """Documents only need processing, no media steps."""
    steps = PIPELINES["document"]
    assert steps == [
        Step.PROCESS_DOC,
    ]


def test_unknown_type_raises():
    """Unknown ingest type should raise an error."""
    with __import__("pytest").raises(KeyError):
        _ = PIPELINES["unknown_type"]


def test_ingest_worker_persists_only_sanitized_error(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO sources (id, name, type, url, topic, priority)
               VALUES ('user-upload', '用户上传', 'manual', '', 'test', 'medium')"""
        )
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic,
               importance, actionability, decision, status, content_type)
               VALUES ('evt-ingest-secret', 'user-upload', '任务', '', 'test',
               4, 4, 'digest', 'processing', 'event')"""
        )

    ingest_type = "unsupported api_key=worker-secret /Users/alice/private.sql"
    with caplog.at_level("ERROR"), pytest.raises(ValueError):
        ingest_routes._process_ingest(
            "evt-ingest-secret", ingest_type, "prompt=private", "test", "title"
        )

    with connect() as conn:
        event = conn.execute(
            "SELECT status, last_error FROM events WHERE id = 'evt-ingest-secret'"
        ).fetchone()

    assert tuple(event) == ("error", "不支持的输入格式。")
    assert "worker-secret" not in caplog.text
    assert "/Users/alice/private.sql" not in caplog.text
    assert "private" not in caplog.text
