"""Stable source-interface contract shared by every fetcher.

A ``Source`` yields ``RawDocument`` objects of ALREADY-PUBLIC text. Nothing here
performs extraction or interpretation; downstream stages (extract -> sanitize)
are responsible for ensuring victim identity never survives to disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["RawDocument", "Source"]


@dataclass(frozen=True, slots=True)
class RawDocument:
    """A single unit of already-public source text, with provenance.

    Attributes:
        url: Canonical public URL the text was retrieved from.
        publisher: Court or outlet name (e.g. "eCourts", "The Hindu").
        fetched_at: ISO ``YYYY-MM-DD`` date the document was retrieved.
        text: The already-public text payload (judgment, order, article body).
    """

    url: str
    publisher: str
    fetched_at: str
    text: str


@runtime_checkable
class Source(Protocol):
    """Interface every source module implements."""

    async def fetch(self) -> list[RawDocument]:
        """Retrieve documents from this source, honouring per-host politeness."""
        ...
