"""AI-powered affairs analysis — FTS retrieval + contemplate cache + LLM judgment."""

from __future__ import annotations

import json
import logging
from typing import Any

from .deepseek_client import chat

logger = logging.getLogger(__name__)

JUDGMENT_SYSTEM_PROMPT = """你是综合事务分析助手。用户提交了一个事务，你需要综合知识情报中心的已有信息，给出结构化判断。

规则：
- 严格基于用户提供的事务正文和检索到的相关信息
- 不要编造知识库中不存在的事实
- 每条判断必须有依据
- related_events 和 related_questions 只从 search_hits 中选取，不要编造 ID
- 仅输出 JSON，不要输出其他内容

输出 JSON 格式：
{
  "category": "行动建议 | 信息核实 | 趋势判断 | 风险预警 | 其他",
  "summary": "一句话概述",
  "judgment": "综合判断（Markdown）",
  "recommended_action": "建议的具体行动",
  "priority": "高 | 中 | 低",
  "confidence": "高 | 中 | 低",
  "key_insights": ["发现1", "发现2"],
  "risk_factors": ["风险点1"],
  "related_events": [
    {"event_id": "xxx", "title": "原标题", "relevance_reason": "为什么相关"}
  ],
  "related_questions": [
    {"question_id": "xxx", "question": "原问题", "relevance_reason": "为什么相关"}
  ]
}"""


