"""Document ingestion — reads text documents and PDFs."""

from __future__ import annotations

from pathlib import Path


def process_document(source: Path | str, *, title: str = "", topic: str = "",
                     on_progress=None) -> dict:
    """Process a document file and return structured event data.

    For .pdf files, routes to pdf_ocr module (text or scanned).
    For other formats, reads as UTF-8 text directly.

    Returns dict with keys: title, topic, text
    """
    path = Path(source)

    if path.suffix.lower() == ".pdf":
        from .pdf_ocr import process_pdf
        return process_pdf(path, title=title, topic=topic, on_progress=on_progress)

    text = path.read_text(encoding="utf-8")

    if not title and path.name:
        title = path.stem

    return {
        "title": title,
        "topic": topic,
        "text": text,
    }
