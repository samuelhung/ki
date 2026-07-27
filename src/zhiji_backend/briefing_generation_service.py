"""Event selection and AI orchestration for news briefings."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("zhiji_backend.briefing")


def call_ai(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4096,
    timeout: int = 120,
    module: str = "briefing",
    task: str = "briefing_quick",
    *,
    chat_fn,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    content = chat_fn(
        messages,
        temperature=0.5,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        timeout=timeout,
        module=module,
        task=task,
    )
    if content is None:
        raise RuntimeError("AI API not configured or call failed")
    return content


def fetch_translated_events(
    limit: int = 80, *, connect_fn, init_db_fn
) -> list[dict[str, Any]]:
    init_db_fn()
    with connect_fn() as conn:
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


def build_events_text(
    events: list[dict[str, Any]], *, source_labels: dict[str, str]
) -> str:
    lines = []
    for event in events:
        title_cn = event.get("title_cn") or event.get("title", "")
        summary_cn = event.get("summary_cn") or event.get("raw_summary", "")
        source = source_labels.get(
            event.get("source_id", ""), event.get("source_id", "")
        )
        summary_short = summary_cn[:800] if summary_cn else "无摘要"
        lines.append(
            f"- [{event['id']}] {source} | {title_cn}\n  摘要: {summary_short}"
        )
    return "\n".join(lines)


def parse_generated_topics(
    raw: str, allowed_event_ids: set[str], *, json_module, logger
) -> list[dict[str, Any]]:
    try:
        parsed = json_module.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("AI response root is not an object")
        topics = parsed.get("topics", [])
        if not isinstance(topics, list):
            raise ValueError("AI response 'topics' is not a list")

        normalized_topics: list[dict[str, Any]] = []
        for topic_index, topic in enumerate(topics):
            if not isinstance(topic, dict):
                raise ValueError(f"AI response topic {topic_index} is not an object")
            events = topic.get("events", [])
            if not isinstance(events, list):
                raise ValueError(
                    f"AI response topic {topic_index} events is not a list"
                )
            normalized_events: list[dict[str, Any]] = []
            for event_index, event in enumerate(events):
                if not isinstance(event, dict):
                    raise ValueError(
                        f"AI response topic {topic_index} event {event_index} is not an object"
                    )
                event_id = event.get("event_id")
                if (
                    not isinstance(event_id, str)
                    or not event_id
                    or event_id not in allowed_event_ids
                ):
                    continue
                normalized_events.append(dict(event))
            normalized_topic = dict(topic)
            normalized_topic["events"] = normalized_events
            normalized_topics.append(normalized_topic)
        return normalized_topics
    except (json_module.JSONDecodeError, ValueError) as exc:
        logger.error(
            "Failed to parse AI briefing response: %s\nRaw: %s",
            exc,
            raw[:500],
        )
        raise RuntimeError(f"AI generated invalid JSON: {exc}") from exc


def _build_system_prompt(is_quick: bool) -> str:
    return (
        "你是一个专业的新闻编辑。根据提供的新闻事件列表，生成一份结构化的中文新闻概览。\n\n"
        "要求：\n"
        "1. 按 topic 分组，每组写一个概述段落（2-4句话），概括该主题的整体趋势和关键发展\n"
        "2. 每组下列出重要事件的要点，每条事件给出 event_id、title_cn（直接用原文）、highlight（一句话亮点）\n"
        "3. 输出严格的 JSON 格式，结构如下：\n"
        '  {"topics": [{"topic": "...", "topic_label": "中文标签", "summary": "中文概述", '
        '"events": [{"event_id": "...", "title_cn": "...", "highlight": "中文亮点", "source_name": "..."}]}]}\n'
        "4. topic_label 使用中文标签\n"
        "5. 每个 topic 最多选 6 条最重要的事件\n"
        + (
            "6. 风格简洁快速，适合即时快报\n"
            if is_quick
            else "6. 风格深度分析，适合每日新闻日报，可以加入趋势解读\n"
        )
        + "7. highlight 控制在 30 字以内，必须使用中文\n"
        "8. summary 必须使用中文，不得出现英文"
    )


def generate_briefing(
    briefing_type: str = "quick",
    limit: int = 80,
    *,
    call_ai_fn,
    fetch_events_fn,
    build_events_text_fn,
    parse_generated_topics_fn,
    uuid_fn,
) -> dict[str, Any]:
    events = fetch_events_fn(limit=limit)
    if not events:
        raise RuntimeError("No translated events available for briefing generation")

    events_text = build_events_text_fn(events)
    is_quick = briefing_type == "quick"
    system_prompt = _build_system_prompt(is_quick)
    user_prompt = f"请根据以下新闻事件生成{'即时快报' if is_quick else '每日深度日报'}：\n\n{events_text}"
    raw = call_ai_fn(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=4096,
        timeout=120,
        task="briefing_quick" if is_quick else "briefing_daily",
    )

    event_map: dict[str, str] = {}
    for event in events:
        event_id = event.get("id")
        if isinstance(event_id, str) and event_id:
            event_map[event_id] = event.get("created_at", "")
    topics_data = parse_generated_topics_fn(raw, set(event_map))
    events_used = sum(len(topic.get("events", [])) for topic in topics_data)
    for topic in topics_data:
        for event in topic.get("events", []):
            event_id = event.get("event_id", "")
            if event_id in event_map:
                event["created_at"] = event_map[event_id]

    briefing_id = f"briefing-{uuid_fn().hex[:12]}"
    return {
        "id": briefing_id,
        "type": briefing_type,
        "topics": topics_data,
        "events_used": events_used,
    }


def enrich_briefing_relevance(
    topics: list[dict[str, Any]], *, fetch_relevance_fn
) -> None:
    event_ids: list[str] = []
    for topic in topics:
        for event in topic.get("events", []):
            event_id = event.get("event_id", "")
            if event_id:
                event_ids.append(event_id)
    if not event_ids:
        return

    relevance_map: dict[str, dict[str, int]] = {}
    for row in fetch_relevance_fn(event_ids):
        counts = relevance_map.setdefault(row["event_id"], {"high": 0, "medium": 0})
        counts[row["relevance"]] += 1
    for topic in topics:
        for event in topic.get("events", []):
            event_id = event.get("event_id", "")
            if event_id in relevance_map:
                event["relevance"] = relevance_map[event_id]


def batch_contemplate_briefing_events(
    topics: list[dict[str, Any]],
    *,
    connect_fn,
    init_db_fn,
    call_ai_fn,
    json_module,
    logger,
) -> None:
    event_ids: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        for event in topic.get("events", []):
            event_id = event.get("event_id", "")
            if event_id and event_id not in seen:
                event_ids.append(event_id)
                seen.add(event_id)
    if not event_ids:
        return

    init_db_fn()
    with connect_fn() as conn:
        placeholders = ",".join(["?"] * len(event_ids))
        rows = conn.execute(
            f"""SELECT id, title_cn, summary_cn, ai_summary
                FROM events WHERE id IN ({placeholders})""",
            event_ids,
        ).fetchall()
    events_data: dict[str, dict] = {row["id"]: dict(row) for row in rows}

    with connect_fn() as conn:
        question_rows = conn.execute(
            "SELECT id, question FROM brainstorm_questions WHERE status = 'open' ORDER BY created_at DESC LIMIT 40"
        ).fetchall()
    questions = [dict(row) for row in question_rows]
    if not questions:
        return

    with connect_fn() as conn:
        cached_rows = conn.execute(
            f"""SELECT question_id, event_id, relevance
                FROM brainstorm_contemplate_cache
                WHERE event_id IN ({placeholders})""",
            event_ids,
        ).fetchall()
    cached_pairs = {(row["question_id"], row["event_id"]) for row in cached_rows}

    event_lines: list[str] = []
    for index, event_id in enumerate(event_ids):
        event = events_data.get(event_id, {})
        title = event.get("title_cn") or ""
        summary = (event.get("summary_cn") or event.get("ai_summary") or "")[:350]
        event_lines.append(f"[事件{index}] {title}\n  {summary}")
    question_lines = [
        f"[问题{index}] {question['question']}"
        for index, question in enumerate(questions)
    ]
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
        "新闻事件：\n"
        + "\n".join(event_lines)
        + "\n\n"
        + "研究问题：\n"
        + "\n".join(question_lines)
    )
    try:
        raw = call_ai_fn(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=4096,
            timeout=180,
        )
        matches = json_module.loads(raw)
        if not isinstance(matches, list):
            logger.warning(
                "Batch contemplate: AI returned non-list, got %s",
                type(matches).__name__,
            )
            return
    except Exception as exc:
        logger.warning("Batch contemplate AI call failed: %s", exc)
        return

    matched_set: set[tuple[int, int]] = set()
    with connect_fn() as conn:
        for match in matches:
            event_index = match.get("event_index", -1)
            question_index = match.get("question_index", -1)
            if not isinstance(event_index, int) or not isinstance(question_index, int):
                continue
            if (
                event_index < 0
                or event_index >= len(event_ids)
                or question_index < 0
                or question_index >= len(questions)
            ):
                continue
            matched_set.add((event_index, question_index))
            event_id = event_ids[event_index]
            question = questions[question_index]
            relevance = match.get("relevance", "medium")
            if relevance not in ("high", "medium"):
                relevance = "medium"
            reason = str(match.get("reason", ""))[:50]
            conn.execute(
                "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                (question["id"], event_id, relevance, reason),
            )

        for event_index, event_id in enumerate(event_ids):
            for question_index, question in enumerate(questions):
                if (event_index, question_index) not in matched_set and (
                    question["id"],
                    event_id,
                ) not in cached_pairs:
                    conn.execute(
                        "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
                        (question["id"], event_id, "low", ""),
                    )

    high_count = sum(1 for match in matches if match.get("relevance") == "high")
    medium_count = sum(1 for match in matches if match.get("relevance") == "medium")
    logger.info(
        "Batch contemplate done: %d events × %d questions → %d high, %d medium",
        len(event_ids),
        len(questions),
        high_count,
        medium_count,
    )
