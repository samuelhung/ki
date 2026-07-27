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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class SourceDependencies:
    parse_items: ParseItems
    load_watermark: Callable[[str], set[str] | None]
    save_watermark: Callable[[str, Iterable[str]], None]
    connect: Callable
    is_duplicate_title: Callable[[str, list[str]], bool]
    fetch_article: FetchArticle
    canonical_url: Callable[[str], str]
    event_id: Callable[[str, str], str]
    insert_event: Callable[[sqlite3.Connection, dict[str, object]], bool]
    append_event_jsonl: Callable[[dict[str, object]], None]


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


def fetch_article_text(
    url: str, max_chars: int = 5000, *, extract_text_fn=None
) -> str | None:
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
    return (extract_text_fn or rss_feed.extract_text)(html, max_chars=max_chars)


def watermark_path(source_id: str, *, data_dir_fn=None) -> Path:
    return (data_dir_fn or get_data_dir)() / "state" / f"rss-{source_id}.json"


def load_watermark(source_id: str, *, watermark_path_fn=None) -> set[str] | None:
    path = (watermark_path_fn or watermark_path)(source_id)
    if not path.exists():
        return None
    return set(json.loads(path.read_text()).get("seen_ids", []))


def save_watermark(
    source_id: str, seen_ids: Iterable[str], *, watermark_path_fn=None
) -> None:
    path = (watermark_path_fn or watermark_path)(source_id)
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


def append_event_jsonl(event: dict[str, object], *, data_dir_fn=None) -> None:
    events_dir = (data_dir_fn or get_data_dir)() / "events"
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


def enabled_rss_sources(
    source_ids: list[str] | None = None,
    *,
    init_db_fn: Callable[[], None] | None = None,
    connect_fn: Callable | None = None,
) -> list[dict[str, object]]:
    (init_db_fn or init_db)()
    where = "WHERE enabled = 1 AND type = 'rss'"
    params: dict[str, object] = {}
    if source_ids is not None:
        if not source_ids:
            return []
        placeholders = ",".join(f":id{index}" for index, _ in enumerate(source_ids))
        where += f" AND id IN ({placeholders})"
        params.update({f"id{index}": value for index, value in enumerate(source_ids)})
    with (connect_fn or connect)() as conn:
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
    new_title: str,
    existing_titles: list[str],
    threshold: float = 0.75,
    *,
    similarity_fn=None,
) -> bool:
    return any(
        (similarity_fn or title_similarity)(new_title, title) >= threshold
        for title in existing_titles
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
    parse_items: ParseItems | None = None,
    fetch_article: FetchArticle | None = None,
    dependencies: SourceDependencies | None = None,
) -> dict[str, object]:
    deps = dependencies or SourceDependencies(
        parse_items=parse_items or rss_feed.parse_rss_items,
        load_watermark=load_watermark,
        save_watermark=save_watermark,
        connect=connect,
        is_duplicate_title=is_duplicate_title,
        fetch_article=fetch_article or fetch_article_text,
        canonical_url=canonical_url,
        event_id=event_id,
        insert_event=insert_event,
        append_event_jsonl=append_event_jsonl,
    )
    source_id = str(source["id"])
    now = datetime.now(UTC).isoformat()
    try:
        items = deps.parse_items(fetcher(str(source["url"])))
        ids = [str(item["external_id"]) for item in items]
        seen = deps.load_watermark(source_id)
        if seen is None:
            deps.save_watermark(source_id, ids)
            _update_source(source_id, now, connect_fn=deps.connect)
            return _result(source_id, baseline=True, items_total=len(items))
        fresh_items = [item for item in items if str(item["external_id"]) not in seen]
        if not fresh_items:
            _update_source(source_id, now, connect_fn=deps.connect)
            deps.save_watermark(source_id, ids)
            return _result(source_id, baseline=False, items_total=len(items))
        with deps.connect() as conn:
            rows = conn.execute(
                "SELECT title FROM events WHERE source_id = ? ORDER BY created_at DESC LIMIT 100",
                (source_id,),
            ).fetchall()
        existing_titles = [row["title"] for row in rows]
        events = _store_fresh_items(source, fresh_items, existing_titles, now, deps)
        deps.save_watermark(
            source_id, ids + [known for known in seen if known not in ids]
        )
        return _result(source_id, baseline=False, items_total=len(items), events=events)
    except Exception as exc:
        message = str(exc)
        _update_source(source_id, now, message, connect_fn=deps.connect)
        return _result(source_id, baseline=False, items_total=0, error=message)


def _update_source(
    source_id: str,
    checked_at: str,
    error: str | None = None,
    *,
    connect_fn: Callable = connect,
) -> None:
    with connect_fn() as conn:
        conn.execute(
            "UPDATE sources SET last_checked_at = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (checked_at, error, source_id),
        )


def _store_fresh_items(source, items, existing_titles, now, deps):
    source_id = str(source["id"])
    events: list[dict[str, object]] = []
    with deps.connect() as conn:
        for item in items:
            title = str(item["title"])
            if deps.is_duplicate_title(title, existing_titles):
                continue
            article_url = str(item["url"]) if item.get("url") else ""
            event = {
                "id": deps.event_id(source_id, str(item["external_id"])),
                "source_id": source_id,
                "source_name": source.get("name"),
                "external_id": item["external_id"],
                "title": title,
                "url": deps.canonical_url(item["url"] or ""),
                "published_at": item["published_at"],
                "raw_summary": deps.fetch_article(article_url)
                or item.get("raw_summary"),
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
            if deps.insert_event(conn, event):
                deps.append_event_jsonl(event)
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
    init_db_fn: Callable[[], None] | None = None,
    fetch_url_fn: FetchUrl | None = None,
    enabled_sources_fn: Callable[[list[str] | None], list[dict[str, object]]]
    | None = None,
    collect_source_fn: Callable[[dict[str, object], FetchUrl], dict[str, object]]
    | None = None,
) -> dict[str, object]:
    (init_db_fn or init_db)()
    fetch = fetcher or fetch_url_fn or fetch_url
    parser = parse_items or rss_feed.parse_rss_items
    article_fetcher = fetch_article or fetch_article_text
    sources = (enabled_sources_fn or enabled_rss_sources)(source_ids)
    if collect_source_fn is None:

        def collect_source(source, source_fetcher):
            return collect_one_source(
                source,
                source_fetcher,
                parse_items=parser,
                fetch_article=article_fetcher,
            )

    else:
        collect_source = collect_source_fn
    checked = 0
    baseline_sources = 0
    total_new = 0
    events: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=min(len(sources), 5)) as executor:
        futures = {
            executor.submit(
                collect_source,
                source,
                fetch,
            ): source["id"]
            for source in sources
        }
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                errors.append({"source_id": str(futures[future]), "error": str(exc)})
                continue
            checked += 1
            if result["baseline"]:
                baseline_sources += 1
            if result["error"]:
                errors.append(
                    {
                        "source_id": str(result["source_id"]),
                        "error": str(result["error"]),
                    }
                )
            total_new += int(result["new_events"])
            events.extend(result.get("events", []))
    return {
        "sources_checked": checked,
        "baseline_sources": baseline_sources,
        "new_events": total_new,
        "events": events,
        "errors": errors,
    }
