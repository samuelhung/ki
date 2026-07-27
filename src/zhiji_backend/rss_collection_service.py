from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import re
import sqlite3
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from . import rss_feed
from .db import connect, init_db
from .paths import DATA_DIR

logger = logging.getLogger("knowledge-intelligence")

DEFAULT_DATA_DIR = DATA_DIR
MAX_WATERMARK_IDS = 500
FetchUrl = Callable[[str], str]
ParseItems = Callable[[str], list[dict[str, str | None]]]
FetchArticle = Callable[[str], str | None]


def get_data_dir() -> Path:
    if configured := os.getenv("KI_DATA_DIR"):
        return Path(configured).expanduser().resolve()
    return DEFAULT_DATA_DIR


def fetch_url(url: str) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": "knowledge-intelligence/0.1"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_article_text(url: str, max_chars: int = 5000) -> str | None:
    if not url or "news.google.com" in url:
        return None
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "knowledge-intelligence/0.1"}
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read().decode(charset, errors="replace")
    except Exception as exc:
        logger.debug("Failed to fetch article from %s: %s", url, exc)
        return None
    try:
        import trafilatura

        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            output_format="text",
        )
        if text and len(text.strip()) > 50:
            text = re.sub(r"\n{3,}", "\n\n", text.strip())
            if len(text) > max_chars:
                text = text[:max_chars].rsplit("\n", 1)[0]
            return text.strip()
    except Exception as exc:
        logger.debug("trafilatura extraction failed for %s: %s", url, exc)
    return rss_feed.extract_text(html, max_chars=max_chars)


def watermark_path(source_id: str) -> Path:
    return get_data_dir() / "state" / f"rss-{source_id}.json"


def load_watermark(source_id: str) -> set[str] | None:
    path = watermark_path(source_id)
    if not path.exists():
        return None
    return set(json.loads(path.read_text()).get("seen_ids", []))


