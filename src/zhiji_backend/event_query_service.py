"""Read-only event queries for event route adapters."""

from __future__ import annotations

import difflib
import logging
from typing import Any

logger = logging.getLogger("zhiji_backend.routes.event_routes")


class EventNotFoundError(LookupError):
    """Raised when an event query targets an unknown event."""


class InvalidSourceFilterError(ValueError):
    """Raised when a source ID filter cannot be parsed safely."""


def list_events(
    topic: str | None,
    status: str | None,
    source_id: str | None,
    content_type: str | None,
    search: str | None,
    offset: int,
    limit: int,
    count: int,
    *,
    connect_fn,
    parse_bounded_identifier_csv_fn,
) -> list[dict[str, object]] | dict[str, object]:
    list_cols = (
        "id, source_id, title, url, published_at,"
        " title_cn, summary_cn, translation_status, translation_error,"
        " topic, importance, actionability, decision, status,"
        " video_path, content_type, created_at"
    )
    if search:
        search_term = search.strip()
        search = " ".join(f'"{word}"' for word in search_term.split() if word)
        if len(search_term) < 3:
            with connect_fn() as conn:
                like_pattern = f"%{search_term}%"
                rows = conn.execute(
                    f"""SELECT {list_cols}
                    FROM events
                    WHERE title LIKE ? OR title_cn LIKE ? OR raw_summary LIKE ? OR summary_cn LIKE ? OR ai_summary LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?""",
                    (
                        like_pattern,
                        like_pattern,
                        like_pattern,
                        like_pattern,
                        like_pattern,
                        max(1, min(200, limit)),
                        max(0, offset),
                    ),
                ).fetchall()
            return [dict(row) for row in rows]
        fts_cols = ", ".join(f"e.{column.strip()}" for column in list_cols.split(","))
        with connect_fn() as conn:
            rows = conn.execute(
                f"""SELECT {fts_cols},
                   snippet(events_fts, 1, '<mark>', '</mark>', '...', 60) as snippet
                FROM events e
                INNER JOIN events_fts fts ON e.id = fts.event_id
                WHERE events_fts MATCH ?
                ORDER BY rank
                LIMIT ? OFFSET ?""",
                (search, max(1, min(200, limit)), max(0, offset)),
            ).fetchall()
        return [dict(row) for row in rows]

    query = (
        "SELECT id, source_id, title, url, published_at,\n"
        "       title_cn, summary_cn, translation_status, translation_error,\n"
        "       topic, importance, actionability, decision, status,\n"
        "       video_path, content_type, created_at\n"
        "FROM events\n"
        "WHERE 1=1\n"
    )
    params: dict[str, object] = {}
    if topic:
        query += " AND topic = :topic"
        params["topic"] = topic
    if status:
        query += " AND status = :status"
        params["status"] = status
    if source_id:
        try:
            ids = parse_bounded_identifier_csv_fn(source_id) or []
        except ValueError as exc:
            raise InvalidSourceFilterError from exc
        if len(ids) == 1:
            query += " AND source_id = :source_id"
            params["source_id"] = ids[0]
        else:
            placeholders = ",".join([f":sid{i}" for i in range(len(ids))])
            query += f" AND source_id IN ({placeholders})"
            for i, sid in enumerate(ids):
                params[f"sid{i}"] = sid
    if content_type:
        query += " AND content_type = :content_type"
        params["content_type"] = content_type
    query += " ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
    params["limit"] = max(1, min(200, limit))
    params["offset"] = max(0, offset)
    with connect_fn() as conn:
        rows = conn.execute(query, params).fetchall()
    result = [dict(row) for row in rows]
    if count:
        count_params = {}
        count_query = "SELECT COUNT(*) FROM events WHERE 1=1"
        if "topic" in params:
            count_query += " AND topic = :topic"
            count_params["topic"] = params["topic"]
        if "status" in params:
            count_query += " AND status = :status"
            count_params["status"] = params["status"]
        if "content_type" in params:
            count_query += " AND content_type = :content_type"
            count_params["content_type"] = params["content_type"]
        if source_id:
            try:
                ids = parse_bounded_identifier_csv_fn(source_id) or []
            except ValueError as exc:
                raise InvalidSourceFilterError from exc
            if len(ids) == 1:
                count_query += " AND source_id = :source_id"
                count_params["source_id"] = ids[0]
            else:
                placeholders = ",".join([f":sid{i}" for i in range(len(ids))])
                count_query += f" AND source_id IN ({placeholders})"
                for i, sid in enumerate(ids):
                    count_params[f"sid{i}"] = sid
        with connect_fn() as conn:
            total = conn.execute(count_query, count_params).fetchone()[0]
        return {"items": result, "total": total}
    return result


