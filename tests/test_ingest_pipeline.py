"""Tests for the ingest pipeline orchestration."""

from __future__ import annotations

from zhiji_backend.ingest.pipeline import PIPELINES, Step


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