def save_watermark(source_id: str, seen_ids: Iterable[str]) -> None:
    path = watermark_path(source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    bounded = list(dict.fromkeys(seen_ids))[:MAX_WATERMARK_IDS]
    payload = {
        "source_id": source_id,
        "seen_ids": bounded,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.replace(path)


def event_id(source_id: str, external_id: str) -> str:
    digest = hashlib.sha256(f"{source_id}:{external_id}".encode()).hexdigest()[:24]
    return f"evt-{digest}"


def append_event_jsonl(event: dict[str, object]) -> None:
    events_dir = get_data_dir() / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).date().isoformat()
    with (events_dir / f"{stamp}.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def insert_event(conn: sqlite3.Connection, event: dict[str, object]) -> bool:
    before = conn.total_changes
    conn.execute(
        """INSERT OR IGNORE INTO events (
          id, source_id, title, url, published_at, raw_summary, title_cn, summary_cn,
          translation_status, translation_error, topic,
          importance, actionability, decision, status
        ) VALUES (
          :id, :source_id, :title, :url, :published_at, :raw_summary, :title_cn, :summary_cn,
          :translation_status, :translation_error, :topic,
          :importance, :actionability, :decision, :status
        )""",
        event,
    )
    return conn.total_changes > before


def enabled_rss_sources(source_ids: list[str] | None = None) -> list[dict[str, object]]:
    init_db()
    where = "WHERE enabled = 1 AND type = 'rss'"
    params: dict[str, object] = {}
    if source_ids is not None:
        if not source_ids:
            return []
        placeholders = ",".join(f":id{index}" for index, _ in enumerate(source_ids))
        where += f" AND id IN ({placeholders})"
        params.update({f"id{index}": value for index, value in enumerate(source_ids)})
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT id, name, url, topic, priority
                FROM sources {where} ORDER BY id""",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def canonical_url(url: str) -> str:
    if not url:
        return url
    cleaned = re.sub(r"[?&](utm_[^&#]+|ref=[^&#]+|source=[^&#]+|oc=[^&#]+)", "", url)
    return re.sub(r"[?&]$", "", cleaned).rstrip("?")


def title_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def is_duplicate_title(
    new_title: str, existing_titles: list[str], threshold: float = 0.75
) -> bool:
    return any(
        title_similarity(new_title, title) >= threshold for title in existing_titles
    )


def _result(
    source_id: str, *, baseline: bool, items_total: int, events=None, error=None
):
    collected = events or []
    return {
        "source_id": source_id,
        "baseline": baseline,
        "new_events": len(collected),
        "events": collected,
        "error": error,
        "items_total": items_total,
    }


def collect_one_source(
    source: dict[str, object],
    fetcher: FetchUrl,
    *,
    parse_items: ParseItems,
    fetch_article: FetchArticle,
) -> dict[str, object]:
    source_id = str(source["id"])
    now = datetime.now(UTC).isoformat()
    try:
        items = parse_items(fetcher(str(source["url"])))
        ids = [str(item["external_id"]) for item in items]
        seen = load_watermark(source_id)
        if seen is None:
            save_watermark(source_id, ids)
            _update_source(source_id, now)
            return _result(source_id, baseline=True, items_total=len(items))
        fresh_items = [item for item in items if str(item["external_id"]) not in seen]
        if not fresh_items:
            _update_source(source_id, now)
            save_watermark(source_id, ids)
            return _result(source_id, baseline=False, items_total=len(items))
        with connect() as conn:
            rows = conn.execute(
                "SELECT title FROM events WHERE source_id = ? ORDER BY created_at DESC LIMIT 100",
                (source_id,),
            ).fetchall()
        existing_titles = [row["title"] for row in rows]
        events = _store_fresh_items(
            source, fresh_items, existing_titles, now, fetch_article
        )
        save_watermark(source_id, ids + [known for known in seen if known not in ids])
        return _result(source_id, baseline=False, items_total=len(items), events=events)
    except Exception as exc:
        message = str(exc)
        _update_source(source_id, now, message)
        return _result(source_id, baseline=False, items_total=0, error=message)


def _update_source(source_id: str, checked_at: str, error: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE sources SET last_checked_at = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (checked_at, error, source_id),
        )


def _store_fresh_items(source, items, existing_titles, now, fetch_article):
    source_id = str(source["id"])
    events: list[dict[str, object]] = []
    with connect() as conn:
        for item in items:
            title = str(item["title"])
            if is_duplicate_title(title, existing_titles):
                continue
            article_url = str(item["url"]) if item.get("url") else ""
            event = {
                "id": event_id(source_id, str(item["external_id"])),
                "source_id": source_id,
                "source_name": source.get("name"),
                "external_id": item["external_id"],
                "title": title,
                "url": canonical_url(item["url"] or ""),
                "published_at": item["published_at"],
                "raw_summary": fetch_article(article_url) or item.get("raw_summary"),
                "title_cn": None,
                "summary_cn": None,
                "translation_status": "pending"
                if source.get("type") == "rss"
                else None,
                "translation_error": None,
                "topic": source.get("topic"),
                "importance": 4 if source.get("priority") == "high" else 2,
                "actionability": 0,
                "decision": "digest",
                "status": "new",
                "collected_at": now,
            }
            if insert_event(conn, event):
                append_event_jsonl(event)
                events.append(event)
                existing_titles.append(title)
        conn.execute(
            "UPDATE sources SET last_checked_at = ?, last_error = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (now, source_id),
        )
    return events


def collect_once(
    source_ids: list[str] | None = None,
    fetcher: FetchUrl | None = None,
    *,
    parse_items: ParseItems | None = None,
    fetch_article: FetchArticle | None = None,
) -> dict[str, object]:
    init_db()
    fetch = fetcher or fetch_url
    parser = parse_items or rss_feed.parse_rss_items
    article_fetcher = fetch_article or fetch_article_text
    sources = enabled_rss_sources(source_ids)
    results = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=min(len(sources), 5)) as executor:
        futures = {
            executor.submit(
                collect_one_source,
                source,
                fetch,
                parse_items=parser,
                fetch_article=article_fetcher,
            ): source["id"]
            for source in sources
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append({"source_id": str(futures[future]), "error": str(exc)})
    errors.extend(
        {"source_id": str(result["source_id"]), "error": str(result["error"])}
        for result in results
        if result["error"]
    )
    return {
        "sources_checked": len(results),
        "baseline_sources": sum(bool(result["baseline"]) for result in results),
        "new_events": sum(int(result["new_events"]) for result in results),
        "events": [event for result in results for event in result.get("events", [])],
        "errors": errors,
    }
