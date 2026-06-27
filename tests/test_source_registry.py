import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend.db import connect, init_db, seed_default_sources
from zhiji_backend.main import app


def test_seed_default_sources_inserts_initial_rss_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()

    inserted = seed_default_sources()

    assert inserted >= 7
    with connect() as conn:
        rows = conn.execute("SELECT id, name, type, topic, priority, enabled FROM sources ORDER BY id").fetchall()
    names = {row["name"] for row in rows}
    assert "BBC World" in names
    assert "BBC Technology" in names
    assert "The Guardian" in names
    assert "NPR" in names
    assert "Al Jazeera" in names
    assert "NYT World" in names
    assert all(row["type"] == "rss" for row in rows)


def test_sources_api_returns_seeded_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    seed_default_sources()
    client = TestClient(app)

    response = client.get("/api/sources")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 7
    first = payload[0]
    assert {"id", "name", "type", "url", "topic", "priority", "enabled"}.issubset(first.keys())


def test_events_api_filters_by_status_and_topic(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    seed_default_sources()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO events (id, source_id, title, url, topic, importance, actionability, status)
            VALUES ('evt-1', 'bbc-technology', 'AI agent news', 'https://example.com/ai', 'tech-ai', 4, 3, 'new')
            """
        )
        conn.execute(
            """
            INSERT INTO events (id, source_id, title, url, topic, importance, actionability, status)
            VALUES ('evt-2', 'bbc-world', 'World news', 'https://example.com/world', 'world', 1, 0, 'archived')
            """
        )
    client = TestClient(app)

    response = client.get("/api/events?topic=tech-ai&status=new")

    assert response.status_code == 200
    assert response.json()[0]["id"] == "evt-1"
    assert len(response.json()) == 1


def test_dashboard_summary_counts_seeded_sources_and_events(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    seed_default_sources()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO events (id, source_id, title, url, topic, importance, actionability, status)
            VALUES ('evt-1', 'bbc-technology', 'AI agent news', 'https://example.com/ai', 'tech-ai', 4, 3, 'new')
            """
        )
    client = TestClient(app)

    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    assert response.json()["today_new"] == 0
    assert response.json()["ingest_total"] == 0
    assert response.json()["brainstorm_total"] == 0
    assert response.json()["sources_enabled"] >= 7
