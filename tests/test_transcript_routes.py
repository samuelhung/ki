from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zhiji_backend import db
from zhiji_backend import transcript_revision_service as revisions
from zhiji_backend import transcript_segmentation_service as segmentation
from zhiji_backend.main import app


@pytest.fixture
def transcript_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "routes.sqlite"))
    db.init_db()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, url) VALUES (?, ?, ?, ?)",
            ("source", "Source", "manual", ""),
        )
        conn.execute(
            """INSERT INTO events
               (id, source_id, title, url, raw_summary, ai_summary)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("evt-1", "source", "Title", "", "原始正文ABC123", "旧总结"),
        )
        conn.execute(
            """INSERT INTO events
               (id, source_id, title, url, raw_summary)
               VALUES (?, ?, ?, ?, ?)""",
            ("evt-2", "source", "Other", "", "其他正文"),
        )

    from zhiji_backend.routes import transcript_routes

    monkeypatch.setattr(transcript_routes, "TRANSCRIPTS_DIR", tmp_path / "transcripts")
    monkeypatch.setattr(
        transcript_routes,
        "chat",
        lambda messages, **_kwargs: (
            messages[-1]["content"]
            .split("<<<核心文本>>>\n", 1)[1]
            .split("\n<<<只读下文>>>", 1)[0]
            + "。\n\n"
        ),
    )
    with segmentation._TASKS_LOCK:
        segmentation._TASKS.clear()
    return TestClient(app), transcript_routes


def _initialize_and_save_manual(client: TestClient) -> tuple[str, str]:
    original = client.get("/api/events/evt-1/transcript").json()["active_revision"][
        "id"
    ]
    response = client.put(
        "/api/events/evt-1/transcript/manual",
        json={"content": "人工正文ABC123", "base_revision_id": original},
    )
    assert response.status_code == 200
    return original, response.json()["active_revision"]["id"]


def test_transcript_workflow_initializes_saves_segments_and_confirms(transcript_client):
    client, _routes = transcript_client

    loaded = client.get("/api/events/evt-1/transcript")
    assert loaded.status_code == 200
    assert loaded.json()["active_revision"]["kind"] == "original"
    assert loaded.json()["content"] == "原始正文ABC123"
    assert loaded.json()["can_segment"] is False

    _original, manual_id = _initialize_and_save_manual(client)
    started = client.post(
        "/api/events/evt-1/transcript/segment",
        json={"base_revision_id": manual_id},
    )
    assert started.status_code == 202
    task_id = started.json()["id"]

    status = client.get(f"/api/events/evt-1/transcript/segment/{task_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "ready"
    assert status.json()["preview"] == "人工正文ABC123。\n\n"
    assert "source" not in status.json()

    confirmed = client.post(f"/api/events/evt-1/transcript/segment/{task_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["active_revision"]["kind"] == "segmented"
    assert confirmed.json()["content"] == "人工正文ABC123。\n\n"
    assert confirmed.json()["summary_stale"] is True
    assert (
        client.post(f"/api/events/evt-1/transcript/segment/{task_id}/confirm").json()[
            "active_revision"
        ]["id"]
        == confirmed.json()["active_revision"]["id"]
    )


def test_revision_content_and_restore_are_event_scoped_and_append_only(
    transcript_client,
):
    client, _routes = transcript_client
    original_id, manual_id = _initialize_and_save_manual(client)

    historical = client.get(f"/api/events/evt-1/transcript/revisions/{original_id}")
    assert historical.status_code == 200
    assert historical.json()["content"] == "原始正文ABC123"

    restored = client.post(
        f"/api/events/evt-1/transcript/revisions/{original_id}/restore",
        json={"base_revision_id": manual_id},
    )
    assert restored.status_code == 200
    assert restored.json()["active_revision"]["kind"] == "restored"
    assert restored.json()["active_revision"]["source_revision_id"] == original_id
    assert [item["kind"] for item in restored.json()["revisions"]] == [
        "restored",
        "manual",
        "original",
    ]

    foreign_id = client.get("/api/events/evt-2/transcript").json()["active_revision"][
        "id"
    ]
    assert (
        client.get(f"/api/events/evt-1/transcript/revisions/{foreign_id}").status_code
        == 404
    )


def test_conflicts_unknown_resources_and_manual_requirement_map_to_http(
    transcript_client,
):
    client, _routes = transcript_client
    original = client.get("/api/events/evt-1/transcript").json()["active_revision"][
        "id"
    ]

    non_manual = client.post(
        "/api/events/evt-1/transcript/segment",
        json={"base_revision_id": original},
    )
    assert non_manual.status_code == 422

    _original, manual_id = _initialize_and_save_manual(client)
    stale = client.put(
        "/api/events/evt-1/transcript/manual",
        json={"content": "冲突正文", "base_revision_id": original},
    )
    assert stale.status_code == 409
    assert (
        client.post(
            f"/api/events/evt-1/transcript/revisions/{original}/restore",
            json={"base_revision_id": original},
        ).status_code
        == 409
    )
    assert client.get("/api/events/missing/transcript").status_code == 404
    assert (
        client.get("/api/events/evt-1/transcript/revisions/tr-missing").status_code
        == 404
    )
    assert (
        client.get("/api/events/evt-1/transcript/segment/task-missing").status_code
        == 404
    )

    started = client.post(
        "/api/events/evt-1/transcript/segment",
        json={"base_revision_id": manual_id},
    )
    assert started.status_code == 202
    task_id = started.json()["id"]
    with segmentation._TASKS_LOCK:
        segmentation._TASKS[task_id].created_at = (
            time.monotonic() - segmentation.TASK_TTL_SECONDS - 1
        )
    assert (
        client.get(f"/api/events/evt-1/transcript/segment/{task_id}").status_code == 410
    )


def test_artifact_publication_failure_returns_accepted_and_repairs_on_read(
    transcript_client, monkeypatch: pytest.MonkeyPatch
):
    client, routes = transcript_client
    original = client.get("/api/events/evt-1/transcript").json()["active_revision"][
        "id"
    ]
    real_publish = revisions.publish_transcript_artifact
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("disk unavailable")
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(revisions, "publish_transcript_artifact", fail_once)
    saved = client.put(
        "/api/events/evt-1/transcript/manual",
        json={"content": "待同步正文", "base_revision_id": original},
    )
    assert saved.status_code == 202
    assert saved.json()["artifact_synced"] is False

    refreshed = client.get("/api/events/evt-1/transcript")
    assert refreshed.status_code == 200
    assert refreshed.json()["artifact_synced"] is True
    assert (routes.TRANSCRIPTS_DIR / "evt-1.md").read_text(
        encoding="utf-8"
    ) == "待同步正文"


def test_body_change_failure_never_activates_a_segmented_revision(
    transcript_client, monkeypatch: pytest.MonkeyPatch
):
    client, routes = transcript_client
    _original, manual_id = _initialize_and_save_manual(client)
    monkeypatch.setattr(routes, "chat", lambda _messages, **_kwargs: "正文被篡改")

    started = client.post(
        "/api/events/evt-1/transcript/segment",
        json={"base_revision_id": manual_id},
    )
    task_id = started.json()["id"]
    status_response = client.get(f"/api/events/evt-1/transcript/segment/{task_id}")

    assert status_response.json() == {
        "id": task_id,
        "status": "failed",
        "base_revision_id": manual_id,
        "completed_chunks": 0,
        "total_chunks": 1,
        "error_code": "body_changed",
    }
    assert (
        client.post(
            f"/api/events/evt-1/transcript/segment/{task_id}/confirm"
        ).status_code
        == 409
    )
    active = client.get("/api/events/evt-1/transcript").json()["active_revision"]
    assert active["id"] == manual_id
    assert active["kind"] == "manual"


def test_body_and_identifier_constraints_are_rejected_before_mutation(
    transcript_client,
):
    client, _routes = transcript_client
    original = client.get("/api/events/evt-1/transcript").json()["active_revision"][
        "id"
    ]

    assert (
        client.put(
            "/api/events/evt-1/transcript/manual",
            json={"content": "x" * 2_000_001, "base_revision_id": original},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/events/evt-1/transcript/manual",
            json={"content": "正文", "base_revision_id": "../bad"},
        ).status_code
        == 422
    )
