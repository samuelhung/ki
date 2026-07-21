from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from zhiji_backend.ingest.pdf_ocr import (
    detect_pdf_type,
    extract_text_pdf,
    process_pdf,
    validate_pdf_safety,
)


class FakePdf:
    def __init__(self, *, pages: int, encrypted: bool = False):
        self.pages = pages
        self.needs_pass = encrypted
        self.is_encrypted = encrypted
        self.closed = False

    def __len__(self) -> int:
        return self.pages

    def close(self) -> None:
        self.closed = True

    def __getitem__(self, index):
        raise AssertionError("PDF pages must not be sampled before safety validation")


def test_validate_pdf_safety_rejects_encrypted_pdf_and_closes_parser(tmp_path: Path):
    path = tmp_path / "encrypted.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    doc = FakePdf(pages=1, encrypted=True)

    with pytest.raises(ValueError, match="加密"):
        validate_pdf_safety(path, opener=lambda _: doc, max_bytes=100, max_pages=300)

    assert doc.closed


def test_validate_pdf_safety_rejects_301_pages_before_processing(tmp_path: Path):
    path = tmp_path / "long.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    doc = FakePdf(pages=301)

    with pytest.raises(ValueError, match="页数"):
        validate_pdf_safety(path, opener=lambda _: doc, max_bytes=100, max_pages=300)

    assert doc.closed


def test_validate_pdf_safety_accepts_exact_size_and_page_boundaries(tmp_path: Path):
    path = tmp_path / "boundary.pdf"
    path.write_bytes(b"x" * 10)
    doc = FakePdf(pages=300)

    assert validate_pdf_safety(path, opener=lambda _: doc, max_bytes=10, max_pages=300) == 300
    assert doc.closed


def test_validate_pdf_safety_rejects_oversized_file_before_opening(tmp_path: Path):
    path = tmp_path / "large.pdf"
    path.write_bytes(b"x" * 11)
    opened = False

    def opener(_):
        nonlocal opened
        opened = True
        return FakePdf(pages=1)

    with pytest.raises(ValueError, match="大小"):
        validate_pdf_safety(path, opener=opener, max_bytes=10, max_pages=300)

    assert not opened


def test_detect_pdf_type_rejects_encrypted_pdf_before_sampling(tmp_path: Path):
    path = tmp_path / "encrypted.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    doc = FakePdf(pages=1, encrypted=True)

    with patch("zhiji_backend.ingest.pdf_ocr._import_pymupdf", return_value=SimpleNamespace(open=lambda _: doc)):
        with pytest.raises(ValueError, match="加密"):
            detect_pdf_type(path)

    assert doc.closed


def test_extract_text_pdf_rejects_301_pages_before_iteration(tmp_path: Path):
    path = tmp_path / "long.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    doc = FakePdf(pages=301)

    with patch("zhiji_backend.ingest.pdf_ocr._import_pymupdf", return_value=SimpleNamespace(open=lambda _: doc)):
        with pytest.raises(ValueError, match="页数"):
            extract_text_pdf(path)

    assert doc.closed


def test_process_pdf_applies_300_page_gate_before_detection(tmp_path: Path):
    path = tmp_path / "long.pdf"
    path.write_bytes(b"%PDF-1.4\n")

    with patch("zhiji_backend.ingest.pdf_ocr.validate_pdf_safety", side_effect=ValueError("PDF 页数超过限制")) as validate:
        with patch("zhiji_backend.ingest.pdf_ocr.detect_pdf_type") as detect:
            with pytest.raises(ValueError, match="页数"):
                process_pdf(path)

    assert validate.call_args.kwargs["max_pages"] == 300
    detect.assert_not_called()
