"""Tests for the Indian Kanoon court-record source (offline, via a fake poster).

Exercises the search → statute-pre-filter → judgment-body fetch flow. No network: a fake
poster maps /search/ and /doc/ URLs to canned JSON. Judgment text here is synthetic
(TESTVILLE, obviously fake) — never real PII (CLAUDE.md §2/§3).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from pipeline.sources.indiankanoon import (
    IndianKanoonSource,
    hit_qualifies,
    newest_first,
    parse_search_hits,
    render_judgment_text,
)

_SEARCH_JSON = json.dumps(
    {
        "docs": [
            {
                "tid": 12345,
                "title": "State vs Accused",
                "docsource": "Delhi High Court",
                "publishdate": "2026-07-05",
                "headline": "conviction under BNS 64 (rape)",
            },
            {
                "tid": 999,
                "title": "Property dispute",
                "docsource": "Delhi High Court",
                "publishdate": "2026-07-06",
                "headline": "suit for possession under the Transfer of Property Act",
            },
            {"title": "no tid here"},  # skipped: no id
        ]
    }
)
_DOC_JSON = json.dumps(
    {
        "tid": 12345,
        "docsource": "Delhi High Court",
        "title": "State vs Accused",
        "publishdate": "2026-07-05",
        "doc": "<div><script>x()</script><p>Judgment: the accused was convicted under "
        "Section 376 IPC and POCSO. Sentence: 10 years.</p></div>",
    }
)


class _FakePoster:
    """Maps a URL to (status, text). /doc/ URLs share one canned doc unless overridden.

    Like the real API, each search page returns different results: ``pages`` lists the result
    payload per page number, and any page past the end comes back empty.
    """

    def __init__(
        self,
        search: str,
        doc: str,
        *,
        search_status: int = 200,
        doc_status: int = 200,
        pages: list[str] | None = None,
    ):
        self._pages = pages if pages is not None else [search]
        self._doc = doc
        self._search_status = search_status
        self._doc_status = doc_status
        self.calls: list[str] = []
        self.search_forms: list[dict[str, str]] = []

    async def post(
        self,
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        self.calls.append(url)
        if url.endswith("/search/"):
            form = dict(data or {})
            self.search_forms.append(form)
            page = int(form.get("pagenum", "0"))
            text = self._pages[page] if page < len(self._pages) else json.dumps({"docs": []})
            return httpx.Response(self._search_status, text=text)
        return httpx.Response(self._doc_status, text=self._doc)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --- hit_qualifies (the pre-filter that gates billing) ---------------------------------------


def test_hit_qualifies_on_statute_or_offence_keyword() -> None:
    assert hit_qualifies("convicted under Section 376 IPC")  # statute
    assert hit_qualifies("a POCSO matter")  # offence keyword
    assert hit_qualifies("charged with rape")  # bare offence still fetched for IK
    assert hit_qualifies("molestation case")


def test_hit_qualifies_rejects_off_topic_and_empty() -> None:
    assert not hit_qualifies("suit for possession under the Transfer of Property Act")
    assert not hit_qualifies("")


# --- parse_search_hits -----------------------------------------------------------------------


def test_parse_search_hits_extracts_metadata_and_skips_idless() -> None:
    hits = parse_search_hits(_SEARCH_JSON)
    assert [h["tid"] for h in hits] == ["12345", "999"]  # the tid-less hit is dropped
    assert hits[0]["docsource"] == "Delhi High Court"


def test_parse_search_hits_malformed_is_empty() -> None:
    assert parse_search_hits("{bad") == []


def test_parse_search_hits_skips_non_dict_entries() -> None:
    assert parse_search_hits(json.dumps({"docs": [123, "x", {"tid": 7}]})) == [
        {"tid": "7", "title": "", "headline": "", "docsource": "", "publishdate": ""}
    ]


# --- render_judgment_text --------------------------------------------------------------------


def test_render_judgment_text_strips_html_and_prepends_header() -> None:
    text = render_judgment_text(json.loads(_DOC_JSON))
    assert "Court: Delhi High Court" in text
    assert "Section 376 IPC" in text and "POCSO" in text
    assert "<p>" not in text and "x()" not in text  # tags + script content gone


def test_render_judgment_text_bounds_length() -> None:
    big = {"docsource": "X", "doc": "<p>" + ("word " * 5000) + "</p>"}
    assert len(render_judgment_text(big, max_chars=200)) == 200


def test_render_judgment_text_empty_doc_is_empty() -> None:
    assert render_judgment_text({"doc": ""}) == ""
    assert render_judgment_text({"doc": "<p></p>"}) == ""


# --- IndianKanoonSource.fetch ----------------------------------------------------------------


def test_fetch_without_token_yields_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INDIANKANOON_API_TOKEN", raising=False)
    poster = _FakePoster(_SEARCH_JSON, _DOC_JSON)
    source = IndianKanoonSource(poster, queries=("rape doctypes:delhi",), fetched_at="2026-07-10")
    assert _run(source.fetch()) == []
    assert poster.calls == []  # never even calls the API without a token


def test_fetch_prefilters_hits_and_fetches_only_qualifying_bodies() -> None:
    poster = _FakePoster(_SEARCH_JSON, _DOC_JSON)
    source = IndianKanoonSource(
        poster, queries=("rape doctypes:delhi",), fetched_at="2026-07-10", token="t"
    )
    docs = _run(source.fetch())
    assert len(docs) == 1  # only the qualifying hit's body is fetched
    assert docs[0].url == "https://indiankanoon.org/doc/12345/"
    assert docs[0].publisher == "Delhi High Court"  # docsource -> court-grade (tier 1)
    assert "Section 376 IPC" in docs[0].text  # the JUDGMENT body, not a metadata snippet
    # Page 1: 1 search + 1 doc fetch (the off-topic hit 999 was NOT fetched -> not billed).
    # Nothing on it was seen before, so we look at page 2, which is empty, and stop.
    assert poster.calls == [
        "https://api.indiankanoon.org/search/",
        "https://api.indiankanoon.org/doc/12345/",
        "https://api.indiankanoon.org/search/",
    ]
    assert source.stats == {
        "hits": 2,
        "qualifying": 1,
        "fetched": 1,
        "search_errors": 0,
        "doc_errors": 0,
        "error_status": 0,
        "already_seen": 0,
        "pages": 1,
    }


def test_fetch_skips_non_200_search() -> None:
    poster = _FakePoster(_SEARCH_JSON, _DOC_JSON, search_status=503)
    source = IndianKanoonSource(poster, queries=("q",), fetched_at="2026-07-10", token="t")
    assert _run(source.fetch()) == []
    assert source.stats["hits"] == 0
    assert source.stats["search_errors"] == 1 and source.stats["error_status"] == 503


def test_rejected_token_stops_after_one_search_and_is_recorded() -> None:
    """A 403 (token/credit rejected — the 2026-09-10..10-11 outage) is recorded, not read as a
    quiet day, and the source stops instead of paying for every remaining query."""
    poster = _FakePoster(_SEARCH_JSON, _DOC_JSON, search_status=403)
    source = IndianKanoonSource(
        poster, queries=("q1", "q2", "q3"), fetched_at="2026-07-10", token="t"
    )
    assert _run(source.fetch()) == []
    assert poster.calls == ["https://api.indiankanoon.org/search/"]  # one call, then stop
    assert source.stats["search_errors"] == 1 and source.stats["error_status"] == 403


def test_transient_search_error_does_not_stop_later_queries() -> None:
    poster = _FakePoster(_SEARCH_JSON, _DOC_JSON, search_status=503)
    source = IndianKanoonSource(poster, queries=("q1", "q2"), fetched_at="2026-07-10", token="t")
    _run(source.fetch())
    assert source.stats["search_errors"] == 2  # a 503 is retried on the next query


def test_fetch_skips_non_200_doc() -> None:
    poster = _FakePoster(_SEARCH_JSON, _DOC_JSON, doc_status=404)
    source = IndianKanoonSource(poster, queries=("q",), fetched_at="2026-07-10", token="t")
    assert _run(source.fetch()) == []
    assert source.stats == {  # qualified, but the body 404'd
        "hits": 2,
        "qualifying": 1,
        "fetched": 0,
        "search_errors": 0,
        "doc_errors": 1,
        "error_status": 404,
        "already_seen": 0,
        "pages": 1,
    }


def test_fetch_respects_per_run_doc_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """The per-document billing budget caps how many judgment bodies a run fetches."""
    from pipeline import config

    monkeypatch.setattr(config, "IK_MAX_DOCS_PER_RUN", 1)
    # Two qualifying hits across the payload; budget of 1 stops after the first body.
    search = json.dumps(
        {
            "docs": [
                {"tid": 1, "title": "A", "headline": "rape POCSO", "docsource": "HC"},
                {"tid": 2, "title": "B", "headline": "Section 376 IPC", "docsource": "HC"},
            ]
        }
    )
    poster = _FakePoster(search, _DOC_JSON)
    source = IndianKanoonSource(poster, queries=("q1", "q2"), fetched_at="2026-07-10", token="t")
    docs = _run(source.fetch())
    assert len(docs) == 1
    assert source.stats["fetched"] == 1  # never billed a second doc


def test_fetch_malformed_doc_payload_skipped() -> None:
    poster = _FakePoster(_SEARCH_JSON, "{bad json")
    source = IndianKanoonSource(poster, queries=("q",), fetched_at="2026-07-10", token="t")
    assert _run(source.fetch()) == []
    assert source.stats["fetched"] == 1  # fetched (billed) but unparseable -> no doc


def test_fetch_non_dict_doc_payload_skipped() -> None:
    # Valid JSON but not an object (e.g. an array) -> no judgment text, skipped.
    poster = _FakePoster(_SEARCH_JSON, "[1, 2, 3]")
    source = IndianKanoonSource(poster, queries=("q",), fetched_at="2026-07-10", token="t")
    assert _run(source.fetch()) == []
    assert source.stats["fetched"] == 1


def _hits_page(*tids: int) -> str:
    return json.dumps(
        {
            "docs": [
                {
                    "tid": tid,
                    "title": "State vs Accused",
                    "docsource": "Delhi High Court",
                    "publishdate": "2026-10-01",
                    "headline": "conviction under BNS 64 (rape)",
                }
                for tid in tids
            ]
        }
    )


def test_searches_ask_for_the_newest_judgments_first() -> None:
    poster = _FakePoster(_SEARCH_JSON, _DOC_JSON)
    source = IndianKanoonSource(
        poster, queries=("q doctypes:delhi",), fetched_at="2026-10-11", token="t"
    )
    _run(source.fetch())
    assert poster.search_forms[0]["formInput"] == "q doctypes:delhi sortby:mostrecent"
    assert newest_first("q sortby:leastrecent") == "q sortby:leastrecent"  # an explicit sort wins


def test_already_handled_judgments_are_not_paid_for_again_and_paging_stops() -> None:
    """Newest first: once a page has a judgment we handled before, everything after it is
    older, so we stop there. We never pay to download a handled judgment twice."""
    poster = _FakePoster(
        "", _DOC_JSON, pages=[_hits_page(1, 2), _hits_page(3, 4), _hits_page(5, 6)]
    )
    handled = {"https://indiankanoon.org/doc/4/"}
    source = IndianKanoonSource(
        poster, queries=("q",), fetched_at="2026-10-11", token="t", seen=handled.__contains__
    )
    docs = _run(source.fetch())
    assert [d.url for d in docs] == [
        "https://indiankanoon.org/doc/1/",
        "https://indiankanoon.org/doc/2/",
        "https://indiankanoon.org/doc/3/",
    ]
    assert len(poster.search_forms) == 2  # page 3 is never requested
    assert "https://api.indiankanoon.org/doc/4/" not in poster.calls
    assert source.stats["already_seen"] == 1 and source.stats["pages"] == 2


def test_paging_stops_at_the_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from pipeline import config

    monkeypatch.setattr(config, "IK_MAX_PAGES_PER_QUERY", 2)
    poster = _FakePoster("", _DOC_JSON, pages=[_hits_page(1), _hits_page(2), _hits_page(3)])
    source = IndianKanoonSource(poster, queries=("q",), fetched_at="2026-10-11", token="t")
    _run(source.fetch())
    assert len(poster.search_forms) == 2
