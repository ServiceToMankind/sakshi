"""Pipeline orchestrator (STUB): fetch -> extract -> sanitize -> dedupe -> validate -> shard.

Wires the daily run end to end:

1. Fetch    -- each configured Source yields ``RawDocument`` objects of
              already-public text, respecting per-host politeness.
2. Extract  -- Gemini produces response_schema-constrained candidates that are
              structurally incapable of holding victim identity.
3. Sanitize -- EVERY candidate passes through ``pipeline.sanitize`` (the last
              gate before disk) to strip any forbidden field or PII-shaped value.
4. Dedupe   -- case-anchored merge; ambiguous pairs routed to ``data/_review/``.
5. Validate -- every record checked against ``schemas/case.schema.json``.
6. Shard    -- atomic, idempotent regeneration of the ``data/`` tree, then
              ``scripts/pii_guard`` as the final assertion.

On failure, or when the review queue exceeds 20, the daily Action auto-opens an
issue rather than publishing partial data.

Full wiring lands in the pipeline phase.
"""

from __future__ import annotations


def main() -> int:
    """Run the daily pipeline. Returns a process exit code.

    TODO(pipeline-phase): wire the six stages above with structured logging,
    a daily token cap, and review-queue/failure issue creation.
    """
    raise NotImplementedError("pipeline orchestration is implemented in the pipeline phase")


if __name__ == "__main__":
    raise SystemExit(main())
