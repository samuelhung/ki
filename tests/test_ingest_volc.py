"""Tests for volc engine transcription (TOS upload + AUC API)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from ingest.volc_transcriber import (
    transcribe,
    submit_transcription,
    poll_result,
    upload_to_tos,
)


class TestSubmitTranscription:
    @patch("ingest.volc_transcriber.requests")
    def test_submit_returns_req_id_and_logid(self, mock_requests):
        """Successful submit returns request id and log id from headers."""
        resp = MagicMock()
        resp.headers = {
            "X-Api-Status-Code": "20000000",
            "X-Api-Message": "OK",
            "X-Tt-Logid": "test-logid-123",
        }
        mock_requests.post.return_value = resp

        req_id, logid = submit_transcription("https://example.com/audio.wav")

        assert req_id  # non-empty uuid
        assert logid == "test-logid-123"

    @patch("ingest.volc_transcriber.requests")
    def test_submit_raises_on_api_error(self, mock_requests):
        """Non-20000000 status should raise RuntimeError."""
        resp = MagicMock()
        resp.headers = {
            "X-Api-Status-Code": "45000030",
            "X-Api-Message": "resource not granted",
        }
        mock_requests.post.return_value = resp

        with pytest.raises(RuntimeError, match="45000030"):
            submit_transcription("https://example.com/audio.wav")


class TestPollResult:
    @patch("ingest.volc_transcriber.requests")
    @patch("ingest.volc_transcriber.time")
    def test_poll_returns_text_when_done(self, mock_time, mock_requests):
        """Poll returns transcription text when status is 20000000."""
        resp = MagicMock()
        resp.headers = {"X-Api-Status-Code": "20000000"}
        resp.json.return_value = {
            "result": {"text": "这是转写结果文本"}
        }
        mock_requests.post.return_value = resp
        # Don't actually sleep
        mock_time.sleep = lambda s: None

        text = poll_result("req-123", "logid-456", max_attempts=3)

        assert text == "这是转写结果文本"

    @patch("ingest.volc_transcriber.requests")
    @patch("ingest.volc_transcriber.time")
    def test_poll_retries_while_processing(self, mock_time, mock_requests):
        """Poll retries while status is 20000001 (processing)."""
        processing = MagicMock()
        processing.headers = {"X-Api-Status-Code": "20000001"}

        done = MagicMock()
        done.headers = {"X-Api-Status-Code": "20000000"}
        done.json.return_value = {"result": {"text": "final text"}}

        mock_requests.post.side_effect = [processing, processing, done]
        mock_time.sleep = lambda s: None

        text = poll_result("req-123", "logid-456", max_attempts=10)

        assert text == "final text"
        assert mock_requests.post.call_count == 3

    @patch("ingest.volc_transcriber.requests")
    @patch("ingest.volc_transcriber.time")
    def test_poll_raises_on_error_status(self, mock_time, mock_requests):
        """Unexpected error status raises RuntimeError."""
        resp = MagicMock()
        resp.headers = {"X-Api-Status-Code": "45000006"}
        mock_requests.post.return_value = resp
        mock_time.sleep = lambda s: None

        with pytest.raises(RuntimeError, match="45000006"):
            poll_result("req-123", "logid-456", max_attempts=3)

    @patch("ingest.volc_transcriber.requests")
    @patch("ingest.volc_transcriber.time")
    def test_poll_timeout_raises(self, mock_time, mock_requests):
        """Max attempts exceeded should raise TimeoutError."""
        resp = MagicMock()
        resp.headers = {"X-Api-Status-Code": "20000001"}  # always processing
        mock_requests.post.return_value = resp
        mock_time.sleep = lambda s: None

        with pytest.raises(TimeoutError, match="转写超时"):
            poll_result("req-123", "logid-456", max_attempts=2)


class TestTranscribeIntegration:
    @patch("ingest.volc_transcriber.upload_to_tos")
    @patch("ingest.volc_transcriber.submit_transcription")
    @patch("ingest.volc_transcriber.poll_result")
    def test_transcribe_orchestrates_full_flow(
        self, mock_poll, mock_submit, mock_upload, tmp_path: Path
    ):
        """transcribe() orchestrates upload → submit → poll."""
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake audio data")

        mock_upload.return_value = "https://tos.example.com/audio.wav"
        mock_submit.return_value = ("req-abc", "logid-def")
        mock_poll.return_value = "完整的转写结果"

        result = transcribe(audio)

        assert result == "完整的转写结果"
        mock_upload.assert_called_once_with(audio)
        mock_submit.assert_called_once_with("https://tos.example.com/audio.wav")
        mock_poll.assert_called_once_with("req-abc", "logid-def")
