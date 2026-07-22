import json

import pytest
from fastapi.testclient import TestClient

from zhiji_backend.main import app
from zhiji_backend.db import connect
from zhiji_backend.routes import event_routes


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    [
        "/api/events?limit=200&offset=1000000",
        "/api/tasks?limit=200&offset=1000000",
        "/api/brainstorm?limit=200&offset=1000000",
        "/api/ingest/queue?limit=200",
        "/api/study/list?page_size=200&page=1",
        "/api/study/mistakes/list?page_size=200&page=1",
        "/api/briefing?limit=200&offset=1000000",
        "/api/chains/hints?limit=200",
        "/api/chains/suggestions?limit=200",
        "/api/dashboard/trend?days=365",
    ],
)
def test_query_bounds_accept_exact_maximum(client, path):
    response = client.get(path)

    assert response.status_code != 422


@pytest.mark.parametrize(
    "path",
    [
        "/api/events?limit=201",
        "/api/events?offset=1000001",
        "/api/tasks?limit=201",
        "/api/tasks?offset=1000001",
        "/api/brainstorm?limit=201",
        "/api/brainstorm?offset=1000001",
        "/api/ingest/queue?limit=201",
        "/api/study/list?page_size=201",
        "/api/study/mistakes/list?page_size=201",
        "/api/briefing?limit=201",
        "/api/briefing?offset=1000001",
        "/api/chains/hints?limit=201",
        "/api/chains/suggestions?limit=201",
        "/api/dashboard/trend?days=366",
    ],
)
def test_query_bounds_reject_overflow_with_422(client, path):
    response = client.get(path)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/api/study/list?page=5001&page_size=200",
        "/api/study/mistakes/list?page=5001&page_size=200",
    ],
)
def test_study_pagination_accepts_exact_maximum_derived_offset(client, path):
    response = client.get(path)

    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/study/list?page=5002&page_size=200",
        "/api/study/mistakes/list?page=5002&page_size=200",
    ],
)
def test_study_pagination_rejects_derived_offset_overflow(client, path):
    response = client.get(path)

    assert response.status_code == 422


def test_event_batch_delete_accepts_100_ids_and_rejects_101(client):
    accepted = client.post(
        "/api/events/batch-delete",
        json={"event_ids": [f"evt-{index}" for index in range(100)]},
    )
    rejected = client.post(
        "/api/events/batch-delete",
        json={"event_ids": [f"evt-{index}" for index in range(101)]},
    )

    assert accepted.status_code == 200
    assert rejected.status_code == 422


def test_event_batch_delete_rejects_empty_and_unsafe_ids(client):
    empty = client.post("/api/events/batch-delete", json={"event_ids": []})
    unsafe = client.post(
        "/api/events/batch-delete", json={"event_ids": ["../outside"]}
    )

    assert empty.status_code == 422
    assert unsafe.status_code == 422


def test_classify_source_filter_caps_and_deduplicates_in_order(client, monkeypatch):
    captured = []

    def classify_batch(*, source_ids, limit):
        captured.append((source_ids, limit))
        return {"classified": 0, "failed": 0}

    monkeypatch.setattr(event_routes, "classify_batch", classify_batch)

    accepted = client.post("/api/classify/batch?source_ids=b,a,b&limit=100")
    rejected = client.post(
        "/api/classify/batch?source_ids="
        + ",".join(f"source-{index}" for index in range(101))
    )

    assert accepted.status_code == 200
    assert captured == [(["b", "a"], 100)]
    assert rejected.status_code == 422


def test_brainstorm_reference_ids_accept_100_deduped_and_reject_101(
    client, monkeypatch
):
    captured = []

    def build_reference_docs(event_ids):
        captured.append(event_ids)
        return [], {}

    monkeypatch.setattr(event_routes, "classify_batch", lambda **kwargs: {})
    from zhiji_backend.routes import brainstorm_routes

    monkeypatch.setattr(brainstorm_routes, "_build_reference_docs", build_reference_docs)

    accepted = client.post(
        "/api/brainstorm/question-1/conversation/start",
        json={
            "event_ids": ["evt-b", "evt-a", "evt-b"]
            + [f"evt-{index}" for index in range(97)],
            "question": "test",
        },
    )
    rejected = client.post(
        "/api/brainstorm/question-1/conversation/start",
        json={
            "event_ids": [f"evt-{index}" for index in range(101)],
            "question": "test",
        },
    )

    assert accepted.status_code == 200
    assert captured == [["evt-b", "evt-a"] + [f"evt-{index}" for index in range(97)]]
    assert rejected.status_code == 422


def test_series_member_ids_cap_and_deduplicate_in_order(client):
    member_ids = ["evt-b", "evt-a", "evt-b"] + [
        f"evt-{index}" for index in range(97)
    ]
    accepted = client.post(
        "/api/ingest/series",
        json={"name": "constraint-series", "member_ids": member_ids},
    )
    rejected = client.post(
        "/api/ingest/series",
        json={
            "name": "constraint-series-overflow",
            "member_ids": [f"evt-overflow-{index}" for index in range(101)],
        },
    )

    assert accepted.status_code == 200
    with connect() as conn:
        row = conn.execute(
            "SELECT member_ids FROM series WHERE id = ?", (accepted.json()["id"],)
        ).fetchone()
    assert json.loads(row["member_ids"]) == ["evt-b", "evt-a"] + [
        f"evt-{index}" for index in range(97)
    ]
    assert rejected.status_code == 422


def test_series_requires_two_distinct_member_ids_after_deduplication(client):
    response = client.post(
        "/api/ingest/series",
        json={"name": "duplicate-only-series", "member_ids": ["evt-a", "evt-a"]},
    )

    assert response.status_code == 422


def test_chain_hint_sync_accepts_100_items_and_rejects_101(client):
    accepted = client.post("/api/chains/hints/sync", json={"hints": [{}] * 100})
    rejected = client.post("/api/chains/hints/sync", json={"hints": [{}] * 101})

    assert accepted.status_code == 200
    assert rejected.status_code == 422


def test_ai_request_item_limits_reject_101(client):
    assert client.post("/api/tag/batch", json={"limit": 101}).status_code == 422
    assert client.post("/api/translate/run", json={"limit": 101}).status_code == 422
    assert (
        client.post(
            "/api/briefing/generate", json={"type": "quick", "limit": 101}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/events/bad%5Cid",
        "/api/brainstorm/bad%5Cid",
        "/api/study/bad%5Cid",
        "/api/tasks/bad%5Cid",
        "/api/ingest/status/bad%5Cid",
        "/api/briefing/bad%5Cid",
    ],
)
def test_route_ids_reject_backslash_with_422(client, path):
    response = client.get(path)

    assert response.status_code == 422


def test_task_linked_source_id_rejects_unsafe_identifier(client):
    response = client.post(
        "/api/tasks",
        json={"title": "unsafe", "source_id": r"event\outside"},
    )

    assert response.status_code == 422
