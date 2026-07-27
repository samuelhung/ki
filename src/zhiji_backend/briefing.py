"""Compatibility facade for briefing generation and persistence."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from . import briefing_generation_service as _generation_service
from . import briefing_repository as _repository
from .ai_client import chat
from .db import connect, init_db

logger = logging.getLogger(__name__)

MAX_SQLITE_OFFSET = 9_223_372_036_854_775_807

TOPIC_LABELS: dict[str, str] = {
    "world": "国际",
    "business": "商业",
    "technology": "科技",
    "politics": "政治",
    "science": "科学",
    "health": "健康",
    "sports": "体育",
    "entertainment": "娱乐",
    "tech-ai": "科技/AI",
}

SOURCE_LABELS: dict[str, str] = {
    "bbc-world": "BBC 世界新闻",
    "bbc-top-stories": "BBC 头条",
    "bbc-business": "BBC 商业",
    "bbc-technology": "BBC 科技",
    "npr": "NPR",
    "al-jazeera": "半岛电视台",
    "reuters-world": "卫报",
    "nyt-world": "纽约时报",
}


def _call_ai(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4096,
    timeout: int = 120,
    module: str = "briefing",
    task: str = "briefing_quick",
) -> str:
    """Call the configured AI API and return the content string."""
    return _generation_service.call_ai(
        system_prompt,
        user_prompt,
        max_tokens,
        timeout,
        module,
        task,
        chat_fn=chat,
    )


def _fetch_translated_events(limit: int = 80) -> list[dict[str, Any]]:
    """Fetch translated events eligible for a briefing."""
    return _generation_service.fetch_translated_events(
        limit,
        connect_fn=connect,
        init_db_fn=init_db,
    )


def _build_events_text(events: list[dict[str, Any]]) -> str:
    """Build the compact event representation used in AI prompts."""
    return _generation_service.build_events_text(events, source_labels=SOURCE_LABELS)


def _parse_generated_topics(
    raw: str, allowed_event_ids: set[str]
) -> list[dict[str, Any]]:
    return _generation_service.parse_generated_topics(
        raw,
        allowed_event_ids,
        json_module=json,
        logger=logger,
    )


def generate_briefing(briefing_type: str = "quick", limit: int = 80) -> dict[str, Any]:
    """Generate and persist a structured Chinese news briefing."""
    briefing = _generation_service.generate_briefing(
        briefing_type,
        limit,
        call_ai_fn=_call_ai,
        fetch_events_fn=_fetch_translated_events,
        build_events_text_fn=_build_events_text,
        parse_generated_topics_fn=_parse_generated_topics,
        uuid_fn=uuid.uuid4,
    )
    _repository.persist_briefing(
        briefing,
        connect_fn=connect,
        init_db_fn=init_db,
        json_module=json,
    )
    try:
        _batch_contemplate_briefing_events(briefing["topics"])
    except Exception as exc:
        logger.warning(
            "Batch contemplate failed for briefing %s: %s", briefing["id"], exc
        )
    return briefing


def _parse_topics_json(topics_json: str) -> list[dict[str, Any]]:
    return _repository.parse_topics_json(topics_json, json_module=json)


def latest_briefing(briefing_type: str = "quick") -> dict[str, Any] | None:
    """Get the latest briefing of the given type."""
    briefing = _repository.latest_briefing(
        briefing_type,
        connect_fn=connect,
        init_db_fn=init_db,
        parse_topics_json_fn=_parse_topics_json,
    )
    if briefing is not None:
        _enrich_briefing_relevance(briefing["topics"])
    return briefing


def list_briefings(limit: int = 30, offset: int = 0) -> dict[str, Any]:
    """Return compact briefing history metadata and the total row count."""
    return _repository.list_briefings(
        limit,
        offset,
        connect_fn=connect,
        init_db_fn=init_db,
    )


def get_briefing(briefing_id: str) -> dict[str, Any] | None:
    """Return one parsed briefing, including topics, or None."""
    briefing = _repository.get_briefing(
        briefing_id,
        connect_fn=connect,
        init_db_fn=init_db,
        parse_topics_json_fn=_parse_topics_json,
    )
    if briefing is not None:
        _enrich_briefing_relevance(briefing["topics"])
    return briefing


def _enrich_briefing_relevance(topics: list[dict[str, Any]]) -> None:
    """Add cached brainstorm relevance labels to briefing events."""
    _repository.enrich_briefing_relevance(
        topics,
        connect_fn=connect,
        init_db_fn=init_db,
    )


def _batch_contemplate_briefing_events(topics: list[dict[str, Any]]) -> None:
    """Evaluate briefing events against open brainstorm questions."""
    _generation_service.batch_contemplate_briefing_events(
        topics,
        connect_fn=connect,
        init_db_fn=init_db,
        call_ai_fn=_call_ai,
        json_module=json,
        logger=logger,
    )
