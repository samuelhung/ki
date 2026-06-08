"""Document ingestion — reads and stores text documents directly."""

from __future__ import annotations

from pathlib import Path


def process_document(source: Path | str, *, title: str = "", topic: str = "") -> dict:
    """Process a document file and return structured event data.

    Returns dict with keys: title, topic, text
    """
    path = Path(source)
    text = path.read_text(encoding="utf-8")

    if not title and path.name:
        title = path.stem

    return {
        "title": title,
        "topic": topic,
        "text": text,
    }
