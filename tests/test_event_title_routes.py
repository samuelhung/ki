from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from zhiji_backend import event_title_service
from zhiji_backend.main import app
from zhiji_backend.routes import event_routes


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_update_event_title_strips_value_and_forwards_connect_dependency(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str, object]] = []

    def update_display_title(event_id: str, title: str, *, connect_fn: object):
        calls.append((event_id, title, connect_fn))
        return {"id": event_id, "title": "Original", "title_cn": title}

    monkeypatch.setattr(
        event_routes._titles, "update_display_title", update_display_title
    )

    response = client.put("/api/events/event-1/title", json={"display_title": "  展示标题  "})

    assert response.status_code == 200
    assert response.json() == {
        "id": "event-1",
        "title": "Original",
        "title_cn": "展示标题",
    }
    assert calls == [("event-1", "展示标题", event_routes.connect)]


@pytest.mark.parametrize("display_title", ["", "   ", "中" * 21])
def test_update_event_title_rejects_empty_or_overlong_values(
    client: TestClient, display_title: str
) -> None:
    response = client.put(
        "/api/events/event-1/title", json={"display_title": display_title}
    )

    assert response.status_code == 422


@pytest.mark.parametrize("display_title", ["\u001c", "\u0085", "\ufeff", "\u00a0"])
def test_update_event_title_rejects_cross_runtime_whitespace_only(
    client: TestClient, display_title: str
) -> None:
    response = client.put(
        "/api/events/event-1/title", json={"display_title": display_title}
    )

    assert response.status_code == 422


def test_update_event_title_accepts_twenty_characters(client: TestClient, monkeypatch) -> None:
    title = "中" * 20
    monkeypatch.setattr(
        event_routes._titles,
        "update_display_title",
        lambda event_id, display_title, *, connect_fn: {
            "id": event_id,
            "title": "Original",
            "title_cn": display_title,
        },
    )

    response = client.put("/api/events/event-1/title", json={"display_title": title})

    assert response.status_code == 200
    assert response.json()["title_cn"] == title


def test_update_event_title_maps_unknown_event_to_not_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def update_display_title(*_args, **_kwargs):
        raise event_title_service.EventNotFoundError

    monkeypatch.setattr(
        event_routes._titles, "update_display_title", update_display_title
    )

    response = client.put("/api/events/missing/title", json={"display_title": "标题"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}


def test_suggest_event_titles_forwards_connect_dependency_and_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, object]] = []

    def suggest_display_titles(event_id: str, *, connect_fn: object):
        calls.append((event_id, connect_fn))
        return ["候选一", "候选二", "候选三"]

    monkeypatch.setattr(
        event_routes._titles, "suggest_display_titles", suggest_display_titles
    )

    response = client.post("/api/events/event-1/title/suggestions")

    assert response.status_code == 200
    assert response.json() == {"titles": ["候选一", "候选二", "候选三"]}
    assert calls == [("event-1", event_routes.connect)]


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (event_title_service.EventNotFoundError, 404, "Event not found"),
        (
            event_title_service.TranscriptUnavailableError,
            400,
            "Event has no transcript content",
        ),
        (
            event_title_service.TitleSuggestionError,
            502,
            "Title suggestions are temporarily unavailable",
        ),
    ],
)
def test_suggest_event_titles_maps_domain_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: type[Exception],
    status_code: int,
    detail: str,
) -> None:
    def suggest_display_titles(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(
        event_routes._titles, "suggest_display_titles", suggest_display_titles
    )

    response = client.post("/api/events/missing/title/suggestions")

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
