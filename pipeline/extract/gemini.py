"""Gemini-based extraction (STUB).

Uses a gemini-2.0-flash-class model to convert already-public source text into
structured case candidates. Gemini SUMMARIZES and CLASSIFIES public text; it
never invents factual claims.

Phase 0 obligations enforced here:
- The request is constrained by ``schemas/extraction.schema.json`` via
  ``response_schema`` -- a schema that has NO victim/name/address fields at all,
  so the model output is structurally incapable of carrying victim identity.
- The prompt forces ``"victim": null`` regardless.
- Post-extraction, every candidate still passes through ``pipeline.sanitize``
  (the last gate before disk) -- extraction output is never trusted directly.
- Each candidate carries a ``confidence`` in 0..1; < 0.8 is quarantined to
  ``data/_review/`` and never auto-published.

Operational concerns (implemented in the pipeline phase): batched requests,
jittered exponential backoff, a daily token cap, and a per-run cost log.
"""

from __future__ import annotations

from typing import Any

from pipeline.sources.base import RawDocument

__all__ = ["extract"]


def extract(docs: list[RawDocument]) -> list[dict[str, Any]]:
    """Extract PRE-sanitized case candidates from already-public documents.

    Returns dicts shaped by ``schemas/extraction.schema.json`` (no PII fields).
    Callers MUST still run each result through :func:`pipeline.sanitize.sanitize_record`
    before the data touches disk.

    TODO(pipeline-phase): implement batched, backoff-guarded, token-capped calls
    to the Gemini API with a response_schema constraint and per-run cost logging.
    """
    raise NotImplementedError("extract is implemented in the pipeline phase")
