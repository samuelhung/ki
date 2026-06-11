from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import re
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Callable, Iterable

from .db import connect, init_db

logger = logging.getLogger("knowledge-intelligence")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
MAX_WATERMARK_IDS = 500

FetchUrl = Callable[[str], str]


def get_data_dir() -> Path:
    configured = os.getenv("KI_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_DATA_DIR


def fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "knowledge-intelligence/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_article_text(url: str, max_chars: int = 5000) -> str | None:
    """Fetch a news article URL and extract its main text content.

    Tries trafilatura first (best for real news sites), falls back to
    built-in HTMLParser extractor. Returns None on total failure.
    """
    if not url or "news.google.com" in url:
        return None

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "knowledge-intelligence/0.1"})
        with urllib.request.urlopen(request, timeout=10) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read().decode(charset, errors="replace")
    except Exception as e:
        logger.debug("Failed to fetch article from %s: %s", url, e)
        return None

    # Primary: trafilatura (best extraction quality)
    try:
        import trafilatura  # lazy import so the module loads without it

        text = trafilatura.extract(html, include_comments=False, include_tables=False,
                                    no_fallback=False, output_format="text")
        if text and len(text.strip()) > 50:  # real content, not just a byline
            text = re.sub(r"\n{3,}", "\n\n", text.strip())
            if len(text) > max_chars:
                text = text[:max_chars].rsplit("\n", 1)[0]
            return text.strip()
    except Exception as e:
        logger.debug("trafilatura extraction failed for %s: %s", url, e)

    # Fallback: built-in HTMLParser extractor
    return _extract_text(html, max_chars=max_chars)


