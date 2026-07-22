"""Tests for document ingestion."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from zhiji_backend.ingest.document import process_document
from zhiji_backend.ingest.epub import _extract_chapters, process_epub


def test_process_text_document(tmp_path: Path):
    """Plain text documents are stored as-is with metadata."""
    doc = tmp_path / "article.md"
    doc.write_text("# Hello World\n\nThis is a test document.", encoding="utf-8")

    result = process_document(doc, title="测试文章", topic="tech")

    assert result["title"] == "测试文章"
    assert result["topic"] == "tech"
    assert "# Hello World" in result["text"]
    assert "This is a test document" in result["text"]


def test_process_document_defaults_title_from_filename(tmp_path: Path):
    """When no title is given, derive title from filename stem."""
    doc = tmp_path / "meeting_notes.md"
    doc.write_text("Q3 planning notes.", encoding="utf-8")

    result = process_document(doc, title="", topic="misc")

    assert result["title"] == "meeting_notes"
    assert "Q3 planning" in result["text"]


def test_process_document_preserves_unicode():
    """Chinese content must be preserved correctly."""
    doc = Path("/tmp/test_cn.txt")
    doc.write_text("这是一篇中文文档。\n包含多行内容。", encoding="utf-8")

    result = process_document(doc, title="中文测试", topic="lang")

    assert "这是一篇中文文档" in result["text"]
    assert "包含多行内容" in result["text"]


def test_extract_epub_text_enforces_injected_limit():
    archive = type("Archive", (), {"read": lambda self, name: b"<p>0123456789</p>"})()

    with pytest.raises(RuntimeError, match="文字"):
        _extract_chapters(archive, ["chapter.xhtml"], max_text_bytes=5)


def test_process_epub_validates_archive_before_opening_members(tmp_path: Path):
    path = tmp_path / "book.epub"
    path.write_bytes(b"not a zip")

    with patch("zhiji_backend.ingest.epub.validate_epub", side_effect=RuntimeError("blocked")) as validate:
        with patch("zhiji_backend.ingest.epub.zipfile.ZipFile") as zip_open:
            with pytest.raises(RuntimeError, match="blocked"):
                process_epub(path)

    validate.assert_called_once_with(path)
    zip_open.assert_not_called()
