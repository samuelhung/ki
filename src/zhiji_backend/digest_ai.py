"""AI-powered daily digest generation using the configured AI API.

Produces structured Markdown digest from today's new events, including:
- Headline summary
- Topic-by-topic analysis
- QA pairs extracted from content
- Expandable follow-up questions
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect, init_db
from .paths import DATA_DIR
from .ai_client import chat

logger = logging.getLogger(__name__)


def _call_ai_text(
    system_prompt: str, user_prompt: str,
    max_tokens: int = 8192, timeout: int = 180,
) -> str:
    """Call the configured AI API for free-text (non-JSON) output."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    content = chat(messages, temperature=0.5, max_tokens=max_tokens, timeout=timeout,
                   module="digest_briefing", task="digest")
    if content is None:
        raise RuntimeError("AI API not configured or call failed")
    return content


def today_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def digest_dir() -> Path:
    configured = os.getenv("KI_DIGESTS_DIR")
    if configured:
        path = Path(configured).expanduser().resolve()
    else:
        path = DATA_DIR / "digests"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fetch_today_events() -> list[dict[str, Any]]:
    """Fetch all events created today (UTC)."""
    init_db()
    today = today_key()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, source_id, title, title_cn, url, topic,
                   raw_summary, summary_cn, ai_summary, importance, created_at
            FROM events
            WHERE date(created_at) = date('now', 'utc')
            ORDER BY importance DESC, created_at DESC
            """,
        ).fetchall()
    return [dict(row) for row in rows]


def _build_events_context(events: list[dict[str, Any]]) -> str:
    """Build compact text representation of events for the AI prompt."""
    lines = []
    for i, evt in enumerate(events, 1):
        source_id = evt.get("source_id", "")

        # RSS events: prefer Chinese translations
        if source_id not in ("douyin", "user-upload"):
            title = evt.get("title_cn") or evt.get("title", "")
            summary = evt.get("summary_cn") or evt.get("raw_summary") or ""
            source_label = "RSS"
        else:
            title = evt.get("title", "")
            summary = evt.get("ai_summary") or evt.get("raw_summary") or ""
            source_label = "抖音/上传" if source_id == "douyin" else "用户上传"

        topic = evt.get("topic") or "未分类"
        summary_short = summary[:500] if summary else "无摘要"

        lines.append(
            f"[{i}] 来源:{source_label} 主题:{topic}\n"
            f"    标题: {title}\n"
            f"    摘要: {summary_short}"
        )

    return "\n\n".join(lines)


def _simple_digest(date_key: str, events: list[dict[str, Any]],
                   total_count: int, topic_set: list[str]) -> str:
    """Simple template-based digest (fallback when AI is unavailable)."""
    lines = [
        f"# 每日摘要 - {date_key}",
        "",
        f"## 今日要闻",
        f"共收录 {total_count} 条新增记录，覆盖 {len(topic_set)} 个主题。",
        "",
    ]

    from collections import defaultdict
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for evt in events:
        grouped[evt.get("topic") or "未分类"].append(evt)

    for topic in sorted(grouped):
        lines.append(f"## {topic}")
        for evt in grouped[topic]:
            source_id = evt.get("source_id", "")
            if source_id not in ("douyin", "user-upload"):
                title = evt.get("title_cn") or evt.get("title", "")
            else:
                title = evt.get("title", "")
            url = evt.get("url", "")
            if url and url.startswith("http"):
                lines.append(f"- [{title}]({url})")
            else:
                lines.append(f"- {title}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def generate_ai_digest() -> dict[str, Any]:
    """Generate an AI-powered structured Markdown digest from today's events.

    Returns:
        Dict with keys: date, markdown, events_used.
    """
    date_key = today_key()
    events = _fetch_today_events()
    total_count = len(events)
    topic_set = sorted({e.get("topic") or "未分类" for e in events})

    if not events:
        markdown = f"# 每日摘要 - {date_key}\n\n今日暂无新增记录。\n"
        _save_digest(date_key, markdown, 0)
        return {"date": date_key, "markdown": markdown, "events_used": 0, "action_candidates_created": 0}

    events_context = _build_events_context(events)

    system_prompt = f"""你是一个专业的信息分析师。请根据今天新增的信息记录，生成一份结构化的每日摘要。

输出格式（严格遵循以下 Markdown 结构）：

# 每日摘要 - {date_key}

## 今日要闻
[一段话总结今日最重要的发现或趋势，2-4句话，概括全局]

## 📊 事件总览
共收录 {total_count} 条新增记录，覆盖 {len(topic_set)} 个主题：{', '.join(topic_set)}。

## [主题名，每个主题一个 ## 二级标题]
[该主题趋势概述，1-2句话]
- [事件标题](url) — 一句话要点（≤25字）

## ❓ 今日关键问答
[从当天信息中提炼 3-5 个关键问题和答案，格式如下]

### Q: [问题]
A: [基于当天信息的回答，2-3句话，可引用具体事件]

### Q: [下一个问题]
A: [回答]

## 🔍 可拓展问题
- [开放性问题1]（可深入方向: [简要提示]）
- [开放性问题2]（可深入方向: [简要提示]）

重要规则：
- "今日关键问答"每个 Q 必须基于当天信息提炼，答案必须能追溯到具体事件
- "可拓展问题"是当天信息未直接回答、但值得进一步探讨的开放性问题，3-5个
- 事件要点每条 25 字以内，每个主题最多选 5 条最重要的
- **只摘取最核心的事件，不要逐条罗列所有 {total_count} 条**
- **所有输出使用中文**
- 不要输出任何前言后语，直接从 "# 每日摘要" 第一行开始"""

    user_prompt = (
        f"以下是今天({date_key})新增的 {total_count} 条信息记录。\n"
        f"请仔细阅读并生成每日摘要。只取最核心、最重要的内容。\n\n"
        f"{events_context}"
    )

    logger.info("Generating AI digest for %s with %d events", date_key, total_count)

    # Try AI generation; fall back to simple digest if AI fails
    markdown = None
    try:
        markdown = _call_ai_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=8192,
            timeout=180,
        )
    except RuntimeError:
        logger.exception("AI API failed for digest %s, falling back to simple digest", date_key)

    if not markdown:
        # Fallback: simple template-based digest
        markdown = _simple_digest(date_key, events, total_count, topic_set)
        logger.info("Used simple digest for %s (no AI)", date_key)

    markdown = markdown.strip() + "\n"
    _save_digest(date_key, markdown, total_count)

    logger.info("AI digest saved: %s, %d events, %d chars",
                date_key, total_count, len(markdown))

    return {
        "date": date_key,
        "markdown": markdown,
        "events_used": total_count,
        "action_candidates_created": 0,
    }


def _save_digest(date_key: str, markdown: str, events_used: int) -> None:
    """Write digest to both SQLite and data/digests/YYYY-MM-DD.md."""
    init_db()

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO digests (date, markdown, events_used, action_candidates_created)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(date) DO UPDATE SET
              markdown = excluded.markdown,
              events_used = excluded.events_used,
              updated_at = CURRENT_TIMESTAMP
            """,
            (date_key, markdown, events_used),
        )

    md_path = digest_dir() / f"{date_key}.md"
    md_path.write_text(markdown, encoding="utf-8")
    logger.info("Digest MD saved: %s", md_path)


def latest_digest() -> dict[str, Any]:
    """Get the latest digest from SQLite."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT date, markdown, events_used, action_candidates_created, updated_at
            FROM digests
            ORDER BY date DESC
            LIMIT 1
            """
        ).fetchone()

    if row:
        return dict(row)
    return generate_ai_digest()
