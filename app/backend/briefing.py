"""AI-powered structured news briefing generation using DeepSeek API.

Produces topic-grouped Chinese overviews from translated RSS events.
Two modes: 'quick' (post-collection snapshot) and 'daily' (in-depth digest).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
import urllib.request
from typing import Any

from .db import connect, init_db

logger = logging.getLogger(__name__)

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


def _deepseek_api_key() -> str | None:
    key = os.getenv("DEEPSEEK_API_KEY", "")
    return key if key and key != "***" else None


def _deepseek_base_url() -> str:
    return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


def _call_deepseek(system_prompt: str, user_prompt: str, max_tokens: int = 4096, timeout: int = 120) -> str:
    """Call DeepSeek chat API and return the content string."""
    api_key = _deepseek_api_key()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not configured")

    payload: dict[str, Any] = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.5,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    data = json.dumps(payload).encode("utf-8")
    base_url = _deepseek_base_url().rstrip("/")
    url = f"{base_url}/v1/chat/completions"

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")[:300]
        except Exception as read_err:
            logger.warning("Failed to read DeepSeek error body: %s", read_err)
        msg = f"HTTP {e.code}: {error_body}"
        logger.warning("DeepSeek briefing HTTP error: %s", msg)
        raise RuntimeError(msg)
    except Exception as e:
        msg = str(e)[:300]
        logger.warning("DeepSeek briefing error: %s", msg)
        raise RuntimeError(msg)


def _fetch_translated_events(limit: int = 80) -> list[dict[str, Any]]:
    """Fetch events that have Chinese translations and are in 'new' status."""
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, source_id, title, title_cn, raw_summary, summary_cn, topic, url,
                   importance, created_at
            FROM events
            WHERE status = 'new'
              AND title_cn IS NOT NULL
              AND source_id NOT IN ('douyin', 'user-upload')
            ORDER BY importance DESC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def _build_events_text(events: list[dict[str, Any]]) -> str:
    """Build a compact text representation of events for the AI prompt."""
    lines = []
    for evt in events:
        title_cn = evt.get("title_cn") or evt.get("title", "")
        summary_cn = evt.get("summary_cn") or evt.get("raw_summary", "")
        source = SOURCE_LABELS.get(evt.get("source_id", ""), evt.get("source_id", ""))
        summary_short = summary_cn[:800] if summary_cn else "无摘要"
        lines.append(
            f"- [{evt['id']}] {source} | {title_cn}\n  摘要: {summary_short}"
        )
    return "\n".join(lines)


def generate_briefing(briefing_type: str = "quick", limit: int = 80) -> dict[str, Any]:
    """Generate a structured Chinese news briefing.

    Args:
        briefing_type: 'quick' for post-collection snapshot, 'daily' for in-depth digest.
        limit: Max events to include.

    Returns:
        Dict with keys: id, type, topics_json, events_used, created_at.
    """
    events = _fetch_translated_events(limit=limit)

    if not events:
        raise RuntimeError("No translated events available for briefing generation")

    # Group by topic for context in the prompt
    topic_groups: dict[str, list[dict[str, Any]]] = {}
    for evt in events:
        topic = evt.get("topic") or "uncategorized"
        topic_groups.setdefault(topic, []).append(evt)

    events_text = _build_events_text(events)

    is_quick = briefing_type == "quick"

    system_prompt = (
        "你是一个专业的新闻编辑。根据提供的新闻事件列表，生成一份结构化的中文新闻概览。\n\n"
        "要求：\n"
        "1. 按 topic 分组，每组写一个概述段落（2-4句话），概括该主题的整体趋势和关键发展\n"
        "2. 每组下列出重要事件的要点，每条事件给出 event_id、title_cn（直接用原文）、highlight（一句话亮点）\n"
        "3. 输出严格的 JSON 格式，结构如下：\n"
        '  {"topics": [{"topic": "...", "topic_label": "...", "summary": "...", '
        '"events": [{"event_id": "...", "title_cn": "...", "highlight": "...", "source_name": "..."}]}]}\n'
        "4. topic_label 使用中文标签\n"
        "5. 每个 topic 最多选 6 条最重要的事件\n"
        + ("6. 风格简洁快速，适合即时快报\n" if is_quick else "6. 风格深度分析，适合每日新闻日报，可以加入趋势解读\n")
        + "7. highlight 控制在 30 字以内"
    )

    user_prompt = f"请根据以下新闻事件生成{'即时快报' if is_quick else '每日深度日报'}：\n\n{events_text}"

    raw = _call_deepseek(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=4096, timeout=120)

    # Parse and validate the AI response
    try:
        parsed = json.loads(raw)
        topics_data = parsed.get("topics", [])
        if not isinstance(topics_data, list):
            raise ValueError("AI response 'topics' is not a list")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse AI briefing response: %s\nRaw: %s", e, raw[:500])
        raise RuntimeError(f"AI generated invalid JSON: {e}")

    # Count events referenced
    events_used = sum(len(t.get("events", [])) for t in topics_data)

    briefing_id = f"briefing-{uuid.uuid4().hex[:12]}"
    topics_json = json.dumps(topics_data, ensure_ascii=False)

    init_db()
    with connect() as conn:
        conn.execute(
            "INSERT INTO briefings (id, type, topics_json, events_used) VALUES (?, ?, ?, ?)",
            (briefing_id, briefing_type, topics_json, events_used),
        )

    return {
        "id": briefing_id,
        "type": briefing_type,
        "topics": topics_data,
        "events_used": events_used,
    }


def latest_briefing(briefing_type: str = "quick") -> dict[str, Any] | None:
    """Get the latest briefing of the given type."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, type, topics_json, events_used, created_at FROM briefings WHERE type = ? ORDER BY created_at DESC LIMIT 1",
            (briefing_type,),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["topics"] = json.loads(d.pop("topics_json"))
    except json.JSONDecodeError:
        d["topics"] = []
    return d