def event_topic_counts(*, connect_fn) -> dict[str, int]:
    topics = ["格局", "财富", "认知", "前瞻"]
    result: dict[str, int] = {}
    with connect_fn() as conn:
        for topic in topics:
            count = conn.execute(
                "SELECT COUNT(*) FROM events WHERE topic = ? AND source_id IN ('douyin','user-upload','user-concept')",
                (topic,),
            ).fetchone()[0]
            result[topic] = int(count)
        briefing_count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE source_id NOT IN ('douyin','user-upload','user-concept','')"
        ).fetchone()[0]
        result["briefing"] = int(briefing_count)
    return result


def get_event(
    event_id: str, *, connect_fn, add_video_url_fn, ingest_root
) -> dict[str, object]:
    with connect_fn() as conn:
        row = conn.execute(
            """SELECT id, source_id, title, url, published_at, raw_summary, ai_summary,
               title_cn, summary_cn, translation_status, translation_error,
               topic, importance, actionability, decision, status, tags_json,
               last_error, progress_stages, video_path, created_at, overview, chain_analysis
               FROM events WHERE id = ?""",
            (event_id,),
        ).fetchone()
    if row is None:
        raise EventNotFoundError
    result = dict(row)
    add_video_url_fn(result, ingest_root)
    result["transcript_path"] = str(ingest_root / "transcripts" / f"{event_id}.md")
    result["summary_path"] = str(ingest_root / "summaries" / f"{event_id}.md")
    with connect_fn() as conn:
        rows = conn.execute(
            "SELECT bq.id, bq.question, bq.status, bq.created_at, "
            "(SELECT json_group_array(bel2.event_id) FROM brainstorm_event_links bel2 WHERE bel2.question_id = bq.id) as answered_event_ids "
            "FROM brainstorm_questions bq "
            "INNER JOIN brainstorm_event_links bel ON bel.question_id = bq.id "
            "WHERE bel.event_id = ? ORDER BY bq.created_at DESC",
            (event_id,),
        ).fetchall()
    result["associated_questions"] = [dict(row) for row in rows]
    return result


def similar_events(event_id: str, limit: int, *, connect_fn) -> list[dict[str, object]]:
    with connect_fn() as conn:
        target = conn.execute(
            "SELECT id, title, title_cn, raw_summary FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if not target:
            raise EventNotFoundError

        target_title = target["title_cn"] or target["title"] or ""
        clean = "".join(
            char if char.isalnum() or char.isspace() else " " for char in target_title
        )
        keywords = [word for word in clean.split() if len(word) > 1]
        if keywords:
            fts_query = " OR ".join(keywords[:12])
            try:
                candidates = conn.execute(
                    """SELECT e.id, e.source_id, e.title, e.title_cn, e.raw_summary, e.url, e.topic, e.created_at
                       FROM events e
                       INNER JOIN events_fts fts ON e.id = fts.event_id
                       WHERE e.id != ? AND e.status = 'new' AND events_fts MATCH ?
                       ORDER BY rank LIMIT 100""",
                    (event_id, fts_query),
                ).fetchall()
            except Exception:
                candidates = []
        else:
            candidates = []
        if not candidates:
            candidates = conn.execute(
                """SELECT id, source_id, title, title_cn, raw_summary, url, topic, created_at
                   FROM events WHERE id != ? AND status = 'new'
                   ORDER BY created_at DESC LIMIT 100""",
                (event_id,),
            ).fetchall()

    target_title_lower = target_title.lower()
    target_text = (target["raw_summary"] or "")[:500].lower()
    scored: list[tuple[float, Any]] = []
    for candidate in candidates:
        candidate_title = (candidate["title_cn"] or candidate["title"] or "").lower()
        candidate_text = (candidate["raw_summary"] or "")[:500].lower()
        title_similarity = difflib.SequenceMatcher(
            None, target_title_lower, candidate_title
        ).ratio()

        def bigrams(value: str) -> set[str]:
            words = value.split()
            if len(words) > 1:
                return {
                    f"{words[index]}_{words[index + 1]}"
                    for index in range(len(words) - 1)
                }
            return set(words)

        target_grams = bigrams(target_text)
        candidate_grams = bigrams(candidate_text)
        if target_grams and candidate_grams:
            jaccard = len(target_grams & candidate_grams) / len(
                target_grams | candidate_grams
            )
        else:
            jaccard = 0.0
        score = title_similarity * 0.6 + jaccard * 0.4
        if score > 0.2:
            scored.append((score, candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, row in scored[:limit]:
        result = dict(row)
        result["similarity"] = round(score, 3)
        results.append(result)
    return results
