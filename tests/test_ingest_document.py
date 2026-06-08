"""Tests for document ingestion."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from ingest.document import process_document


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
