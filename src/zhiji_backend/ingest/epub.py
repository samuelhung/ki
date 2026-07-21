"""EPUB text extraction — zero-dependency, pure stdlib.

EPUB is a ZIP archive containing XHTML pages. We extract text by:
1. Opening the ZIP container
2. Reading container.xml to locate the root .opf file
3. Parsing .opf for metadata (title) + reading order (spine)
4. Stripping HTML tags from each chapter XHTML
5. Concatenating with chapter markers

No scanning/OCR needed — EPUBs are always text-based.
"""

from __future__ import annotations

import html.parser
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from ..security.file_intake import EpubLimits, validate_epub

logger = logging.getLogger(__name__)

# EPUB namespace map
_NS = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf":       "http://www.idpf.org/2007/opf",
    "dc":        "http://purl.org/dc/elements/1.1/",
}


class _HTMLStripper(html.parser.HTMLParser):
    """Accumulate text content, skipping scripts/styles/images."""

    _SKIP_TAGS = {"script", "style", "img", "br", "hr"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, _attrs) -> None:
        if tag in self._SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip > 0:
            self._skip -= 1
        # Block-level tags → newline
        if tag in {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "section"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if text:
            self.parts.append(text)


def _strip_html(html_text: str) -> str:
    """Remove HTML tags and return plain text."""
    stripper = _HTMLStripper()
    stripper.feed(html_text)
    return " ".join(stripper.parts)


def _strip_xml_comments(xml_bytes: bytes) -> bytes:
    """Strip XML comments to avoid '--' inside comments breaking Expat.

    Some EPUB generators (e.g. KindleGen) emit meta tags with '--' inside
    XML comment blocks, which is illegal per XML 1.0 and rejected by Expat.
    """
    return re.sub(rb'<!--.*?-->', b'', xml_bytes, flags=re.DOTALL)


def _find_opf_path(zf: zipfile.ZipFile) -> str:
    """Locate the OPF root file path from META-INF/container.xml."""
    try:
        container_xml = zf.read("META-INF/container.xml")
    except KeyError:
        raise RuntimeError("无效 EPUB：缺少 META-INF/container.xml")

    container_xml = _strip_xml_comments(container_xml)
    root = ET.fromstring(container_xml)
    elem = root.find(".//container:rootfile", _NS)
    if elem is None:
        raise RuntimeError("无效 EPUB：container.xml 中找不到 rootfile")
    return elem.attrib.get("full-path", "")


def _extract_opf_meta(zf: zipfile.ZipFile, opf_path: str) -> tuple[str, list[str]]:
    """Extract title and ordered spine item paths from OPF."""
    opf_xml = zf.read(opf_path)
    cleaned = opf_xml.decode("utf-8")
    # Strip XML comments before parsing — some EPUB generators put '--' inside
    # comments (e.g. title like 盐铁论--xxx), which is illegal in XML.
    cleaned = re.sub(r'<!--.*?-->', '', cleaned, flags=re.DOTALL)
    # Remove default namespace so we don't have to prefix every tag
    cleaned = cleaned.replace('xmlns="http://www.idpf.org/2007/opf"', "")
    root = ET.fromstring(cleaned)

    # Title
    title = ""
    for tag in (".//{http://purl.org/dc/elements/1.1/}title", ".//dc:title"):
        elem = root.find(tag, _NS) if "dc:title" not in tag else _find_dc(root, "title")
        if elem is not None and elem.text:
            title = elem.text.strip()
            break

    # Spine → ordered list of itemref idref values
    spine: list[str] = []
    spine_elem = root.find("spine")
    if spine_elem is not None:
        for itemref in spine_elem.findall("itemref"):
            spine.append(itemref.attrib.get("idref", ""))

    # Manifest → id → href mapping
    id_to_href: dict[str, str] = {}
    manifest = root.find("manifest")
    if manifest is not None:
        for item in manifest.findall("item"):
            iid = item.attrib.get("id", "")
            href = item.attrib.get("href", "")
            if iid and href:
                id_to_href[iid] = href

    # Resolve spine idrefs to hrefs, relative to OPF directory
    opf_dir = Path(opf_path).parent
    chapter_paths: list[str] = []
    for idref in spine:
        href = id_to_href.get(idref)
        if href:
            resolved = str(opf_dir / href) if str(opf_dir) != "." else href
            chapter_paths.append(resolved)

    return title, chapter_paths


def _find_dc(root: ET.Element, tag_suffix: str) -> ET.Element | None:
    """Find a Dublin Core element inside <metadata>."""
    metadata = root.find("metadata")
    if metadata is None:
        return None
    for child in metadata:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == tag_suffix:
            return child
    return None


def _extract_chapters(
    zf: zipfile.ZipFile,
    chapter_paths: list[str],
    *,
    max_text_bytes: int = EpubLimits().max_text,
) -> str:
    """Read and strip HTML from each chapter, returning concatenated text."""
    parts: list[str] = []
    text_bytes = 0
    for i, cpath in enumerate(chapter_paths, 1):
        try:
            html = zf.read(cpath).decode("utf-8", errors="replace")
        except KeyError:
            logger.warning("EPUB 章节缺失: %s", cpath)
            continue
        text = _strip_html(html)
        if text.strip():
            part = f"--- 第 {i} 章 ---\n{text}"
            text_bytes += len(part.encode("utf-8")) + (2 if parts else 0)
            if text_bytes > max_text_bytes:
                raise RuntimeError("EPUB 提取文字大小超过限制")
            parts.append(part)
    return "\n\n".join(parts)


def process_epub(path: Path, *, title: str = "") -> dict:
    """Extract full text from an EPUB file.

    Returns dict with keys: title, topic, text
    """
    validate_epub(path)
    try:
        zf = zipfile.ZipFile(str(path), "r")
    except zipfile.BadZipFile:
        raise RuntimeError("无效 EPUB：无法作为 ZIP 打开")
    except Exception as e:
        raise RuntimeError(f"打开 EPUB 失败: {e}")

    try:
        # 1. Locate OPF
        opf_path = _find_opf_path(zf)
        logger.info("EPUB OPF: %s", opf_path)

        # 2. Parse metadata + spine
        epub_title, chapter_paths = _extract_opf_meta(zf, opf_path)
        logger.info("EPUB: title=%r, chapters=%d", epub_title, len(chapter_paths))

        # 3. Extract text
        text = _extract_chapters(zf, chapter_paths)
        if not text.strip():
            raise RuntimeError("EPUB 未提取到任何文字内容")

        final_title = title or epub_title or path.stem
        return {
            "title": final_title,
            "topic": "",
            "text": text,
        }
    finally:
        zf.close()
