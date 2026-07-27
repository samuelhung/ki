from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from zhiji_backend import paths as backend_paths
from zhiji_backend.db import connect, init_db
from zhiji_backend.main import app
from zhiji_backend.media_capability import verify_video_capability

TOKEN = "secret-token"
AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}"}
LEGACY_VIDEO_ROOT = (
    "/Users/mrh/Documents/Projects/KnowledgeIntelligence/data/ingest/videos"
)


def _insert_event(event_id: str, video_path: str) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO sources (id, name, type, url, topic, priority)
               VALUES ('user-upload', 'User upload', 'manual', '', 'test', 'medium')"""
        )
        conn.execute(
            """INSERT INTO events
               (id, source_id, title, url, topic, importance, actionability,
                decision, status, content_type, video_path)
               VALUES (?, 'user-upload', 'Video event', '', 'test', 1, 1,
                       'digest', 'completed', 'video', ?)""",
            (event_id, video_path),
        )


def _prepare_event(tmp_path, monkeypatch, *, event_id: str, video_path: str):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    monkeypatch.setenv("KI_API_TOKEN", TOKEN)
    ingest_root = tmp_path / "ingest"
    (ingest_root / "videos").mkdir(parents=True)
    monkeypatch.setattr(backend_paths, "INGEST_ROOT", ingest_root)
    init_db()
    _insert_event(event_id, video_path)
    client = TestClient(app, client=("10.8.0.2", 50000))
    return client, ingest_root


def test_event_detail_issues_signed_url_for_active_copy_of_legacy_video(
    tmp_path, monkeypatch
):
    filename = "evt-legacy.mp4"
    stored_path = f"{LEGACY_VIDEO_ROOT}/{filename}"
    client, ingest_root = _prepare_event(
        tmp_path,
        monkeypatch,
        event_id="evt-legacy",
        video_path=stored_path,
    )
    (ingest_root / "videos" / filename).write_bytes(b"video")

    response = client.get("/api/events/evt-legacy", headers=AUTH_HEADERS)

    assert response.status_code == 200
    detail = response.json()
    assert detail["video_path"] == stored_path
    assert LEGACY_VIDEO_ROOT not in detail["video_url"]
    assert TOKEN not in detail["video_url"]
    parts = urlsplit(detail["video_url"])
    query = parse_qs(parts.query)
    assert parts.path == f"/media/videos/{filename}"
    assert verify_video_capability(
        filename,
        expires=query["expires"][0],
        signature=query["signature"][0],
        api_token=TOKEN,
    )


@pytest.mark.parametrize(
    ("event_id", "filename", "create_kind"),
    [
        ("evt-missing", "missing.mp4", "missing"),
        ("evt-unsafe", "unsafe name.mp4", "regular"),
        ("evt-symlink", "linked.mp4", "symlink"),
    ],
)
def test_event_detail_omits_video_url_for_unavailable_or_unsafe_files(
    tmp_path, monkeypatch, event_id, filename, create_kind
):
    stored_path = f"{LEGACY_VIDEO_ROOT}/{filename}"
    client, ingest_root = _prepare_event(
        tmp_path,
        monkeypatch,
        event_id=event_id,
        video_path=stored_path,
    )
    video_file = ingest_root / "videos" / filename
    if create_kind == "regular":
        video_file.write_bytes(b"video")
    elif create_kind == "symlink":
        outside = tmp_path / "outside.mp4"
        outside.write_bytes(b"outside")
        video_file.symlink_to(outside)

    response = client.get(f"/api/events/{event_id}", headers=AUTH_HEADERS)

    assert response.status_code == 200
    detail = response.json()
    assert detail["video_path"] == stored_path
    assert "video_url" not in detail


def test_event_detail_omits_video_url_without_api_token(tmp_path, monkeypatch):
    filename = "evt-tokenless.mp4"
    stored_path = f"{LEGACY_VIDEO_ROOT}/{filename}"
    _, ingest_root = _prepare_event(
        tmp_path,
        monkeypatch,
        event_id="evt-tokenless",
        video_path=stored_path,
    )
    (ingest_root / "videos" / filename).write_bytes(b"video")
    monkeypatch.setenv("KI_API_TOKEN", "")
    client = TestClient(app)

    response = client.get("/api/events/evt-tokenless")

    assert response.status_code == 200
    detail = response.json()
    assert detail["video_path"] == stored_path
    assert "video_url" not in detail
