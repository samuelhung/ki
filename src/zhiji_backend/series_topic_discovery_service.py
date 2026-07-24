"""Topic-scoped AI discovery for thematic series."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from .db import connect, init_db
from .series_candidate_service import persist_discovered_candidates

type ConnectFn = Callable[[], AbstractContextManager[sqlite3.Connection]]
type InitDbFn = Callable[[], None]
type ChatFn = Callable[..., str | None]

logger = logging.getLogger("zhiji_backend.routes.series_routes")


def discover_by_topic(
    data: dict[str, Any],
    *,
    connect_fn: ConnectFn = connect,
    init_db_fn: InitDbFn = init_db,
    chat_fn: ChatFn,
) -> dict[str, Any]:
    """Discover candidate series related to a user-provided topic."""
    init_db_fn()
    topic = data.get("topic", "").strip()
    if not topic:
        return {"message": "请输入主题关键词", "series": []}

    keywords = [kw.strip() for kw in topic.split() if len(kw.strip()) >= 1]
    if len(keywords) == 1 and not keywords[0].isascii():
        chars = keywords[0]
        keywords = []
        for i in range(len(chars) - 1):
            bigram = chars[i : i + 2]
            if bigram not in keywords:
                keywords.append(bigram)
        if not keywords:
            keywords = [chars]
    if not keywords:
        return {"message": "关键词无效", "series": []}

    with connect_fn() as conn:
        conditions = []
        params = []
        for kw in keywords:
            like = f"%{kw}%"
            conditions.append("(title LIKE ? OR overview LIKE ?)")
            params.extend([like, like])
        where = " OR ".join(conditions)

        event_rows = conn.execute(
            f"SELECT id, title, overview FROM events "
            f"WHERE overview IS NOT NULL AND overview != '' AND status != 'error' AND ({where}) "
            f"ORDER BY created_at DESC LIMIT 30",
            params,
        ).fetchall()

    if len(event_rows) < 2:
        return {"message": f"与「{topic}」相关的内容不足 2 条", "series": []}

    events_text = ""
    for ev in event_rows:
        ov = ev["overview"] or ""
        events_text += f"\n### 事件ID: {ev['id']}\n标题: {ev['title']}\n概述: {ov}\n"

    prompt = f"""你是知识专题策展人。用户对「{topic}」主题感兴趣，请在以下相关内容中聚类成 1-3 个有意义的专题系列。

事件列表：
{events_text}

要求：
- 每个专题需包含至少 2 条事件
- 为每个专题生成简洁的名称（≤20字）和一句话描述（≤80字）
- member_ids 必须使用上面给出的真实"事件ID"值
- 一条内容可以属于多个专题
- 输出 JSON 数组，格式：[{{"name": "...", "description": "...", "member_ids": ["真实的event_id", ...], "rationale": "为什么这些内容构成一个专题"}}]
- 直接输出 JSON，不要 Markdown 包裹"""

    messages = [
        {
            "role": "system",
            "content": "你是知识专题策展人。输出纯 JSON 数组，每个元素包含 name/description/member_ids/rationale。",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        raw = chat_fn(
            messages,
            temperature=0.4,
            max_tokens=4096,
            timeout=120,
            response_format={"type": "json_object"},
            module="series",
            task="discover_by_topic",
        )
        if not raw:
            return {"message": "AI 未返回结果", "series": []}

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n```$", "", raw)

        candidates = json.loads(raw)
        if not isinstance(candidates, list):
            return {"message": "AI 返回格式异常", "series": []}

        for candidate in candidates:
            candidate["member_ids"] = [
                member_id.strip().lstrip("[").rstrip("]")
                for member_id in candidate.get("member_ids", [])
            ]

        persisted, skipped_dupes, _ = persist_discovered_candidates(
            candidates, connect_fn=connect_fn
        )
        return {
            "series": persisted,
            "duplicates_skipped": len(skipped_dupes),
            "duplicates": skipped_dupes if skipped_dupes else [],
            "matched_events": len(event_rows),
        }

    except (json.JSONDecodeError, Exception) as e:
        logger.exception("By-topic discovery failed")
        return {"message": f"按主题发现失败: {str(e)[:200]}", "series": []}
