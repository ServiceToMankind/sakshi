"""Graduated auto-publish gate — what may ship WITHOUT a human reading it first.

A record that already passed sanitize + scope + dedupe (i.e. it is in the published
set, so its confidence is at/above :data:`config.CONFIDENCE_REVIEW_THRESHOLD`) is
AUTO-published only when it is demonstrably safe to make a permanent public claim
about it unattended. Everything else is held in the needs-review queue for a human
to promote — never silently dropped, never silently published.

The bar (ALL must hold), and why each exists:

- ``minor_involved`` is ``False`` — a minor's case is only ever human-promoted
  (POCSO s.23 caution; the record is already age-free by projection, but even the
  minimal projection is not auto-shipped).
- No accused is named — every ``name_public_court_record`` is null. A named person,
  even from a court record, is human-reviewed first (presumption of innocence).
- At least one source is DURABLE provenance (court / news_article / press_release).
  A live-blog-only record is a mutable, URL-decaying page — not a durable basis for
  a permanent public claim without human confirmation.
- ``confidence`` >= :data:`config.AUTO_PUBLISH_CONFIDENCE` — the 0.80..0.84 band is
  above the quarantine floor but not confident enough to ship unattended.

This is deliberately CONSERVATIVE: when unsure, hold for review. Weakening it needs a
human-approved issue, same as the other guardrails.
"""

from __future__ import annotations

from typing import Any

from pipeline import config

__all__ = ["DURABLE_SOURCE_TYPES", "auto_publish_eligible", "has_pocso_signal"]

# Provenance classes durable enough to anchor a permanent public claim unattended.
# (live_blog is intentionally excluded — see module docstring.)
DURABLE_SOURCE_TYPES = frozenset({"court", "news_article", "press_release"})


def has_pocso_signal(record: dict[str, Any]) -> bool:
    """True if the record's category or any offence section references POCSO.

    POCSO applies ONLY to minors, so a POCSO signal is a deterministic minor
    indicator independent of the model's ``minor_involved`` boolean — the second
    layer behind that single, model-supplied flag.
    """
    if str(record.get("category", "")).strip().lower() == "pocso":
        return True
    return any("POCSO" in str(section).upper() for section in record.get("offence_sections") or [])


def auto_publish_eligible(record: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return ``(eligible, reasons)`` for auto-publishing ``record`` unattended.

    ``reasons`` lists every failed criterion (for the run report and the review-queue
    comment); it is empty exactly when ``eligible`` is ``True``. A record is evaluated
    independently of run mode — in staged mode the split only labels the report; in
    auto mode it decides what ships to main vs the needs-review queue.
    """
    reasons: list[str] = []
    minor = bool(record.get("minor_involved"))
    if minor:
        reasons.append("minor_involved")
    # POCSO implies a minor. If the case carries a POCSO signal but is flagged
    # non-minor, the model's minor determination is suspect — HOLD it rather than
    # auto-publish a possible minor's re-identifying detail (the record is only
    # age-projected when minor_involved is True, so a false negative would ship
    # day-precise dates). A human resolves the mismatch.
    if not minor and has_pocso_signal(record):
        reasons.append("pocso_minor_mismatch")
    if any(a.get("name_public_court_record") for a in record.get("accused", []) or []):
        reasons.append("named_accused")
    sources = record.get("sources", []) or []
    if not any(s.get("source_type") in DURABLE_SOURCE_TYPES for s in sources):
        reasons.append("live_blog_only")
    if float(record.get("confidence", 0)) < config.AUTO_PUBLISH_CONFIDENCE:
        reasons.append("confidence_below_auto")
    return (not reasons, reasons)