def analyze_affair(affair_id: str, body: str) -> dict | None:
    """Run the full analysis pipeline for a given affair.

    Returns the parsed judgment JSON dict, or None on failure.
    """
    from .db import connect

    # ── Step 1: FTS search for related events ──
    related_events = _fts_search(body)
    logger.info("Affair %s: FTS returned %d related events", affair_id, len(related_events))

    # ── Step 2: Find related brainstorm questions from contemplate cache ──
    related_questions = _find_related_questions(related_events)
    logger.info("Affair %s: found %d related questions", affair_id, len(related_questions))

    # ── Step 3: Build prompt ──
    search_context = _build_search_context(related_events, related_questions)

    user_prompt = f"""事务正文：
{body}

知识库中检索到的相关信息：
{search_context}

请基于以上信息，对该事务给出结构化判断。"""

    # ── Step 4: LLM call ──
    content = chat(
        [
            {"role": "system", "content": JUDGMENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=4096,
        timeout=180,
        module="affairs",
        task="judge",
    )
    if not content:
        logger.warning("Affair %s: AI judgment returned empty", affair_id)
        return None

    try:
        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if lines[0].startswith("```") else content
            if content.endswith("```"):
                content = content[:-3].strip()
        result = json.loads(content)
        logger.info("Affair %s: AI judgment generated", affair_id)
        return result
    except Exception as e:
        logger.warning("Affair %s: AI analysis failed: %s", affair_id, e)
        return None


def _fts_search(query: str, limit: int = 10) -> list[dict]:
    """Full-text search events matching the query.
    
    Strategy: extract character n-grams for Chinese text → try FTS5 → fall back to LIKE.
    """
    from .db import connect

    if not query or not query.strip():
        return []

    raw = query.strip()[:300]
    
    # Extract Chinese character n-grams (bigrams + trigrams) plus space-delimited words
    terms = _extract_search_terms(raw)
    if not terms:
        return []
    
    fts_query = " ".join(terms[:20])

    rows = []
    try:
        with connect() as conn:
            rows = conn.execute(
                """SELECT e.id, e.title, e.title_cn, e.raw_summary, e.summary_cn,
                          e.topic, e.source_id, e.created_at
                   FROM events_fts f
                   JOIN events e ON f.event_id = e.id
                   WHERE events_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, limit),
            ).fetchall()
    except Exception as e:
        logger.debug("FTS search failed: %s, falling back to LIKE", e)

    # Fallback to LIKE if FTS returned nothing
    if not rows:
        with connect() as conn:
            like_terms = terms[:12]
            if not like_terms:
                return []
            clauses = []
            params = []
            for term in like_terms:
                like = f"%{term}%"
                clauses.append("(e.title LIKE ? OR e.title_cn LIKE ? OR e.raw_summary LIKE ? OR e.summary_cn LIKE ?)")
                params.extend([like, like, like, like])
            sql = f"""SELECT e.id, e.title, e.title_cn, e.raw_summary, e.summary_cn,
                             e.topic, e.source_id, e.created_at
                      FROM events e
                      WHERE {' OR '.join(clauses)}
                      ORDER BY e.created_at DESC
                      LIMIT ?"""
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()

    return [dict(r) for r in rows]


def _extract_search_terms(text: str) -> list[str]:
    """Extract meaningful search terms from mixed Chinese/English text.
    
    For Chinese: generates overlapping bigrams and trigrams.
    For English: splits on whitespace/punctuation.
    Removes common noise terms and deduplicates.
    """
    import re
    terms = set()
    
    # Chinese characters (CJK range)
    cjk_pattern = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]+')
    for match in cjk_pattern.finditer(text):
        seg = match.group()
        # Generate overlapping bigrams
        for i in range(len(seg) - 1):
            terms.add(seg[i:i+2])
        # Generate overlapping trigrams
        for i in range(len(seg) - 2):
            terms.add(seg[i:i+3])
    
    # English/other text: split by whitespace/punctuation
    non_cjk = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf]+', ' ', text)
    for word in re.split(r'[\s,，、。\.!！?？:：;；()（）【】\[\]""''…—/\\|@#$%^&*+=<>{}~`\t\n\r-]+', non_cjk):
        word = word.strip().lower()
        if len(word) >= 2:
            terms.add(word)
    
    # Remove pure noise (numbers only, single chars)
    noise_pattern = re.compile(r'^\d+$')
    filtered = [t for t in terms if not noise_pattern.match(t) and len(t) >= 2]
    
    # Sort by length descending (longer terms more specific)
    filtered.sort(key=lambda x: -len(x))
    return filtered[:30]


def _find_related_questions(events: list[dict]) -> list[dict]:
    """Find brainstorm questions related to the given events via contemplate cache."""
    from .db import connect

    event_ids = [e["id"] for e in events if e.get("id")]
    if not event_ids:
        return []

    placeholders = ",".join("?" for _ in event_ids)
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT DISTINCT bq.id, bq.question, bq.topic, bcc.relevance, bcc.reason
                FROM brainstorm_contemplate_cache bcc
                JOIN brainstorm_questions bq ON bcc.question_id = bq.id
                WHERE bcc.event_id IN ({placeholders})
                  AND bcc.relevance != 'low'
                ORDER BY CASE bcc.relevance WHEN 'high' THEN 0 ELSE 1 END
                LIMIT 10""",
            event_ids,
        ).fetchall()
    return [dict(r) for r in rows]


def _build_search_context(events: list[dict], questions: list[dict]) -> str:
    """Build a compact context string from search results."""
    parts = []

    if events:
        parts.append("## 相关采集内容")
        for i, e in enumerate(events[:10], 1):
            title = e.get("title_cn") or e.get("title", "无标题")
            summary = (e.get("summary_cn") or e.get("raw_summary") or "")[:200]
            parts.append(f"{i}. [{e['id']}] {title}")
            if summary:
                parts.append(f"   摘要: {summary}")

    if questions:
        parts.append("\n## 相关头脑风暴问题")
        for i, q in enumerate(questions[:10], 1):
            parts.append(f"{i}. [{q['id']}] {q['question']}")
            if q.get("relevance"):
                parts.append(f"   关联度: {q['relevance']}")

    return "\n".join(parts) if parts else "未找到相关信息"


def evaluate_affair_events(affair_id: str, body: str, events: list[dict]) -> list[dict]:
    """Batch-evaluate relevance of events to an affair via single AI call.
    
    Returns list of {event_id, relevance, reason} for events with non-low relevance.
    """
    if not events:
        return []

    prompt_items = []
    for i, e in enumerate(events):
        title = (e.get("title_cn") or e.get("title", ""))[:120]
        summary = (e.get("summary_cn") or e.get("raw_summary") or "")[:200]
        prompt_items.append(f"{i+1}. [{e['id']}] {title}\n   摘要: {summary}")
    events_text = "\n".join(prompt_items)

    system = "你是一个信息关联度评估助手。你的任务是评估一组事件与一个事务的相关程度。仅输出 JSON，不含其他内容。"

    user = f"""事务：
{body}

待评估内容（共 {len(events)} 条）：
{events_text}

请逐条评估关联度。"""

    content = chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=8192,
        timeout=180,
        module="affairs",
        task="relevance",
    )
    if not content:
        return []

    try:
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if lines[0].startswith("```") else content
            if content.endswith("```"):
                content = content[:-3].strip()
        results = json.loads(content)
        logger.info("Affair %s: evaluated %d events, got %d results", affair_id, len(events), len(results))
        return results
    except Exception as e:
        logger.warning("Affair %s: event relevance evaluation failed: %s", affair_id, e)
        return []
