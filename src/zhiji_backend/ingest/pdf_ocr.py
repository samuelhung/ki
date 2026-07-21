"""PDF OCR — text extraction + Volcengine OCRNormal for scanned documents.

Text-based PDFs are extracted directly via pymupdf.
Scanned PDFs are rendered page-by-page and sent to Volcengine OCR.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlencode

import requests  # type: ignore

from ..security.file_intake import (
    DOCUMENT_MAX_BYTES,
    OCR_PDF_MAX_BYTES,
    OCR_PDF_MAX_PAGES,
)

logger = logging.getLogger(__name__)

# ── Config ──
OCR_ENDPOINT = "https://visual.volcengineapi.com"
OCR_ACTION = "OCRNormal"
OCR_VERSION = "2020-08-26"
OCR_SERVICE = "cv"
OCR_REGION = "cn-north-1"
OCR_QPS_DELAY = 1.05  # seconds between requests (free tier QPS=1)

TOS_AK = os.getenv("TOS_AK", "")
TOS_SK = os.getenv("TOS_SK", "")

# ── PDF detection ──

_DETECT_PAGES = 5          # sample first N pages for detection
_TEXT_THRESHOLD = 50       # chars/page below this → scan


def _import_pymupdf():
    """Lazy import with friendly error."""
    try:
        import fitz  # pymupdf
        return fitz
    except ImportError:
        raise RuntimeError("缺少依赖 pymupdf：pip install pymupdf")


def validate_pdf_safety(
    path: Path,
    *,
    max_bytes: int,
    max_pages: int | None,
    opener=None,
) -> int:
    """Reject oversized, encrypted, or over-page-limit PDFs before processing."""
    if path.stat().st_size > max_bytes:
        raise ValueError("PDF 大小超过限制")
    open_pdf = opener or _import_pymupdf().open
    doc = open_pdf(str(path))
    try:
        if bool(getattr(doc, "needs_pass", False)) or bool(getattr(doc, "is_encrypted", False)):
            raise ValueError("不支持加密 PDF")
        pages = len(doc)
        if max_pages is not None and pages > max_pages:
            raise ValueError("PDF 页数超过限制")
        return pages
    finally:
        doc.close()


def detect_pdf_type(path: Path) -> str:
    """Return 'text' or 'scan' by sampling first pages."""
    validate_pdf_safety(
        path,
        max_bytes=DOCUMENT_MAX_BYTES,
        max_pages=OCR_PDF_MAX_PAGES,
    )
    fitz = _import_pymupdf()
    doc = fitz.open(str(path))
    try:
        total_chars = 0
        pages_sampled = min(_DETECT_PAGES, len(doc))
        for i in range(pages_sampled):
            text = doc[i].get_text()
            total_chars += len(text.strip())
        avg = total_chars / max(pages_sampled, 1)
        return "text" if avg >= _TEXT_THRESHOLD else "scan"
    finally:
        doc.close()


def extract_text_pdf(path: Path) -> str:
    """Extract full text from a text-based PDF."""
    validate_pdf_safety(
        path,
        max_bytes=DOCUMENT_MAX_BYTES,
        max_pages=OCR_PDF_MAX_PAGES,
    )
    fitz = _import_pymupdf()
    doc = fitz.open(str(path))
    try:
        parts: list[str] = []
        for i in range(len(doc)):
            text = doc[i].get_text().strip()
            if text:
                parts.append(f"--- 第 {i+1} 页 ---\n{text}")
        return "\n\n".join(parts)
    finally:
        doc.close()


# ── Volcengine HMAC-SHA256 signing ──

def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sign(method: str, uri: str, query: str,
          headers: dict[str, str], body: str,
          ak: str, sk: str) -> str:
    """Compute Volcengine V4 signature string."""
    now = datetime.now(timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_date = now.strftime("%Y%m%d")

    # Canonical request
    canonical_headers = "\n".join(
        f"{k}:{v}" for k, v in sorted(headers.items())
    )
    signed_headers = ";".join(sorted(headers.keys()))
    hashed_payload = _sha256_hex(body.encode("utf-8"))

    canonical_request = "\n".join([
        method, uri, query,
        canonical_headers + "\n",
        signed_headers, hashed_payload,
    ])

    # String to sign
    credential_scope = f"{short_date}/{OCR_REGION}/{OCR_SERVICE}/request"
    string_to_sign = "\n".join([
        "HMAC-SHA256", x_date, credential_scope,
        _sha256_hex(canonical_request.encode("utf-8")),
    ])

    # Signature
    k_date = _hmac_sha256(sk.encode("utf-8"), short_date)
    k_region = _hmac_sha256(k_date, OCR_REGION)
    k_service = _hmac_sha256(k_region, OCR_SERVICE)
    k_signing = _hmac_sha256(k_service, "request")
    signature = _hmac_sha256(k_signing, string_to_sign).hex()

    return (
        f"HMAC-SHA256 Credential={ak}/{short_date}/{OCR_REGION}/{OCR_SERVICE}/request, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    ), x_date


# ── OCRNormal API call ──

def ocr_page(image_base64: str) -> str:
    """Call Volcengine OCRNormal for a single page image (base64).

    Returns recognized text, or empty string on failure.
    """
    if not TOS_AK or not TOS_SK:
        raise RuntimeError("TOS_AK/TOS_SK 未配置，无法调用火山 OCR")

    uri = "/"
    query = urlencode({"Action": OCR_ACTION, "Version": OCR_VERSION})
    body = urlencode({"image_base64": image_base64})

    headers = {
        "host": "visual.volcengineapi.com",
        "content-type": "application/x-www-form-urlencoded",
    }
    auth, x_date = _sign("POST", uri, query, headers, body, TOS_AK, TOS_SK)
    headers["Authorization"] = auth
    headers["X-Date"] = x_date

    for attempt in range(3):
        try:
            resp = requests.post(
                f"{OCR_ENDPOINT}/?{query}",
                data=body,
                headers=headers,
                timeout=30,
            )
            data = resp.json()
            if data.get("code") == 10000:
                lines = data.get("data", {}).get("line_texts", [])
                return "\n".join(lines)
            else:
                logger.warning("OCR error: code=%s msg=%s", data.get("code"), data.get("message"))
                if attempt < 2:
                    time.sleep(2 ** attempt)
        except Exception as e:
            logger.warning("OCR request failed (attempt %d): %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(2 ** attempt)

    return ""


# ── Scanned PDF processing ──

def _render_page_to_png(doc, page_index: int, dpi: int = 200) -> bytes:
    """Render a single PDF page to PNG bytes."""
    page = doc[page_index]
    pix = page.get_pixmap(dpi=dpi)
    return pix.tobytes("png")


def ocr_scanned_pdf(
    path: Path,
    on_progress: Callable[[int, int], None] | None = None,
) -> str:
    """Full OCR pipeline for a scanned PDF.

    Args:
        path: Path to PDF file
        on_progress: Optional callback(current_page, total_pages)

    Returns concatenated text from all pages.
    """
    validate_pdf_safety(
        path,
        max_bytes=OCR_PDF_MAX_BYTES,
        max_pages=OCR_PDF_MAX_PAGES,
    )
    fitz = _import_pymupdf()
    doc = fitz.open(str(path))
    total = len(doc)

    parts: list[str] = []
    try:
        for i in range(total):
            # Render page
            png_bytes = _render_page_to_png(doc, i)
            b64 = base64.b64encode(png_bytes).decode("ascii")

            # Rate-limited OCR call
            if i > 0:
                time.sleep(OCR_QPS_DELAY)

            text = ocr_page(b64)
            if text:
                parts.append(f"--- 第 {i+1} 页 ---\n{text}")

            if on_progress:
                on_progress(i + 1, total)
    finally:
        doc.close()

    return "\n\n".join(parts)


# ── Main entry point ──

def process_pdf(
    path: Path,
    title: str = "",
    topic: str = "",
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Process a PDF file and return {title, topic, text}.

    Auto-detects text vs scanned and chooses extraction method.
    """
    validate_pdf_safety(
        path,
        max_bytes=DOCUMENT_MAX_BYTES,
        max_pages=OCR_PDF_MAX_PAGES,
    )
    pdf_type = detect_pdf_type(path)
    logger.info("PDF type: %s (%s)", pdf_type, path.name)

    if pdf_type == "text":
        text = extract_text_pdf(path)
    else:
        text = ocr_scanned_pdf(path, on_progress=on_progress)

    if not title:
        title = path.stem

    return {"title": title, "topic": topic, "text": text}
