import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from backend.main import app
from backend.db import init_db, get_db_path


def test_health_endpoint_returns_ok():
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["service"] == "knowledge-intelligence"


def test_dashboard_bootstrap_summary_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    client = TestClient(app)

    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    payload = response.json()
    assert {"today_events", "high_priority_events", "sources_enabled"} == set(payload)
    assert payload["today_events"] == 0
    assert payload["high_priority_events"] == 0


def test_init_db_creates_sqlite_file(tmp_path, monkeypatch):
    db_path = tmp_path / "intelligence.sqlite"
    monkeypatch.setenv("KI_DB_PATH", str(db_path))

    init_db()

    assert get_db_path() == db_path
    assert db_path.exists()
