"""Tests for the RSS and eCourts source parsers and fetch loops (offline)."""

from __future__ import annotations

import asyncio
from typing import Any

from pipeline.sources import ecourts, rss_media
from pipeline.sources.rss_media import Feed, RssMediaSource, parse_feed

_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Example</title>
  <item>
    <title>TESTVILLE case listed</title>
    <description>A case at the Special POCSO Court, &lt;b&gt;TESTVILLE&lt;/b&gt;.</description>
    <link>https://example.invalid/news/1</link>
  </item>
  <item>
    <title>No link item</title>
    <description>ignored</description>
  </item>
</channel></rss>"""

_ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom TESTVILLE update</title>
    <summary>Under trial in TESTVILLE.</summary>
    <link href="https://example.invalid/atom/1"/>
  </entry>
</feed>"""


class _Resp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class _FakeClient:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self.mapping = mapping

    async def get(self, url: str) -> Any:
        return self.mapping.get(url)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --- RSS / Atom parsing ------------------------------------------------------


def test_parse_rss_extracts_items_with_links_only() -> None:
    docs = parse_feed(_RSS, "The Example Herald", "2026-07-09")
    assert len(docs) == 1  # the link-less item is dropped
    assert docs[0].url == "https://example.invalid/news/1"
    assert "TESTVILLE" in docs[0].text
    assert "<b>" not in docs[0].text  # HTML stripped


def test_parse_atom_entry() -> None:
    docs = parse_feed(_ATOM, "The Example Herald", "2026-07-09")
    assert len(docs) == 1
    assert docs[0].url == "https://example.invalid/atom/1"
    assert "Under trial" in docs[0].text


def test_parse_malformed_feed_is_empty() -> None:
    assert parse_feed("<not xml", "x", "2026-07-09") == []


def test_rss_source_fetch_skips_none_and_non_200() -> None:
    feeds = (
        Feed("https://a.invalid/feed", "A"),
        Feed("https://b.invalid/feed", "B"),
        Feed("https://c.invalid/feed", "C"),
    )
    client = _FakeClient(
        {
            "https://a.invalid/feed": _Resp(200, _RSS),
            "https://b.invalid/feed": None,  # robots-disallowed
            "https://c.invalid/feed": _Resp(304, ""),  # unchanged
        }
    )
    source = RssMediaSource(client, feeds=feeds, fetched_at="2026-07-09")
    docs = _run(source.fetch())
    assert len(docs) == 1
    assert docs[0].publisher == "A"


def test_default_feeds_are_established_outlets() -> None:
    publishers = {feed.publisher for feed in rss_media.DEFAULT_FEEDS}
    assert "The Hindu" in publishers


# --- eCourts / NJDG parsing --------------------------------------------------


def test_render_case_text_lists_public_fields_only() -> None:
    text = ecourts.render_case_text(
        {"cnr": "TSHC01-000001-2026", "court": "Special POCSO Court", "sections": ["BNS 64"]}
    )
    assert "CNR: TSHC01-000001-2026" in text
    assert "Sections: BNS 64" in text


def test_parse_ecourts_json_list_and_cases_object() -> None:
    as_list = ecourts.parse_ecourts_json(
        '[{"cnr":"X","court":"C","url":"https://e.invalid/1"}]', "eCourts", "2026-07-09"
    )
    assert len(as_list) == 1 and as_list[0].publisher == "eCourts"

    as_obj = ecourts.parse_ecourts_json(
        '{"cases":[{"cnr":"Y","court":"C","case_url":"https://e.invalid/2"}]}',
        "eCourts",
        "2026-07-09",
    )
    assert len(as_obj) == 1 and as_obj[0].url == "https://e.invalid/2"


def test_parse_ecourts_json_skips_bad_entries_and_malformed() -> None:
    assert ecourts.parse_ecourts_json("{bad json", "eCourts", "2026-07-09") == []
    assert ecourts.parse_ecourts_json('"a string"', "eCourts", "2026-07-09") == []
    # entries without a url or without renderable text are dropped
    docs = ecourts.parse_ecourts_json(
        '[{"cnr":"Z"}, "not-a-dict", {"url":"https://e.invalid/3"}]', "eCourts", "2026-07-09"
    )
    assert docs == []


def test_ecourts_source_fetch_uses_endpoints() -> None:
    client = _FakeClient(
        {
            "https://e.invalid/api": _Resp(
                200, '[{"cnr":"X","court":"C","url":"https://e.invalid/1"}]'
            )
        }
    )
    source = ecourts.EcourtsSource(
        client,
        endpoints=("https://e.invalid/api",),
        fetched_at="2026-07-09",
    )
    docs = _run(source.fetch())
    assert len(docs) == 1


def test_ecourts_endpoints_from_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("ECOURTS_ENDPOINTS", "https://e.invalid/a, https://e.invalid/b")
    source = ecourts.EcourtsSource(_FakeClient({}))
    assert _run(source.fetch()) == []  # both endpoints miss the empty fake client
