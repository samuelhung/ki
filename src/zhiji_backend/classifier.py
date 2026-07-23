"""Content classifier — assigns one of four cognitive layers to non-RSS events.

Uses the configured AI API to classify content into:
  格局 (geopolitics), 财富 (finance/business), 认知 (cognition/methodology), 前瞻 (technology/trends)
"""

from __future__ import annotations

import logging

from .ai_client import chat
from .db import connect, init_db

logger = logging.getLogger(__name__)

CATEGORIES = ["格局", "财富", "认知", "前瞻"]


def classify_content(title: str, text: str) -> str:
    """Classify content into one of four cognitive layers. Returns the label string."""

    snippet = text[:2000] if len(text) > 2000 else text

    system_prompt = (
        "你是一个内容分类助手。根据以下内容，判断它属于哪个认知层次，只输出一个词。\n\n"
        "四个类别：\n"
        "- 格局：地缘政治、大国博弈、战争冲突、国际关系、外交战略\n"
        "- 财富：金融、投资、商业、货币、产业分析、公司估值、贸易\n"
        "- 认知：历史规律、文明演化、宗教哲学、思维模型、方法论、个人成长\n"
        "- 前瞻：AI、能源、航天、芯片、科技突破、未来趋势判断、产业前瞻\n\n"
        "规则：\n"
        "1. 如果内容在讲国际局势、地缘冲突、大国关系 → 格局\n"
        "2. 如果内容在讲钱怎么流动、投资理财、商业分析 → 财富\n"
        "3. 如果内容在讲历史规律、文明比较、怎么思考、个人提升 → 认知\n"
        "4. 如果内容在讲新技术、未来趋势、科技突破 → 前瞻\n"
        "5. 只输出一个词：格局、财富、认知 或 前瞻\n"
        "6. 不要输出任何其他内容"
    )

    user_prompt = f"标题：{title}\n\n内容：{snippet}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    label = chat(messages, temperature=0.1, max_tokens=16, timeout=30,
                 module="ingest_pipeline", task="classify")
    if label is None:
        logger.warning("Classification failed — returning default '认知'")
        return "认知"

    # Normalize output
    for cat in CATEGORIES:
        if cat in label:
            return cat

    logger.warning("Unexpected classifier output: %s, defaulting to 认知", label[:50])
    return "认知"


def classify_event(event_id: str) -> str | None:
    """Classify a single event and update its topic. Returns the label or None."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT title, title_cn, summary_cn, raw_summary, ai_summary FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()

    if not row:
        return None

    title = row["title_cn"] or row["title"] or ""
    text = (
        row["ai_summary"]
        or row["summary_cn"]
        or row["raw_summary"]
        or ""
    )

    if not text.strip():
        logger.info("Event %s has no text content, skipping classification", event_id)
        return None

    label = classify_content(title, text)

    with connect() as conn:
        conn.execute(
            "UPDATE events SET topic = ? WHERE id = ?",
            (label, event_id),
        )

    logger.info("Classified event %s as %s", event_id, label)
    return label


def classify_batch(source_ids: list[str] | None = None, limit: int = 200) -> dict[str, int]:
    """Classify all unclassified non-RSS events. Returns counts by category."""
    init_db()
    counts = {cat: 0 for cat in CATEGORIES}
    counts["skipped"] = 0

    source_filter = source_ids if source_ids else ['douyin', 'user-upload']
    placeholders = ','.join(['?' for _ in source_filter])
    query = """
        SELECT id, title, title_cn, summary_cn, raw_summary, ai_summary
        FROM events
        WHERE source_id IN ({placeholders})
          AND (topic IS NULL OR topic NOT IN ('格局','财富','认知','前瞻')
               OR topic IN ('uncategorized','', 'meeting','test','psychology','uncategorized'))
        ORDER BY created_at DESC
        LIMIT ?
    """.replace('{placeholders}', placeholders)
    params = source_filter + [limit]
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()

    for row in rows:
        title = row["title_cn"] or row["title"] or ""
        text = (
            row["ai_summary"]
            or row["summary_cn"]
            or row["raw_summary"]
            or ""
        )
        if not text.strip():
            counts["skipped"] += 1
            continue

        label = classify_content(title, text)
        if label not in CATEGORIES:
            counts["skipped"] += 1
            continue

        with connect() as conn:
            conn.execute(
                "UPDATE events SET topic = ? WHERE id = ?",
                (label, row["id"]),
            )
        counts[label] += 1

    logger.info("Batch classification done: %s", counts)
    return counts
