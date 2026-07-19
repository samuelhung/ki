import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend import briefing as briefing_module
from zhiji_backend.briefing import list_briefings
from zhiji_backend.db import connect, init_db
from zhiji_backend.main import app

SQLITE_MAX_INTEGER = 9_223_372_036_854_775_807


def test_pytest_bootstrap_uses_isolated_data_home():
    test_home = Path(os.environ["ZHIJI_HOME"]).resolve()

    assert test_home.exists()
    assert test_home != (Path.home() / ".zhiji").resolve()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    test_client = TestClient(app, raise_server_exceptions=False)
    try:
        yield test_client
    finally:
        test_client.close()


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


def test_briefing_history_helper_clamps_pagination(client, seeded_briefings):
    payload = list_briefings(limit=0, offset=-5)

    assert [item["id"] for item in payload["items"]] == ["briefing-3"]
    assert payload["total"] == 3
    assert list_briefings(offset=SQLITE_MAX_INTEGER + 1)["items"] == []


@pytest.mark.parametrize("offset", [-1, SQLITE_MAX_INTEGER + 1])
def test_briefing_history_rejects_out_of_range_offset(client, offset):
    response = client.get(f"/api/briefing?offset={offset}")

    assert response.status_code == 422


def test_briefing_history_tolerates_invalid_topic_payloads(client):
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO briefings (id, type, topics_json, events_used, created_at)
            VALUES (?, 'quick', ?, 0, ?)
            """,
            [
                ("briefing-malformed", "{invalid", "2026-07-19 10:00:00"),
                ("briefing-object", json.dumps({"topic": "格局"}), "2026-07-19 11:00:00"),
            ],
        )

    response = client.get("/api/briefing")

    assert response.status_code == 200
    topic_counts = {item["id"]: item["topic_count"] for item in response.json()["items"]}
    assert topic_counts["briefing-malformed"] == 0
    assert topic_counts["briefing-object"] == 0


def test_briefing_detail_returns_topics(client, seeded_briefings):
    response = client.get("/api/briefing/briefing-2")

    assert response.status_code == 200
    assert response.json()["id"] == "briefing-2"
    assert response.json()["topics"][0]["topic"] == "格局"
    assert "topics_json" not in response.json()


@pytest.mark.parametrize(
    ("briefing_id", "topics_json"),
    [
        ("briefing-malformed", "{invalid"),
        ("briefing-object", json.dumps({"topic": "格局"})),
    ],
)
def test_briefing_detail_normalizes_invalid_topic_payloads(client, briefing_id, topics_json):
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO briefings (id, type, topics_json, events_used)
            VALUES (?, 'quick', ?, 0)
            """,
            (briefing_id, topics_json),
        )

    response = client.get(f"/api/briefing/{briefing_id}")

    assert response.status_code == 200
    assert response.json()["topics"] == []


@pytest.mark.parametrize(
    ("briefing_id", "topics_json", "expected_topics"),
    [
        ("briefing-null-topic", json.dumps([None]), []),
        (
            "briefing-null-event",
            json.dumps([{"topic": "格局", "events": [None]}]),
            [{"topic": "格局", "events": []}],
        ),
        (
            "briefing-object-events",
            json.dumps([{"topic": "格局", "events": {"event_id": "event-1"}}]),
            [{"topic": "格局", "events": []}],
        ),
    ],
)
def test_briefing_detail_normalizes_nested_topic_payloads(
    client,
    briefing_id,
    topics_json,
    expected_topics,
):
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO briefings (id, type, topics_json, events_used)
            VALUES (?, 'quick', ?, 0)
            """,
            (briefing_id, topics_json),
        )

    response = client.get(f"/api/briefing/{briefing_id}")

    assert response.status_code == 200
    assert response.json()["topics"] == expected_topics


@pytest.mark.parametrize(
    ("briefing_id", "event_id"),
    [
        ("briefing-list-event-id", ["event-1"]),
        ("briefing-null-event-id", None),
        ("briefing-empty-event-id", ""),
    ],
)
def test_briefing_detail_removes_invalid_event_ids(client, briefing_id, event_id):
    topics_json = json.dumps(
        [{"topic": "格局", "events": [{"event_id": event_id, "title_cn": "无效事件"}]}]
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO briefings (id, type, topics_json, events_used)
            VALUES (?, 'quick', ?, 0)
            """,
            (briefing_id, topics_json),
        )

    response = client.get(f"/api/briefing/{briefing_id}")

    assert response.status_code == 200
    assert response.json()["topics"] == [{"topic": "格局", "events": []}]


