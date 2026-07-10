"""Indian Kanoon source — a court-record MIRROR via its documented API.

Indian Kanoon (https://api.indiankanoon.org) mirrors Indian judgments and orders
(Supreme Court, High Courts, some district courts, tribunals). Its API is the ONE
legitimate, ToS-covered way to pull court records programmatically without
touching a CAPTCHA — direct eCourts case-search is CAPTCHA-gated and off-limits.

Access is token-authenticated and PAID: set ``INDIANKANOON_API_TOKEN`` (from repo
secrets, never committed). WITHOUT the token this source fetches nothing — it never
fabricates. Requests go through the shared :class:`PoliteClient` so the honest
User-Agent, per-host rate limit, and backoff apply exactly as for every other
source.

Only already-public judgment metadata (title, court, date, headline snippet) is
rendered into RawDocument text; extraction + sanitize still enforce that no victim
identity survives, regardless of what a source returns.
"""

from __future__ import annotations

import json
import os
from datetime import date

from pipeline import config
from pipeline.sources.base import RawDocument
from pipeline.sources.http import HttpPoster

__all__ = ["IndianKanoonSource", "parse_search_response", "render_doc_text"]

_SEARCH_URL = "https://api.indiankanoon.org/search/"


def _api_token() -> str | None:
    token = os.environ.get("INDIANKANOON_API_TOKEN", "").strip()
    return token or None


def _doc_publisher(docsource: str, fallback: str) -> str:
    """The docsource IS the provenance authority.

    A judgment's docsource is its court (e.g. "Delhi High Court"), which downstream
    classifies as source_type=court; anything else (an indexed news item, or a
    missing docsource) stays media-grade so accused names are withheld.
    """
    return docsource.strip() or fallback


def render_doc_text(doc: dict[str, object]) -> str:
    """Render one Indian Kanoon search hit into a compact line of public text."""
    parts: list[str] = []
    for key, label in (
        ("title", "Title"),
        ("docsource", "Court"),
        ("publishdate", "Date"),
        ("headline", "Excerpt"),
    ):
        value = doc.get(key)
        if value in (None, "", []):
            continue
        parts.append(f"{label}: {value}")
    return ". ".join(parts)


def parse_search_response(
    payload: str, fetched_at: str, *, fallback_publisher: str = "Indian Kanoon"
) -> list[RawDocument]:
    """Parse an Indian Kanoon ``/search/`` JSON payload into RawDocuments.

    Expects an object with a ``"docs"`` list (each with ``tid`` + metadata). Each
    document's publisher is its ``docsource`` (the court), so a judgment classifies
    as court-grade and an indexed news item stays media-grade. Malformed JSON, or a
    hit without an id, is skipped rather than raising.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    docs_in = data.get("docs", []) if isinstance(data, dict) else []

    docs: list[RawDocument] = []
    for hit in docs_in:
        if not isinstance(hit, dict):
            continue
        tid = hit.get("tid")
        text = render_doc_text(hit)
        if tid in (None, "") or not text:
            continue
        docs.append(
            RawDocument(
                url=f"https://indiankanoon.org/doc/{tid}/",
                publisher=_doc_publisher(str(hit.get("docsource", "")), fallback_publisher),
                fetched_at=fetched_at,
                text=text,
            )
        )
    return docs


class IndianKanoonSource:
    """A :class:`~pipeline.sources.base.Source` over the Indian Kanoon search API."""

    def __init__(
        self,
        client: HttpPoster,
        queries: tuple[str, ...],
        *,
        publisher: str = "Indian Kanoon",
        fetched_at: str | None = None,
        token: str | None = None,
    ) -> None:
        self._client = client
        self._queries = queries
        self._publisher = publisher
        self._fetched_at = fetched_at or date.today().isoformat()
        self._token = token if token is not None else _api_token()

    async def fetch(self) -> list[RawDocument]:
        """Query each search string, capped at the per-run doc budget (cost control).

        No token => fetch nothing (safe). Indian Kanoon bills per document, so the
        run stops once ``config.IK_MAX_DOCS_PER_RUN`` documents are collected.
        """
        if not self._token:
            return []
        headers = {"Authorization": f"Token {self._token}"}
        docs: list[RawDocument] = []
        for query in self._queries:
            if len(docs) >= config.IK_MAX_DOCS_PER_RUN:
                break
            response = await self._client.post(
                _SEARCH_URL, data={"formInput": query, "pagenum": "0"}, headers=headers
            )
            if response is None or response.status_code != 200:
                continue
            docs.extend(
                parse_search_response(
                    response.text, self._fetched_at, fallback_publisher=self._publisher
                )
            )
        return docs[: config.IK_MAX_DOCS_PER_RUN]
