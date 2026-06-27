import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend.db import connect, init_db, seed_default_sources
from zhiji_backend.main import app


def test_generate_digest_api_creates_digest_and_candidates(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    monkeypatch.setenv("KI_WIKI_DIR", str(tmp_path / "wiki"))
    init_db()
    seed_default_sources()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO events (id, source_id, title, url, raw_summary, topic, importance, actionability, status)
            VALUES ('evt-api', 'bbc-technology', 'API digest item', 'https://example.com/api', 'API summary', 'tech-ai', 5, 4, 'new')
            """
        )
    client = TestClient(app)

    response = client.post("/api/digest/generate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["events_used"] == 1
    assert payload["action_candidates_created"] == 0
    assert "API digest item" in payload["markdown"] or "API digest" in payload["markdown"]


def test_digest_api_returns_latest_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    monkeypatch.setenv("KI_WIKI_DIR", str(tmp_path / "wiki"))
    init_db()
    seed_default_sources()
    client = TestClient(app)
    client.post("/api/digest/generate")

    response = client.get("/api/digest/latest")

    assert response.status_code == 200
    assert {"date", "markdown", "events_used", "action_candidates_created"}.issubset(response.json().keys())
