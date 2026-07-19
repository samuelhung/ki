"""AI-powered structured news briefing generation using the configured AI API.

Produces topic-grouped Chinese overviews from translated RSS events.
Two modes: 'quick' (post-collection snapshot) and 'daily' (in-depth digest).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from .db import connect, init_db
from .ai_client import chat

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


def _call_ai(system_prompt: str, user_prompt: str, max_tokens: int = 4096, timeout: int = 120,
                   module: str = "digest_briefing", task: str = "briefing_quick") -> str:
    """Call the configured AI API and return the content string."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    content = chat(messages, temperature=0.5, max_tokens=max_tokens, response_format={"type": "json_object"}, timeout=timeout,
                   module=module, task=task)
    if content is None:
        raise RuntimeError("AI API not configured or call failed")
    return content


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
            ORDER BY created_at DESC, importance DESC
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
        '  {"topics": [{"topic": "...", "topic_label": "中文标签", "summary": "中文概述", '
        '"events": [{"event_id": "...", "title_cn": "...", "highlight": "中文亮点", "source_name": "..."}]}]}\n'
        "4. topic_label 使用中文标签\n"
        "5. 每个 topic 最多选 6 条最重要的事件\n"
        + ("6. 风格简洁快速，适合即时快报\n" if is_quick else "6. 风格深度分析，适合每日新闻日报，可以加入趋势解读\n")
        + "7. highlight 控制在 30 字以内，必须使用中文\n"
        + "8. summary 必须使用中文，不得出现英文"
    )

    user_prompt = f"请根据以下新闻事件生成{'即时快报' if is_quick else '每日深度日报'}：\n\n{events_text}"

    raw = _call_ai(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=4096, timeout=120,
                        task="briefing_quick" if is_quick else "briefing_daily")

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

    # Enrich events with created_at from DB
    event_map: dict[str, str] = {e["id"]: e.get("created_at", "") for e in events}
    for topic in topics_data:
        for evt in topic.get("events", []):
            eid = evt.get("event_id", "")
            if eid in event_map:
                evt["created_at"] = event_map[eid]

    briefing_id = f"briefing-{uuid.uuid4().hex[:12]}"
    topics_json = json.dumps(topics_data, ensure_ascii=False)

    init_db()
    with connect() as conn:
        conn.execute(
            "INSERT INTO briefings (id, type, topics_json, events_used) VALUES (?, ?, ?, ?)",
            (briefing_id, briefing_type, topics_json, events_used),
        )

    # Batch contemplate: evaluate relevance to brainstorm questions (non-blocking best-effort)
    try:
        _batch_contemplate_briefing_events(topics_data)
    except Exception as e:
        logger.warning("Batch contemplate failed for briefing %s: %s", briefing_id, e)

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

    # Enrich events with brainstorm relevance if cache exists
    _enrich_briefing_relevance(d["topics"])

    return d


