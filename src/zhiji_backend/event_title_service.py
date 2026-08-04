"""Display-title operations for ingest events."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from . import ai_client, transcript_revision_service
from .db import connect
from .security.constraints import safe_identifier


class InvalidDisplayTitleError(ValueError):
    """Raised when a display title is empty or exceeds its length limit."""


class EventNotFoundError(LookupError):
    """Raised when a title operation targets an unknown event."""


class TranscriptUnavailableError(ValueError):
    """Raised when an event has no usable active transcript."""


class TitleSuggestionError(ValueError):
    """Raised when AI title suggestions do not meet the output contract."""


def normalize_display_title(value: str) -> str:
    """Return a trimmed display title constrained to one through twenty characters."""
    if not isinstance(value, str):
        raise InvalidDisplayTitleError
    normalized = value.strip()
    if not 1 <= len(normalized) <= 20:
        raise InvalidDisplayTitleError
    return normalized


def update_display_title(
    event_id: str, display_title: str, *, connect_fn=connect
) -> dict[str, str | None]:
    """Persist a display title without changing the original event title."""
    safe_identifier(event_id)
    title_cn = normalize_display_title(display_title)
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id, title, title_cn FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if row is None:
            raise EventNotFoundError(event_id)
        conn.execute("UPDATE events SET title_cn = ? WHERE id = ?", (title_cn, event_id))
    return {"id": row["id"], "title": row["title"], "title_cn": title_cn}


def _suggestion_prompt(transcript: str) -> str:
    return f"""基于以下转写内容，为事件生成中文展示标题。

转写内容：
{transcript}

规则：
1. 只返回 JSON 对象，格式必须是 {{"titles":[...]}}，不得包含任何其他文字。
2. titles 必须恰好包含 3 个互不重复的中文候选。
3. 每个候选去除首尾空白后必须为 1 到 20 个字符。
"""


def _parse_suggestions(response: str | None) -> list[str]:
    if not isinstance(response, str) or not response.strip():
        raise TitleSuggestionError
    try:
        payload: Any = json.loads(response)
    except json.JSONDecodeError as exc:
        raise TitleSuggestionError from exc
    if not isinstance(payload, dict):
        raise TitleSuggestionError
    titles = payload.get("titles")
    if not isinstance(titles, list) or len(titles) != 3:
        raise TitleSuggestionError
    try:
        normalized = [normalize_display_title(title) for title in titles]
    except InvalidDisplayTitleError as exc:
        raise TitleSuggestionError from exc
    if len(set(normalized)) != 3:
        raise TitleSuggestionError
    return normalized


def suggest_display_titles(
    event_id: str,
    *,
    connect_fn=connect,
    get_transcript_fn: Callable[..., transcript_revision_service.TranscriptState] = transcript_revision_service.get_transcript,
    ai_chat_fn: Callable[..., str | None] = ai_client.chat,
) -> list[str]:
    """Return three validated Chinese display-title suggestions for an event."""
    safe_identifier(event_id)
    try:
        transcript = get_transcript_fn(event_id, connect_fn=connect_fn)
    except transcript_revision_service.EventNotFoundError as exc:
        raise EventNotFoundError(event_id) from exc
    content = transcript.active_content
    if not isinstance(content, str) or not content.strip():
        raise TranscriptUnavailableError
    response = ai_chat_fn(
        messages=[{"role": "user", "content": _suggestion_prompt(content)}],
        temperature=0.2,
        max_tokens=256,
        response_format={"type": "json_object"},
        module="event_title",
        task="suggestions",
        thinking=False,
    )
    return _parse_suggestions(response)