def test_parse_topics_json_does_not_mutate_decoded_input(monkeypatch):
    decoded = [{"topic": "格局", "events": [{"event_id": "event-1"}]}]
    monkeypatch.setattr(briefing_module.json, "loads", lambda _: decoded)

    topics = briefing_module._parse_topics_json("ignored")
    topics[0]["events"][0]["event_id"] = "changed"

    assert decoded == [{"topic": "格局", "events": [{"event_id": "event-1"}]}]


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


@pytest.mark.parametrize(
    ("ai_payload", "detail"),
    [
        ([], "AI response root is not an object"),
        ({"topics": [None]}, "AI response topic 0 is not an object"),
        (
            {"topics": [{"topic": "格局", "events": {}}]},
            "AI response topic 0 events is not a list",
        ),
        (
            {"topics": [{"topic": "格局", "events": [None]}]},
            "AI response topic 0 event 0 is not an object",
        ),
    ],
)
def test_briefing_generate_returns_controlled_error_for_malformed_ai_shape(
    client, monkeypatch, ai_payload, detail
):
    monkeypatch.setattr(
        briefing_module,
        "_fetch_translated_events",
        lambda limit: [
            {
                "id": "event-1",
                "source_id": "npr",
                "title": "Event",
                "title_cn": "事件",
                "summary_cn": "摘要",
                "topic": "world",
                "created_at": "2026-07-20 08:00:00",
            }
        ],
    )
    monkeypatch.setattr(
        briefing_module,
        "_call_ai",
        lambda **kwargs: json.dumps(ai_payload),
    )

    response = client.post(
        "/api/briefing/generate",
        json={"type": "quick", "limit": 80},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == f"AI generated invalid JSON: {detail}"
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM briefings").fetchone()[0] == 0


def test_briefing_generate_filters_invalid_and_unknown_event_references(
    client, monkeypatch
):
    monkeypatch.setattr(
        briefing_module,
        "_fetch_translated_events",
        lambda limit: [
            {
                "id": "event-1",
                "source_id": "npr",
                "title": "Event",
                "title_cn": "事件",
                "summary_cn": "摘要",
                "topic": "world",
                "created_at": "2026-07-20 08:00:00",
            }
        ],
    )
    monkeypatch.setattr(
        briefing_module,
        "_call_ai",
        lambda **kwargs: json.dumps(
            {
                "topics": [
                    {
                        "topic": "格局",
                        "events": [
                            {"event_id": "event-1", "title_cn": "有效事件"},
                            {"event_id": "", "title_cn": "空引用"},
                            {"event_id": None, "title_cn": "空值引用"},
                            {"title_cn": "缺少引用"},
                            {"event_id": ["event-1"], "title_cn": "错误类型"},
                            {"event_id": "unknown", "title_cn": "未知引用"},
                        ],
                    }
                ]
            }
        ),
    )
    monkeypatch.setattr(
        briefing_module,
        "_batch_contemplate_briefing_events",
        lambda topics: None,
    )

    response = client.post(
        "/api/briefing/generate",
        json={"type": "quick", "limit": 80},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["events_used"] == 1
    detail = client.get(f"/api/briefing/{payload['id']}")
    assert detail.status_code == 200
    assert detail.json()["events_used"] == 1
    assert detail.json()["topics"] == [
        {
            "topic": "格局",
            "events": [
                {
                    "event_id": "event-1",
                    "title_cn": "有效事件",
                    "created_at": "2026-07-20 08:00:00",
                }
            ],
        }
    ]