def list_briefings(limit: int = 30, offset: int = 0) -> dict[str, Any]:
    """Return compact briefing history metadata and the total row count."""
    limit = max(1, min(limit, 100))
    offset = max(offset, 0)

    init_db()
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM briefings").fetchone()[0]
        rows = conn.execute(
            """
            SELECT id, type, events_used, json_array_length(topics_json) AS topic_count,
                   created_at
            FROM briefings
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    return {
        "items": [dict(row) for row in rows],
        "total": total,
    }


def get_briefing(briefing_id: str) -> dict[str, Any] | None:
    """Return one parsed briefing, including topics, or None."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, type, topics_json, events_used, created_at
            FROM briefings
            WHERE id = ?
            """,
            (briefing_id,),
        ).fetchone()

    if row is None:
        return None

    briefing = dict(row)
    try:
        briefing["topics"] = json.loads(briefing.pop("topics_json"))
    except json.JSONDecodeError:
        briefing["topics"] = []

    _enrich_briefing_relevance(briefing["topics"])
    return briefing


def _enrich_briefing_relevance(topics: list[dict[str, Any]]) -> None:
    """Add brainstorm relevance labels to briefing events from cache."""
    # Collect all event_ids in this briefing
    event_ids: list[str] = []
    for t in topics:
        for evt in t.get("events", []):
            eid = evt.get("event_id", "")
            if eid:
                event_ids.append(eid)

    if not event_ids:
        return

    init_db()
    with connect() as conn:
        placeholders = ",".join(["?"] * len(event_ids))
        rows = conn.execute(
            f"""SELECT event_id, relevance
                FROM brainstorm_contemplate_cache
                WHERE event_id IN ({placeholders})
                AND relevance IN ('high', 'medium')
                ORDER BY CASE relevance WHEN 'high' THEN 1 WHEN 'medium' THEN 2 END""",
            event_ids,
        ).fetchall()

    # Build map: event_id -> {"high": N, "medium": N}
    relevance_map: dict[str, dict[str, int]] = {}
    for r in rows:
        m = relevance_map.setdefault(r["event_id"], {"high": 0, "medium": 0})
        m[r["relevance"]] += 1

    # Inject into topics
    for t in topics:
        for evt in t.get("events", []):
            eid = evt.get("event_id", "")
            if eid in relevance_map:
                evt["relevance"] = relevance_map[eid]


def _batch_contemplate_briefing_events(topics: list[dict[str, Any]]) -> None:
    """After briefing generation, batch-evaluate all referenced events against
    open brainstorm questions in a single AI call. Results are stored in
    brainstorm_contemplate_cache for subsequent lookups."""

    # Collect unique event IDs from briefing topics
    event_ids: list[str] = []
    seen: set[str] = set()
    for t in topics:
        for evt in t.get("events", []):
            eid = evt.get("event_id", "")
            if eid and eid not in seen:
                event_ids.append(eid)
                seen.add(eid)

    if not event_ids:
        return

    # Get event content
    init_db()
    with connect() as conn:
        placeholders = ",".join(["?"] * len(event_ids))
        rows = conn.execute(
            f"""SELECT id, title_cn, summary_cn, ai_summary
                FROM events WHERE id IN ({placeholders})""",
            event_ids,
        ).fetchall()
    events_data: dict[str, dict] = {r["id"]: dict(r) for r in rows}

    # Get open questions
    with connect() as conn:
        q_rows = conn.execute(
            "SELECT id, question FROM brainstorm_questions WHERE status = 'open' ORDER BY created_at DESC LIMIT 40"
        ).fetchall()
    questions = [dict(r) for r in q_rows]

    if not questions:
        return

    # Check already-cached pairs
    with connect() as conn:
        cached_rows = conn.execute(
            f"""SELECT question_id, event_id, relevance
                FROM brainstorm_contemplate_cache
                WHERE event_id IN ({placeholders})""",
            event_ids,
        ).fetchall()
    cached_pairs: set[tuple[str, str]] = {(r["question_id"], r["event_id"]) for r in cached_rows}

    # Build prompt: event summaries + question list
    event_lines: list[str] = []
    for i, eid in enumerate(event_ids):
        evt = events_data.get(eid, {})
        title = evt.get("title_cn") or ""
        summary = (evt.get("summary_cn") or evt.get("ai_summary") or "")[:350]
        event_lines.append(f"[事件{i}] {title}\n  {summary}")

    question_lines: list[str] = []
    for j, q in enumerate(questions):
        question_lines.append(f"[问题{j}] {q['question']}")

    system_prompt = (
        "你是一个内容匹配助手。以下是一组新闻事件和一组研究问题。\n"
        "对每个事件-问题组合，判断该事件能否帮助回答该问题：\n"
        "- high: 事件直接涉及该问题主题，可作为核心素材\n"
        "- medium: 事件部分相关或可提供背景参考\n"
        "- low: 完全无关（跳过不输出）\n"
        "只输出 JSON 数组，严格按以下格式，不要其他内容：\n"
        '[{"event_index": 0, "question_index": 3, "relevance": "high", "reason": "直接相关"}, ...]\n'
        "只输出 high 或 medium 的项，low 的跳过。reason 用中文，10字以内。"
    )

    user_prompt = (
        "新闻事件：\n" + "\n".join(event_lines) + "\n\n"
        "研究问题：\n" + "\n".join(question_lines)
    )

    try:
        raw = _call_ai(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=4096, timeout=180)
        matches = json.loads(raw)
        if not isinstance(matches, list):
            logger.warning("Batch contemplate: AI returned non-list, got %s", type(matches).__name__)
            return
    except Exception as e:
        logger.warning("Batch contemplate AI call failed: %s", e)
        return

    # Persist results
    matched_set: set[tuple[int, int]] = set()
    with connect() as conn:
        for m in matches:
            ei = m.get("event_index", -1)
            qi = m.get("question_index", -1)
            if not isinstance(ei, int) or not isinstance(qi, int):
                continue
            if ei < 0 or ei >= len(event_ids) or qi < 0 or qi >= len(questions):
                continue
            matched_set.add((ei, qi))
            eid = event_ids[ei]
            q = questions[qi]
            relevance = m.get("relevance", "medium")
            if relevance not in ("high", "medium"):
                relevance = "medium"
            reason = str(m.get("reason", ""))[:50]
            conn.execute(
                "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                (q["id"], eid, relevance, reason),
            )

        # Cache unmatched as low (only if not already cached)
        for ei, eid in enumerate(event_ids):
            for qi, q in enumerate(questions):
                if (ei, qi) not in matched_set and (q["id"], eid) not in cached_pairs:
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (q["id"], eid, "low", ""),
                    )

    high_count = sum(1 for m in matches if m.get("relevance") == "high")
    medium_count = sum(1 for m in matches if m.get("relevance") == "medium")
    logger.info(
        "Batch contemplate done: %d events × %d questions → %d high, %d medium",
        len(event_ids), len(questions), high_count, medium_count,
    )
