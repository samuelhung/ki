"""Compatibility facade for the split RSS ingestion implementation."""

from __future__ import annotations

import logging
import sqlite3
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

from . import rss_collection_service, rss_feed
from .db import connect, init_db

logger = logging.getLogger("knowledge-intelligence")

DEFAULT_DATA_DIR = rss_collection_service.DEFAULT_DATA_DIR
MAX_WATERMARK_IDS = rss_collection_service.MAX_WATERMARK_IDS
FetchUrl = rss_collection_service.FetchUrl

_COLLECT_ONCE_IMPLEMENTATION = rss_collection_service.collect_once
_PARSE_RSS_ITEMS_IMPLEMENTATION = rss_feed.parse_rss_items


def get_data_dir() -> Path:
    return rss_collection_service.get_data_dir(default_data_dir=DEFAULT_DATA_DIR)


def fetch_url(url: str) -> str:
    return rss_collection_service.fetch_url(url)


def fetch_article_text(url: str, max_chars: int = 5000) -> str | None:
    return rss_collection_service.fetch_article_text(
        url, max_chars=max_chars, extract_text_fn=_extract_text, logger_obj=logger
    )


def _extract_text(html: str, max_chars: int = 5000) -> str:
    return rss_feed.extract_text(html, max_chars=max_chars, logger_obj=logger)


def strip_html(value: str | None) -> str:
    return rss_feed.strip_html(value)


def parse_datetime(value: str | None) -> str | None:
    return rss_feed.parse_datetime(value, logger_obj=logger)


def child_text(element: ET.Element, names: Iterable[str]) -> str | None:
    return rss_feed.child_text(element, names)


def atom_link(element: ET.Element) -> str | None:
    return rss_feed.atom_link(element)


def stable_item_id(title: str, url: str, published_at: str | None) -> str:
    return rss_feed.stable_item_id(title, url, published_at)


def parse_rss_items(feed_text: str) -> list[dict[str, str | None]]:
    implementation = rss_feed.parse_rss_items
    if implementation is not _PARSE_RSS_ITEMS_IMPLEMENTATION:
        return implementation(feed_text)
    return implementation(
        feed_text,
        strip_html_fn=strip_html,
        child_text_fn=child_text,
        atom_link_fn=atom_link,
        parse_datetime_fn=parse_datetime,
        stable_item_id_fn=stable_item_id,
    )


def watermark_path(source_id: str) -> Path:
    return rss_collection_service.watermark_path(source_id, data_dir_fn=get_data_dir)


def load_watermark(source_id: str) -> set[str] | None:
    return rss_collection_service.load_watermark(
        source_id, watermark_path_fn=watermark_path
    )


def save_watermark(source_id: str, seen_ids: Iterable[str]) -> None:
    rss_collection_service.save_watermark(
        source_id,
        seen_ids,
        watermark_path_fn=watermark_path,
        max_ids=MAX_WATERMARK_IDS,
    )


def event_id(source_id: str, external_id: str) -> str:
    return rss_collection_service.event_id(source_id, external_id)


def append_event_jsonl(event: dict[str, object]) -> None:
    rss_collection_service.append_event_jsonl(event, data_dir_fn=get_data_dir)


def insert_event(conn: sqlite3.Connection, event: dict[str, object]) -> bool:
    return rss_collection_service.insert_event(conn, event)


def enabled_rss_sources(source_ids: list[str] | None = None) -> list[dict[str, object]]:
    return rss_collection_service.enabled_rss_sources(
        source_ids, init_db_fn=init_db, connect_fn=connect
    )


def _canonical_url(url: str) -> str:
    return rss_collection_service.canonical_url(url)


def _title_similarity(a: str, b: str) -> float:
    return rss_collection_service.title_similarity(a, b)


def _is_duplicate_title(
    new_title: str, existing_titles: list[str], threshold: float = 0.75
) -> bool:
    return rss_collection_service.is_duplicate_title(
        new_title, existing_titles, threshold, similarity_fn=_title_similarity
    )


def _collect_one_source(
    source: dict[str, object], fetcher: FetchUrl
) -> dict[str, object]:
    dependencies = rss_collection_service.SourceDependencies(
        parse_items=parse_rss_items,
        load_watermark=load_watermark,
        save_watermark=save_watermark,
        connect=connect,
        is_duplicate_title=_is_duplicate_title,
        fetch_article=fetch_article_text,
        canonical_url=_canonical_url,
        event_id=event_id,
        insert_event=insert_event,
        append_event_jsonl=append_event_jsonl,
    )
    return rss_collection_service.collect_one_source(
        source,
        fetcher,
        dependencies=dependencies,
    )


def collect_once(
    source_ids: list[str] | None = None, fetcher: FetchUrl | None = None
) -> dict[str, object]:
    implementation = rss_collection_service.collect_once
    if implementation is not _COLLECT_ONCE_IMPLEMENTATION:
        return implementation(source_ids, fetcher=fetcher)
    return implementation(
        source_ids,
        fetcher=fetcher,
        init_db_fn=init_db,
        fetch_url_fn=fetch_url,
        enabled_sources_fn=enabled_rss_sources,
        collect_source_fn=_collect_one_source,
    )
