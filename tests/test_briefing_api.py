import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend.db import connect, init_db
from zhiji_backend.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    return TestClient(app)


@pytest.fixture
def seeded_briefings(client):
    rows = [
        (
            "briefing-1",
            "quick",
            [{"topic": "认知", "events": [{"event_id": "event-1"}]}],
            1,
            "2026-07-18 08:00:00",
        ),
        (
            "briefing-2",
            "daily",
            [{"topic": "格局", "events": [{"event_id": "event-2"}]}],
            1,
            "2026-07-19 09:00:00",
        ),
        (
            "briefing-3",
            "quick",
            [
                {"topic": "财富", "events": [{"event_id": "event-3"}]},
                {"topic": "前瞻", "events": []},
            ],
            1,
            "2026-07-19 09:00:00",
        ),
    ]
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO briefings (id, type, topics_json, events_used, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (briefing_id, briefing_type, json.dumps(topics), events_used, created_at)
                for briefing_id, briefing_type, topics, events_used, created_at in rows
            ],
        )


def test_briefing_history_is_newest_first(client, seeded_briefings):
    response = client.get("/api/briefing?limit=2&offset=0")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == ["briefing-3", "briefing-2"]
    assert payload["total"] == 3
    assert set(payload["items"][0]) == {
        "id",
        "type",
        "events_used",
        "topic_count",
        "created_at",
    }
    assert payload["items"][0]["topic_count"] == 2
    assert "topics_json" not in payload["items"][0]


def test_briefing_history_clamps_pagination(client, seeded_briefings):
    response = client.get("/api/briefing?limit=0&offset=-5")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == ["briefing-3"]
    assert payload["total"] == 3


def test_briefing_detail_returns_topics(client, seeded_briefings):
    response = client.get("/api/briefing/briefing-2")

    assert response.status_code == 200
    assert response.json()["id"] == "briefing-2"
    assert response.json()["topics"][0]["topic"] == "格局"
    assert "topics_json" not in response.json()


def test_briefing_detail_returns_404(client):
    assert client.get("/api/briefing/missing").status_code == 404


def test_briefing_latest_route_remains_compatible(client, seeded_briefings):
    response = client.get("/api/briefing/latest?briefing_type=daily")

    assert response.status_code == 200
    assert response.json()["id"] == "briefing-2"
    assert response.json()["topics"][0]["topic"] == "格局"


def test_briefing_generate_rejects_unknown_type(client):
    response = client.post(
        "/api/briefing/generate",
        json={"type": "weekly", "limit": 80},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("limit", [0, 201])
def test_briefing_generate_rejects_out_of_range_limit(client, limit):
    response = client.post(
        "/api/briefing/generate",
        json={"type": "quick", "limit": limit},
    )

    assert response.status_code == 422
