"""Tests for the unified ingest API endpoints."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend.main import app
from zhiji_backend.db import init_db, get_db_path

client = TestClient(app)


class TestDouyinIngest:
    @patch("zhiji_backend.routes.ingest_routes._process_ingest")
    def test_accepts_share_text_and_creates_event(self, mock_process):
        """POST /api/ingest/douyin creates a pending event and returns immediately."""
        response = client.post("/api/ingest/douyin", json={
            "share_text": "看看 https://v.douyin.com/abc123/ 有意思",
            "topic": "psychology",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"
        assert data["event_id"].startswith("evt-ingest-")
        assert data["type"] == "douyin_share"

    @patch("zhiji_backend.routes.ingest_routes._process_ingest")
    def test_event_appears_in_events_list(self, mock_process):
        """Created event should be visible in GET /api/events."""
        resp = client.post("/api/ingest/douyin", json={
            "share_text": "https://v.douyin.com/abc456/ test",
            "topic": "test",
        })
        event_id = resp.json()["event_id"]

        events_resp = client.get("/api/events")
        assert events_resp.status_code == 200
        events = events_resp.json()
        event_ids = [e["id"] for e in events]
        assert event_id in event_ids


class TestFileIngest:
    @patch("zhiji_backend.routes.ingest_routes._process_ingest")
    def test_accepts_document_upload(self, mock_process):
        """POST /api/ingest/file with type=document creates an event."""
        file_content = b"# Test Document\n\nHello World"
        response = client.post(
            "/api/ingest/file",
            data={"type": "document", "title": "测试文档", "topic": "test"},
            files={"file": ("test.md", io.BytesIO(file_content), "text/markdown")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"
        assert data["type"] == "document"

    @patch("zhiji_backend.routes.ingest_routes._process_ingest")
    def test_accepts_audio_file_upload(self, mock_process):
        """POST /api/ingest/file with type=audio_file creates an event."""
        file_content = b"fake audio data"
        response = client.post(
            "/api/ingest/file",
            data={"type": "audio_file", "title": "录音", "topic": "meeting"},
            files={"file": ("recording.wav", io.BytesIO(file_content), "audio/wav")},
        )

        assert response.status_code == 200
        assert response.json()["type"] == "audio_file"

    @patch("zhiji_backend.routes.ingest_routes._process_ingest")
    def test_accepts_video_file_upload(self, mock_process):
        """POST /api/ingest/file with type=video_file creates an event."""
        response = client.post(
            "/api/ingest/file",
            data={"type": "video_file", "title": "视频", "topic": "test"},
            files={"file": ("clip.mp4", b"fake video data", "video/mp4")},
        )

        assert response.status_code == 200
        assert response.json()["type"] == "video_file"


class TestIngestStatus:
    @patch("zhiji_backend.routes.ingest_routes._process_ingest")
    def test_status_returns_event_info(self, mock_process):
        """GET /api/ingest/status/{id} returns the event."""
        resp = client.post("/api/ingest/douyin", json={
            "share_text": "https://v.douyin.com/abc789/ test",
            "topic": "test",
        })
        event_id = resp.json()["event_id"]

        status_resp = client.get(f"/api/ingest/status/{event_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["id"] == event_id
        assert data["status"] in ("processing", "new", "error")

    def test_status_404_for_unknown_event(self):
        """Non-existent event returns 404."""
        resp = client.get("/api/ingest/status/evt-nonexistent")
        assert resp.status_code == 404
