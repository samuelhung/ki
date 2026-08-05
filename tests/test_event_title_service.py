from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from zhiji_backend import event_title_service
from zhiji_backend.transcript_revision_service import TranscriptState

EXPECTED_TITLE_EDGE_WHITESPACE = (
    "\u0009\u000a\u000b\u000c\u000d"
    "\u001c\u001d\u001e\u001f"
    "\u0020\u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000\ufeff"
)


@contextmanager
def _connect(database: Path):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _create_events(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                title_cn TEXT
            );
            INSERT INTO events (id, title, title_cn)
            VALUES ('event-1', 'Original title', '旧标题');
            """
        )


def _transcript(content: str) -> TranscriptState:
    return TranscriptState(
        event_id="event-1",
        original_revision_id="tr-original",
        active_revision_id="tr-active",
        artifact_revision_id="tr-active",
        summary_revision_id="tr-active",
        active_kind="manual",
        active_content=content,
        active_created_at="2026-08-04 00:00:00",
    )


def test_normalize_display_title_strips_and_accepts_twenty_characters() -> None:
    assert event_title_service.normalize_display_title("  中文标题  ") == "中文标题"
    assert event_title_service.normalize_display_title("中" * 20) == "中" * 20


def test_title_edge_whitespace_contract_is_explicit_and_complete() -> None:
    assert event_title_service.DISPLAY_TITLE_EDGE_WHITESPACE == EXPECTED_TITLE_EDGE_WHITESPACE


@pytest.mark.parametrize("edge", ["\u001c", "\u0085", "\ufeff", "\u00a0"])
def test_normalize_display_title_uses_the_cross_runtime_edge_whitespace_contract(
    edge: str,
) -> None:
    assert event_title_service.normalize_display_title(f"{edge}中文标题{edge}") == "中文标题"


@pytest.mark.parametrize("edge", ["\u001c", "\u0085", "\ufeff", "\u00a0"])
def test_normalize_display_title_rejects_contract_whitespace_only(edge: str) -> None:
    with pytest.raises(event_title_service.InvalidDisplayTitleError):
        event_title_service.normalize_display_title(edge)


@pytest.mark.parametrize("value", ["", "   ", "中" * 21])
def test_normalize_display_title_rejects_empty_and_overlong_values(value: str) -> None:
    with pytest.raises(event_title_service.InvalidDisplayTitleError):
        event_title_service.normalize_display_title(value)


def test_update_display_title_only_changes_title_cn(tmp_path: Path) -> None:
    database = tmp_path / "events.sqlite"
    _create_events(database)

    result = event_title_service.update_display_title(
        "event-1",
        "  新标题  ",
        connect_fn=lambda: _connect(database),
    )

    assert result == {"id": "event-1", "title": "Original title", "title_cn": "新标题"}
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT title, title_cn FROM events WHERE id = 'event-1'"
        ).fetchone()
    assert row == ("Original title", "新标题")


def test_update_display_title_rejects_unknown_event(tmp_path: Path) -> None:
    database = tmp_path / "events.sqlite"
    _create_events(database)

    with pytest.raises(event_title_service.EventNotFoundError):
        event_title_service.update_display_title(
            "missing",
            "新标题",
            connect_fn=lambda: _connect(database),
        )


def test_suggest_display_titles_sends_active_transcript_and_required_ai_options() -> None:
    calls: list[dict[str, object]] = []

    def ai_chat_fn(**kwargs):
        calls.append(kwargs)
        return '{"titles":["标题甲","标题乙","标题丙"]}'

    result = event_title_service.suggest_display_titles(
        "event-1",
        get_transcript_fn=lambda event_id, **_kwargs: _transcript("当前人工修正转写"),
        ai_chat_fn=ai_chat_fn,
    )

    assert result == ["标题甲", "标题乙", "标题丙"]
    assert "当前人工修正转写" in calls[0]["messages"][0]["content"]
    assert "json" in calls[0]["messages"][0]["content"]
    assert calls[0] == {
        "messages": calls[0]["messages"],
        "temperature": 0.2,
        "max_tokens": 256,
        "response_format": {"type": "json_object"},
        "module": "event_title",
        "task": "suggestions",
        "model": "deepseek-v4-flash",
        "thinking": False,
    }


@pytest.mark.parametrize(
    "response",
    [
        None,
        "not json",
        "[]",
        '{"titles":["甲","乙"]}',
        '{"titles":["甲","甲","丙"]}',
        '{"titles":["甲","中中中中中中中中中中中中中中中中中中中中中","丙"]}',
        '{"titles":["甲", 2, "丙"]}',
    ],
)
def test_suggest_display_titles_rejects_invalid_ai_batches(response: str | None) -> None:
    with pytest.raises(event_title_service.TitleSuggestionError):
        event_title_service.suggest_display_titles(
            "event-1",
            get_transcript_fn=lambda event_id, **_kwargs: _transcript("可用转写"),
            ai_chat_fn=lambda **_kwargs: response,
        )


def test_suggest_display_titles_accepts_three_distinct_twenty_character_titles() -> None:
    titles = ["甲" * 20, "乙" * 20, "丙" * 20]

    assert event_title_service.suggest_display_titles(
        "event-1",
        get_transcript_fn=lambda event_id, **_kwargs: _transcript("可用转写"),
        ai_chat_fn=lambda **_kwargs: '{"titles":["' + '","'.join(titles) + '"]}',
    ) == titles


def test_suggest_display_titles_normalizes_contract_whitespace_from_ai_candidates() -> None:
    assert event_title_service.suggest_display_titles(
        "event-1",
        get_transcript_fn=lambda event_id, **_kwargs: _transcript("可用转写"),
        ai_chat_fn=lambda **_kwargs: '{"titles":["\\u001c标题甲\\u001c","\\u0085标题乙\\u0085","\\ufeff标题丙\\ufeff"]}',
    ) == ["标题甲", "标题乙", "标题丙"]


def test_suggest_display_titles_rejects_empty_transcript() -> None:
    with pytest.raises(event_title_service.TranscriptUnavailableError):
        event_title_service.suggest_display_titles(
            "event-1",
            get_transcript_fn=lambda event_id, **_kwargs: _transcript("  "),
            ai_chat_fn=lambda **_kwargs: pytest.fail("AI should not be called"),
        )


def test_suggest_display_titles_maps_missing_transcript_event_to_title_service_error() -> None:
    def missing_transcript(event_id, **_kwargs):
        raise event_title_service.transcript_revision_service.EventNotFoundError(event_id)

    with pytest.raises(event_title_service.EventNotFoundError):
        event_title_service.suggest_display_titles(
            "event-1",
            get_transcript_fn=missing_transcript,
            ai_chat_fn=lambda **_kwargs: pytest.fail("AI should not be called"),
        )
