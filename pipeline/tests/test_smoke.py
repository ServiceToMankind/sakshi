"""Import smoke tests for the stable scaffold interfaces.

Keeps the package importable and the source-interface contract covered while the
data-acquisition modules (fetch/extract/dedupe/shard) are still stubs.
"""

from __future__ import annotations

import pipeline
from pipeline.sources.base import RawDocument, Source


def test_package_imports() -> None:
    assert pipeline.__doc__ is not None


def test_raw_document_holds_provenance() -> None:
    doc = RawDocument(
        url="https://example.invalid/doc",
        publisher="eCourts",
        fetched_at="2026-07-09",
        text="Already-public order text.",
    )
    assert doc.url == "https://example.invalid/doc"
    assert doc.publisher == "eCourts"
    assert doc.fetched_at == "2026-07-09"
    assert doc.text.startswith("Already-public")


def test_source_protocol_is_runtime_checkable() -> None:
    class _Dummy:
        def fetch(self) -> list[RawDocument]:
            return []

    assert isinstance(_Dummy(), Source)
