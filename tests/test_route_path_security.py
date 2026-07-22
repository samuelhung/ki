from fastapi.testclient import TestClient

from zhiji_backend import paths as backend_paths
from zhiji_backend.db import connect, init_db
from zhiji_backend.main import app
from zhiji_backend.routes import brainstorm_routes, study_routes


def test_event_delete_does_not_follow_transcript_symlink(tmp_path, monkeypatch):
    ingest_root = tmp_path / "ingest"
    transcripts = ingest_root / "transcripts"
    summaries = ingest_root / "summaries"
    transcripts.mkdir(parents=True)
    summaries.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("keep", encoding="utf-8")
    (transcripts / "evt-symlink.md").symlink_to(outside)
    monkeypatch.setattr(backend_paths, "INGEST_ROOT", ingest_root)
    init_db()
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO sources (id, name, type, url, topic, priority)
               VALUES ('user-upload', '用户上传', 'manual', '', 'test', 'medium')"""
        )
        conn.execute(
            """INSERT OR REPLACE INTO events
               (id, source_id, title, url, topic, importance, actionability,
                decision, status, content_type)
               VALUES ('evt-symlink', 'user-upload', 'x', '', 'test', 1, 1,
                       'digest', 'completed', 'event')"""
        )

    response = TestClient(app).delete("/api/events/evt-symlink")

    assert response.status_code == 200
    assert outside.read_text(encoding="utf-8") == "keep"


def test_brainstorm_delete_does_not_follow_markdown_symlink(tmp_path, monkeypatch):
    brainstorm_root = tmp_path / "brainstorm"
    brainstorm_root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("keep", encoding="utf-8")
    (brainstorm_root / "question-symlink.md").symlink_to(outside)
    monkeypatch.setattr(brainstorm_routes, "BRAINSTORM_DIR", brainstorm_root)
    init_db()
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO brainstorm_questions (id, event_id, question)
               VALUES ('question-symlink', NULL, 'test')"""
        )

    response = TestClient(app).delete("/api/brainstorm/question-symlink")

    assert response.status_code == 200
    assert outside.read_text(encoding="utf-8") == "keep"


def test_study_file_route_rejects_symlinked_material_directory(tmp_path, monkeypatch):
    study_root = tmp_path / "study"
    outside = tmp_path / "outside"
    study_root.mkdir()
    outside.mkdir()
    (outside / "讲题稿版.md").write_text("outside", encoding="utf-8")
    (study_root / "study-symlink").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(study_routes, "STUDY_DATA_DIR", study_root)

    response = TestClient(app).get("/api/study/study-symlink/file/md")

    assert response.status_code == 404
    assert b"outside" not in response.content


def test_study_file_route_rejects_unknown_format_with_422():
    response = TestClient(app).get("/api/study/study-safe/file/executable")

    assert response.status_code == 422
