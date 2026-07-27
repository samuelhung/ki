from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser

logger = logging.getLogger("knowledge-intelligence")

StripHtml = Callable[[str | None], str]
ChildText = Callable[[ET.Element, Iterable[str]], str | None]
AtomLink = Callable[[ET.Element], str | None]
ParseDatetime = Callable[[str | None], str | None]
StableItemId = Callable[[str, str, str | None], str]

_BLOCK_TAGS = {
    "blockquote",
    "br",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "p",
    "pre",
    "tr",
}
_SKIP_TAGS = {
    "aside",
    "button",
    "footer",
    "form",
    "header",
    "iframe",
    "input",
    "nav",
    "noscript",
    "script",
    "select",
    "style",
    "svg",
    "textarea",
}
_NOISE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"^Skip to content$",
        r"^Site search$",
        r"^Accessibility links$",
        r"^Keyboard shortcuts",
        r"^BBC (News )?Services$",
        r"^NPR\s*$",
        r"^NPR App$",
        r"^Apple Podcasts$",
        r"^Spotify$",
        r"^Amazon Music$",
        r"^iHeart Radio$",
        r"^YouTube Music$",
        r"^RSS link$",
        r"^Subscribe to",
        r"^Share this",
        r"^Copy link",
        r"^Related topics$",
        r"^Explore more$",
        r"^More on this story$",
        r"^Top stories$",
        r"^Follow .+ on",
        r"^Image source,",
        r"^Image caption,",
        r"^\d+ (minutes|hours|days) ago$",
        r"^Published\s",
        r"^\d+ (January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$",
    )
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, _attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip > 0:
            self._skip -= 1
        elif tag in _BLOCK_TAGS - {"br", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip == 0 and (text := data.strip()):
            self.parts.append(text)


def extract_text(html: str, max_chars: int = 5000) -> str:
    """Extract readable text from HTML while removing common boilerplate."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception as exc:
        logger.warning("HTMLParser extraction failed: %s", exc)
    raw = re.sub(r"\n{3,}", "\n\n", "\n".join(parser.parts))
    filtered = [
        line
        for line in raw.split("\n")
        if not any(pattern.match(line.strip()) for pattern in _NOISE_PATTERNS)
    ]
    raw = re.sub(r"\n{3,}", "\n\n", "\n".join(filtered))
    if len(raw) > max_chars:
        raw = raw[:max_chars].rsplit("\n", 1)[0]
    return raw.strip()


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def parse_datetime(value: str | None) -> str | None:
    if not value or not (text := value.strip()):
        return None
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()
    except Exception:
        logger.debug("parsedate_to_datetime failed for %r, trying fromisoformat", text)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()
    except Exception:
        logger.debug("fromisoformat failed for %r, returning raw text", text)
        return text


def child_text(element: ET.Element, names: Iterable[str]) -> str | None:
    wanted = set(names)
    for child in list(element):
        if child.tag.rsplit("}", 1)[-1] in wanted:
            return child.text
    return None


def atom_link(element: ET.Element) -> str | None:
    for child in list(element):
        if child.tag.rsplit("}", 1)[-1] == "link":
            if href := child.attrib.get("href"):
                return href
            if child.text:
                return child.text
    return None


def stable_item_id(title: str, url: str, published_at: str | None) -> str:
    raw = "|".join([title, url, published_at or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_rss_items(
    feed_text: str,
    *,
    strip_html_fn: StripHtml | None = None,
    child_text_fn: ChildText | None = None,
    atom_link_fn: AtomLink | None = None,
    parse_datetime_fn: ParseDatetime | None = None,
    stable_item_id_fn: StableItemId | None = None,
) -> list[dict[str, str | None]]:
    clean_html = strip_html_fn or strip_html
    get_child_text = child_text_fn or child_text
    get_atom_link = atom_link_fn or atom_link
    parse_date = parse_datetime_fn or parse_datetime
    make_stable_id = stable_item_id_fn or stable_item_id
    root = ET.fromstring(feed_text)
    items = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] in {"item", "entry"}
    ]
    parsed: list[dict[str, str | None]] = []
    for item in items:
        title = clean_html(get_child_text(item, ["title"]))
        url = (get_child_text(item, ["link"]) or get_atom_link(item) or "").strip()
        guid = (get_child_text(item, ["guid", "id"]) or "").strip()
        published_at = parse_date(
            get_child_text(item, ["pubDate", "published", "updated", "date"])
        )
        summary = clean_html(
            get_child_text(item, ["description", "summary", "content", "encoded"])
        )
        if not title and not url:
            continue
        parsed.append(
            {
                "external_id": guid or make_stable_id(title, url, published_at),
                "title": title or url,
                "url": url,
                "published_at": published_at,
                "raw_summary": summary,
            }
        )
    return parsed