def _extract_text(html: str, max_chars: int = 5000) -> str:
    """Extract readable text from HTML, stripping boilerplate."""
    import re
    from html.parser import HTMLParser

    SKIP_TAGS = {'script', 'style', 'nav', 'header', 'footer', 'aside',
                 'noscript', 'iframe', 'svg', 'form', 'button', 'select',
                 'input', 'textarea'}

    class _Extractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []
            self._skip = 0

        def handle_starttag(self, tag, _attrs):
            if tag in SKIP_TAGS:
                self._skip += 1
            elif tag in ('br', 'p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'tr', 'blockquote', 'pre'):
                self.parts.append('\n')

        def handle_endtag(self, tag):
            if tag in SKIP_TAGS and self._skip > 0:
                self._skip -= 1
            elif tag in ('p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'blockquote', 'pre'):
                self.parts.append('\n')

        def handle_data(self, data):
            if self._skip == 0:
                text = data.strip()
                if text:
                    self.parts.append(text)

    parser = _Extractor()
    try:
        parser.feed(html)
    except Exception as e:
        logger.warning("HTMLParser extraction failed: %s", e)
    raw = '\n'.join(parser.parts)
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    # Filter common navigation/menu noise lines
    noise_patterns = [
        r'^Skip to content$', r'^Site search$', r'^Accessibility links$',
        r'^Keyboard shortcuts', r'^BBC (News )?Services$', r'^NPR\s*$',
        r'^NPR App$', r'^Apple Podcasts$', r'^Spotify$', r'^Amazon Music$',
        r'^iHeart Radio$', r'^YouTube Music$', r'^RSS link$',
        r'^Subscribe to', r'^Share this', r'^Copy link', r'^Related topics$',
        r'^Explore more$', r'^More on this story$', r'^Top stories$',
        r'^Follow .+ on', r'^Image source,', r'^Image caption,',
        r'^\d+ (minutes|hours|days) ago$', r'^Published\s', r'^\d+ (January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$',
    ]
    lines = raw.split('\n')
    filtered = [l for l in lines if not any(re.match(p, l.strip()) for p in noise_patterns)]
    raw = '\n'.join(filtered)
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    if len(raw) > max_chars:
        raw = raw[:max_chars].rsplit('\n', 1)[0]
    return raw.strip()


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def parse_datetime(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        logger.debug("parsedate_to_datetime failed for %r, trying fromisoformat", text)
    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        logger.debug("fromisoformat failed for %r, returning raw text", text)
        return text


def child_text(element: ET.Element, names: Iterable[str]) -> str | None:
    wanted = set(names)
    for child in list(element):
        local = child.tag.rsplit("}", 1)[-1]
        if local in wanted:
            return child.text
    return None


def atom_link(element: ET.Element) -> str | None:
    for child in list(element):
        local = child.tag.rsplit("}", 1)[-1]
        if local == "link":
            href = child.attrib.get("href")
            if href:
                return href
            if child.text:
                return child.text
    return None


def stable_item_id(title: str, url: str, published_at: str | None) -> str:
    raw = "|".join([title, url, published_at or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_rss_items(feed_text: str) -> list[dict[str, str | None]]:
    root = ET.fromstring(feed_text)
    items: list[ET.Element] = []
    for element in root.iter():
        local = element.tag.rsplit("}", 1)[-1]
        if local in {"item", "entry"}:
            items.append(element)

    parsed: list[dict[str, str | None]] = []
    for item in items:
        title = strip_html(child_text(item, ["title"]))
        url = (child_text(item, ["link"]) or atom_link(item) or "").strip()
        guid = (child_text(item, ["guid", "id"]) or "").strip()
        published_at = parse_datetime(child_text(item, ["pubDate", "published", "updated", "date"]))
        summary = strip_html(child_text(item, ["description", "summary", "content", "encoded"]))
        external_id = guid or stable_item_id(title, url, published_at)
        if not title and not url:
            continue
        parsed.append(
            {
                "external_id": external_id,
                "title": title or url,
                "url": url,
                "published_at": published_at,
                "raw_summary": summary,
            }
        )
    return parsed


def watermark_path(source_id: str) -> Path:
    return get_data_dir() / "state" / f"rss-{source_id}.json"


def load_watermark(source_id: str) -> set[str] | None:
    path = watermark_path(source_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    return set(payload.get("seen_ids", []))


def save_watermark(source_id: str, seen_ids: Iterable[str]) -> None:
    path = watermark_path(source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    bounded = list(dict.fromkeys(seen_ids))[:MAX_WATERMARK_IDS]
    payload = {"source_id": source_id, "seen_ids": bounded, "updated_at": datetime.now(timezone.utc).isoformat()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.replace(path)


def event_id(source_id: str, external_id: str) -> str:
    digest = hashlib.sha256(f"{source_id}:{external_id}".encode("utf-8")).hexdigest()[:24]
    return f"evt-{digest}"


def append_event_jsonl(event: dict[str, object]) -> None:
    events_dir = get_data_dir() / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    with (events_dir / f"{stamp}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def insert_event(conn: sqlite3.Connection, event: dict[str, object]) -> bool:
    before = conn.total_changes
    conn.execute(
        """
        INSERT OR IGNORE INTO events (
          id, source_id, title, url, published_at, raw_summary, title_cn, summary_cn,
          translation_status, translation_error, topic,
          importance, actionability, decision, status
        ) VALUES (
          :id, :source_id, :title, :url, :published_at, :raw_summary, :title_cn, :summary_cn,
          :translation_status, :translation_error, :topic,
          :importance, :actionability, :decision, :status
        )
        """,
        event,
    )
    return conn.total_changes > before


def enabled_rss_sources(source_ids: list[str] | None = None) -> list[dict[str, object]]:
    init_db()
    where = "WHERE enabled = 1 AND type = 'rss'"
    params: dict[str, object] = {}
    if source_ids:
        placeholders = ",".join(f":id{i}" for i, _ in enumerate(source_ids))
        where += f" AND id IN ({placeholders})"
        params.update({f"id{i}": value for i, value in enumerate(source_ids)})
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, name, url, topic, priority
            FROM sources
            {where}
            ORDER BY id
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def _canonical_url(url: str) -> str:
    """Strip tracking parameters for dedup."""
    if not url:
        return url
    # Remove common tracking params
    cleaned = re.sub(r"[?&](utm_[^&#]+|ref=[^&#]+|source=[^&#]+|oc=[^&#]+)", "", url)
    cleaned = re.sub(r"[?&]$", "", cleaned)
    cleaned = cleaned.rstrip("?")
    return cleaned


def _title_similarity(a: str, b: str) -> float:
    """Return 0.0–1.0 similarity between two titles."""
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _is_duplicate_title(new_title: str, existing_titles: list[str], threshold: float = 0.75) -> bool:
    """Check if a title is too similar to any existing titles."""
    for existing in existing_titles:
        if _title_similarity(new_title, existing) >= threshold:
            return True
    return False


def _collect_one_source(source: dict[str, object], fetcher: FetchUrl) -> dict[str, object]:
    """Collect events from a single source. Returns result dict suitable for aggregation."""
    source_id = str(source["id"])
    now = datetime.now(timezone.utc).isoformat()

    try:
        items = parse_rss_items(fetcher(str(source["url"])))
        ids = [str(item["external_id"]) for item in items]
        seen = load_watermark(source_id)

        if seen is None:
            save_watermark(source_id, ids)
            with connect() as conn:
                conn.execute(
                    "UPDATE sources SET last_checked_at = ?, last_error = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (now, source_id),
                )
            return {
                "source_id": source_id, "baseline": True, "new_events": 0,
                "events": [], "error": None, "items_total": len(items),
            }

        fresh_items = [item for item in items if str(item["external_id"]) not in seen]
        if not fresh_items:
            with connect() as conn:
                conn.execute(
                    "UPDATE sources SET last_checked_at = ?, last_error = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (now, source_id),
                )
            save_watermark(source_id, ids)
            return {
                "source_id": source_id, "baseline": False, "new_events": 0,
                "events": [], "error": None, "items_total": len(items),
            }

        # Load existing titles for dedup
        with connect() as conn:
            existing_rows = conn.execute(
                "SELECT title FROM events WHERE source_id = ? ORDER BY created_at DESC LIMIT 100",
                (source_id,),
            ).fetchall()
        existing_titles = [r["title"] for r in existing_rows]

        new_events: list[dict[str, object]] = []
        saved_ids = ids + [known for known in seen if known not in ids]
        with connect() as conn:
            for item in fresh_items:
                title = str(item["title"])
                # Dedup: skip overly similar titles
                if _is_duplicate_title(title, existing_titles):
                    continue

                # Fetch full article text
                article_url = str(item["url"]) if item.get("url") else ""
                full_text = fetch_article_text(article_url)
                summary = full_text if full_text else item.get("raw_summary")

                # Determine if translation is needed (English sources)
                needs_translation = source.get("type") == "rss"

                event = {
                    "id": event_id(source_id, str(item["external_id"])),
                    "source_id": source_id,
                    "source_name": source.get("name"),
                    "external_id": item["external_id"],
                    "title": title,
                    "url": _canonical_url(item["url"] or ""),
                    "published_at": item["published_at"],
                    "raw_summary": summary,
                    "title_cn": None,
                    "summary_cn": None,
                    "translation_status": "pending" if needs_translation else None,
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
                    new_events.append(event)
                    existing_titles.append(title)  # update dedup set

            conn.execute(
                "UPDATE sources SET last_checked_at = ?, last_error = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (now, source_id),
            )
        save_watermark(source_id, saved_ids)
        return {
            "source_id": source_id, "baseline": False, "new_events": len(new_events),
            "events": new_events, "error": None, "items_total": len(items),
        }

    except Exception as exc:
        message = str(exc)
        with connect() as conn:
            conn.execute(
                "UPDATE sources SET last_checked_at = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (now, message, source_id),
            )
        return {
            "source_id": source_id, "baseline": False, "new_events": 0,
            "events": [], "error": message, "items_total": 0,
        }


def collect_once(source_ids: list[str] | None = None, fetcher: FetchUrl | None = None) -> dict[str, object]:
    init_db()
    fetch = fetcher or fetch_url
    all_sources = enabled_rss_sources(source_ids)
    checked = 0
    baseline_sources = 0
    total_new = 0
    all_events: list[dict[str, object]] = []
    all_errors: list[dict[str, str]] = []

    # Parallel collection with ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(len(all_sources), 5)) as executor:
        future_map = {
            executor.submit(_collect_one_source, src, fetch): src["id"]
            for src in all_sources
        }
        for future in as_completed(future_map):
            try:
                result = future.result()
            except Exception as exc:
                source_id = str(future_map[future])
                all_errors.append({"source_id": source_id, "error": str(exc)})
                continue

            checked += 1
            if result["baseline"]:
                baseline_sources += 1
            if result["error"]:
                all_errors.append({"source_id": str(result["source_id"]), "error": str(result["error"])})
            total_new += int(result["new_events"])
            all_events.extend(result.get("events", []))

    return {
        "sources_checked": checked,
        "baseline_sources": baseline_sources,
        "new_events": total_new,
        "events": all_events,
        "errors": all_errors,
    }
