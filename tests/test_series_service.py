from __future__ import annotations

import importlib
import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints

import pytest
from fastapi import HTTPException

from zhiji_backend.db import connect, init_db
from zhiji_backend.routes import series_routes


@pytest.fixture
def series_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "series.sqlite"))
    init_db()
    return connect, init_db


def _service():
    try:
        return importlib.import_module("zhiji_backend.series_service")
    except ModuleNotFoundError:
        pytest.fail("zhiji_backend.series_service has not been extracted")


def _insert_series(
    series_id: str,
    name: str,
    member_ids: list[str],
    *,
    status: str = "published",
    sort_order: list[str] | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO series "
            "(id, name, description, member_ids, sort_order, status, updated_at) "
            "VALUES (?, ?, 'old description', ?, ?, ?, '2000-01-01 00:00:00')",
            (
                series_id,
                name,
                json.dumps(member_ids),
                json.dumps(sort_order or []),
                status,
            ),
        )


def _insert_event(
    event_id: str,
    title: str,
    *,
    suggested_series_json: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sources (id, name, type, url) "
            "VALUES ('manual', 'Manual', 'manual', '')"
        )
        conn.execute(
            "INSERT INTO events "
            "(id, source_id, title, url, topic, status, overview, "
            "suggested_series_json, created_at) "
            "VALUES (?, 'manual', ?, ?, 'world', 'completed', ?, ?, ?)",
            (
                event_id,
                title,
                f"https://example.com/{event_id}",
                f"Overview for {event_id}",
                suggested_series_json,
                f"2026-07-{10 + len(event_id):02d} 12:00:00",
            ),
        )


def test_service_exposes_typed_public_contract() -> None:
    service = _service()

    assert service.name_similarity("Topic", "topic") == 1.0
    assert service.member_overlap_score(["a", "b"], ["b", "c"]) == pytest.approx(
        1 / 3
    )
    assert get_type_hints(service.create_series)["data"] is service.SeriesCreateData
    assert get_type_hints(service.reorder_series)["data"] is service.SeriesOrderData
    assert get_type_hints(service.add_series_members)["data"] is service.SeriesMembersData
    assert get_type_hints(service.merge_series)["data"] is service.SeriesMergeData

    service_functions = [
        service.list_series,
        service.list_candidates,
        service.create_series,
        service.delete_series,
        service.update_series,
        service.merge_series,
        service.get_series_detail,
        service.reorder_series,
        service.get_series_suggestions,
        service.add_series_members,
    ]
    for function in service_functions:
        signature = inspect.signature(function)
        assert signature.return_annotation is not inspect.Signature.empty
        assert all(
            parameter.annotation is not inspect.Parameter.empty
            for parameter in signature.parameters.values()
        )


def test_list_series_filters_candidates_and_renders_missing_member_placeholders(
    series_db,
) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db
    _insert_event("event-a", "Published event")
    _insert_series(
        "published-1", "Published", ["event-a", "deleted-event"]
    )
    _insert_series(
        "candidate-1",
        "Candidate",
        ["candidate-deleted"],
        status="candidate",
    )

    published_only = service.list_series(
        connect_fn=connect_fn, init_db_fn=init_db_fn
    )
    including_candidates = service.list_series(
        True, connect_fn=connect_fn, init_db_fn=init_db_fn
    )

    assert [item["id"] for item in published_only["items"]] == ["published-1"]
    assert published_only["items"][0]["members"] == [
        {"id": "event-a", "title": "Published event"},
        {"id": "deleted-event", "title": "(已删除)"},
    ]
    included = {item["id"]: item for item in including_candidates["items"]}
    assert set(included) == {"published-1", "candidate-1"}
    assert included["candidate-1"]["members"] == [
        {"id": "candidate-deleted", "title": "(已删除)"}
    ]


def test_list_candidates_parses_members_and_returns_similarity_shape(series_db) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db
    _insert_event("event-a", "Candidate event")
    _insert_series(
        "candidate-1",
        "Alpha topic",
        ["event-a", "deleted-event"],
        status="candidate",
    )
    _insert_series(
        "published-1", "Alpha topics", ["event-a", "event-b"]
    )
    _insert_series("candidate-bad", "Unrelated", [], status="candidate")
    with connect() as conn:
        conn.execute(
            "UPDATE series SET member_ids = 'not-json' WHERE id = 'candidate-bad'"
        )

    result = service.list_candidates(
        connect_fn=connect_fn, init_db_fn=init_db_fn
    )

    items = {item["id"]: item for item in result["items"]}
    assert result["total"] == 2
    assert items["candidate-1"]["member_count"] == 2
    assert items["candidate-1"]["members"] == [
        {"id": "event-a", "title": "Candidate event"},
        {"id": "deleted-event", "title": "(已删除)"},
    ]
    assert items["candidate-1"]["similar_to"] == [
        {
            "id": "published-1",
            "name": "Alpha topics",
            "status": "published",
            "name_similarity": round(
                service.name_similarity("Alpha topic", "Alpha topics"), 3
            ),
            "member_overlap": 0.333,
        }
    ]
    assert items["candidate-bad"]["member_count"] == 0
    assert items["candidate-bad"]["members"] == []


