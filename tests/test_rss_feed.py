from __future__ import annotations

from zhiji_backend import rss_feed

ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title><![CDATA[<b>First</b> item]]></title>
    <link href="https://example.com/a" />
    <id>atom-1</id>
    <updated>2026-05-21T08:00:00Z</updated>
    <summary><![CDATA[First&nbsp; summary]]></summary>
  </entry>
  <entry>
    <title>Fallback id</title>
    <link>https://example.com/b</link>
    <updated>Thu, 21 May 2026 09:00:00 GMT</updated>
  </entry>
</feed>
"""


def test_parse_rss_items_supports_atom_links_dates_and_stable_fallback_ids():
    items = rss_feed.parse_rss_items(ATOM_FEED)

    assert items == [
        {
            "external_id": "atom-1",
            "title": "First item",
            "url": "https://example.com/a",
            "published_at": "2026-05-21T08:00:00+00:00",
            "raw_summary": "First summary",
        },
        {
            "external_id": rss_feed.stable_item_id(
                "Fallback id",
                "https://example.com/b",
                "2026-05-21T09:00:00+00:00",
            ),
            "title": "Fallback id",
            "url": "https://example.com/b",
            "published_at": "2026-05-21T09:00:00+00:00",
            "raw_summary": "",
        },
    ]


def test_extract_text_removes_boilerplate_and_honors_max_chars():
    html = """
    <html><body>
      <nav>Site search</nav>
      <article><h1>Useful title</h1><p>Useful article body.</p></article>
      <script>hidden()</script>
    </body></html>
    """

    assert rss_feed.extract_text(html, max_chars=200) == (
        "Useful title\n\nUseful article body."
    )
    assert rss_feed.extract_text(
        "<p>First line</p><p>Second line</p>", max_chars=17
    ) == ("First line")


def test_parse_datetime_preserves_invalid_nonempty_values():
    assert rss_feed.parse_datetime(None) is None
    assert rss_feed.parse_datetime("  ") is None
    assert rss_feed.parse_datetime("not-a-date") == "not-a-date"