def test_delete_series_deletes_existing_series_and_returns_404_for_missing(
    series_db,
) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db
    _insert_series("series-1", "Series", ["event-a", "event-b"])

    assert service.delete_series(
        "series-1", connect_fn=connect_fn, init_db_fn=init_db_fn
    ) == {"deleted": "series-1"}
    with connect() as conn:
        assert conn.execute(
            "SELECT id FROM series WHERE id = 'series-1'"
        ).fetchone() is None

    with pytest.raises(HTTPException) as error:
        service.delete_series(
            "missing", connect_fn=connect_fn, init_db_fn=init_db_fn
        )
    assert error.value.status_code == 404
    assert error.value.detail == "专题不存在"


def test_reorder_series_persists_order_and_minute_timestamp_and_handles_missing(
    series_db,
) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db
    _insert_series("series-1", "Series", ["event-a", "event-b"])
    order = SimpleNamespace(member_ids=["event-b", "event-a"])

    assert service.reorder_series(
        "series-1", order, connect_fn=connect_fn, init_db_fn=init_db_fn
    ) == {"id": "series-1", "member_ids": ["event-b", "event-a"]}
    with connect() as conn:
        row = conn.execute(
            "SELECT sort_order, updated_at FROM series WHERE id = 'series-1'"
        ).fetchone()
    assert json.loads(row["sort_order"]) == ["event-b", "event-a"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", row["updated_at"])

    with pytest.raises(HTTPException) as error:
        service.reorder_series(
            "missing", order, connect_fn=connect_fn, init_db_fn=init_db_fn
        )
    assert error.value.status_code == 404
    assert error.value.detail == "专题不存在"


def test_create_upgrades_same_name_candidate_and_creates_new_published_series(
    series_db,
) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db
    _insert_series("candidate-1", "Same name", ["old-a", "old-b"], status="candidate")

    upgraded = service.create_series(
        series_routes.SeriesCreateRequest(
            name="  Same name  ",
            description="  replacement  ",
            member_ids=["new-a", "new-b"],
        ),
        connect_fn=connect_fn,
        init_db_fn=init_db_fn,
    )
    created = service.create_series(
        series_routes.SeriesCreateRequest(
            name="Brand new",
            description="description",
            member_ids=["new-c", "new-d"],
        ),
        connect_fn=connect_fn,
        init_db_fn=init_db_fn,
    )

    assert upgraded == {"id": "candidate-1", "name": "Same name"}
    assert created["name"] == "Brand new"
    assert created["id"].startswith("series-")
    with connect() as conn:
        rows = {
            row["id"]: dict(row)
            for row in conn.execute(
                "SELECT id, name, description, member_ids, status FROM series"
            ).fetchall()
        }
    assert rows["candidate-1"] == {
        "id": "candidate-1",
        "name": "Same name",
        "description": "replacement",
        "member_ids": '["new-a", "new-b"]',
        "status": "published",
    }
    assert rows[created["id"]]["status"] == "published"


def test_update_changes_only_allowed_fields_and_ignores_unknown_fields(series_db) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db
    _insert_series("series-1", "Old", ["a", "b"])

    assert service.update_series(
        "series-1",
        {
            "name": "New",
            "description": "New description",
            "status": "candidate",
            "member_ids": '["replaced"]',
            "unexpected": "ignored",
        },
        connect_fn=connect_fn,
        init_db_fn=init_db_fn,
    ) == {"updated": "series-1"}

    with connect() as conn:
        row = conn.execute("SELECT * FROM series WHERE id = 'series-1'").fetchone()
    assert row["name"] == "New"
    assert row["description"] == "New description"
    assert row["status"] == "candidate"
    assert row["member_ids"] == '["a", "b"]'
    assert row["updated_at"] != "2000-01-01 00:00:00"


def test_update_with_only_unknown_fields_does_not_touch_timestamp(series_db) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db
    _insert_series("series-1", "Old", ["a", "b"])

    result = service.update_series(
        "series-1",
        {"member_ids": [], "unexpected": True},
        connect_fn=connect_fn,
        init_db_fn=init_db_fn,
    )

    assert result == {"updated": "series-1"}
    with connect() as conn:
        updated_at = conn.execute(
            "SELECT updated_at FROM series WHERE id = 'series-1'"
        ).fetchone()[0]
    assert updated_at == "2000-01-01 00:00:00"


def test_update_missing_series_returns_404(series_db) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db

    with pytest.raises(HTTPException) as error:
        service.update_series(
            "missing",
            {"name": "New"},
            connect_fn=connect_fn,
            init_db_fn=init_db_fn,
        )

    assert error.value.status_code == 404
    assert error.value.detail == "专题不存在"


def test_merge_preserves_order_deduplicates_deletes_source_and_invalidates_cache(
    series_db,
) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db
    _insert_series("target", "Target", ["event-a", "event-b"])
    _insert_series("source", "Source", ["event-b", "event-c"], status="candidate")
    with connect() as conn:
        conn.execute(
            "INSERT INTO series_scan_cache "
            "(series_id, scanned_count, recommendations_json) VALUES ('target', 2, '[]')"
        )

    result = service.merge_series(
        series_routes.SeriesMergeRequest(source_id="source", target_id="target"),
        connect_fn=connect_fn,
        init_db_fn=init_db_fn,
    )

    assert result["target"]["member_ids"] == ["event-a", "event-b", "event-c"]
    assert result["target"]["members_added"] == 1
    with connect() as conn:
        assert conn.execute("SELECT id FROM series WHERE id = 'source'").fetchone() is None
        target = conn.execute(
            "SELECT member_ids FROM series WHERE id = 'target'"
        ).fetchone()
        cache = conn.execute(
            "SELECT series_id FROM series_scan_cache WHERE series_id = 'target'"
        ).fetchone()
    assert json.loads(target["member_ids"]) == ["event-a", "event-b", "event-c"]
    assert cache is None


def test_detail_preserves_sort_order_and_omits_missing_members(series_db) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db
    for event_id in ["event-a", "event-b", "event-c"]:
        _insert_event(event_id, f"Title {event_id}")
    _insert_series(
        "series-1",
        "Series",
        ["event-a", "deleted-event", "event-b", "event-c"],
        sort_order=["event-b", "deleted-event", "event-a"],
    )

    result = service.get_series_detail(
        "series-1", connect_fn=connect_fn, init_db_fn=init_db_fn
    )

    assert [member["id"] for member in result["members"]] == [
        "event-b",
        "event-a",
        "event-c",
    ]
    assert "deleted-event" not in {member["id"] for member in result["members"]}


def test_member_append_preserves_order_skips_existing_ids_and_invalidates_cache(
    series_db,
) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db
    _insert_series("series-1", "Series", ["event-a", "event-b"])
    with connect() as conn:
        conn.execute(
            "INSERT INTO series_scan_cache "
            "(series_id, scanned_count, recommendations_json) VALUES ('series-1', 2, '[]')"
        )

    result = service.add_series_members(
        "series-1",
        series_routes.SeriesMembersRequest(
            event_ids=["event-b", "event-c", "event-d"]
        ),
        connect_fn=connect_fn,
        init_db_fn=init_db_fn,
    )

    assert result == {
        "id": "series-1",
        "member_ids": ["event-a", "event-b", "event-c", "event-d"],
    }
    with connect() as conn:
        cache = conn.execute(
            "SELECT series_id FROM series_scan_cache WHERE series_id = 'series-1'"
        ).fetchone()
    assert cache is None


def test_member_append_preserves_repeated_new_ids_in_direct_service_input(
    series_db,
) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db
    _insert_series("series-1", "Series", ["event-a", "event-b"])

    result = service.add_series_members(
        "series-1",
        SimpleNamespace(event_ids=["event-c", "event-c"]),
        connect_fn=connect_fn,
        init_db_fn=init_db_fn,
    )

    assert result == {
        "id": "series-1",
        "member_ids": ["event-a", "event-b", "event-c", "event-c"],
    }
    with connect() as conn:
        stored_member_ids = conn.execute(
            "SELECT member_ids FROM series WHERE id = 'series-1'"
        ).fetchone()[0]
    assert json.loads(stored_member_ids) == [
        "event-a",
        "event-b",
        "event-c",
        "event-c",
    ]


def test_suggestions_support_legacy_strings_and_new_objects(series_db) -> None:
    service = _service()
    connect_fn, init_db_fn = series_db
    _insert_series("series-1", "Series", ["existing", "other"])
    _insert_event("existing", "Existing", suggested_series_json='["series-1"]')
    _insert_event("legacy", "Legacy", suggested_series_json='["series-1"]')
    _insert_event(
        "object",
        "Object",
        suggested_series_json='[{"series_id":"series-1","reason":"Relevant"}]',
    )

    result = service.get_series_suggestions(
        "series-1", connect_fn=connect_fn, init_db_fn=init_db_fn
    )

    suggestions = {item["id"]: item for item in result["suggestions"]}
    assert set(suggestions) == {"legacy", "object"}
    assert suggestions["legacy"]["reason"] == ""
    assert suggestions["object"]["reason"] == "Relevant"
