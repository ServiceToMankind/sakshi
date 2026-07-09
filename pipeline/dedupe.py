"""Case-anchored deduplication (STUB).

Deduplication is CASE-ANCHORED, never identity-anchored: cases are matched on
FIR number, court case number (CNR), police station, district, date, court --
NEVER on victim identity (which is never ingested in the first place).

Matching strategy (implemented in the pipeline phase):
- Exact match on CNR, or on (station, FIR number).
- Fuzzy match via rapidfuzz on district + date (+-3 days) + offence sections +
  court, above a tuned threshold.

Merge policy when two records are judged the same case:
- Court records beat media records.
- A newer status beats an older status.
- ``sources[]`` is unioned.
Ambiguous pairs are NOT auto-merged; they are routed to ``data/_review/`` for
human adjudication and excluded from the published site.
"""

from __future__ import annotations

from typing import Any

__all__ = ["dedupe", "is_same_case", "merge_records"]


def is_same_case(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return True if ``a`` and ``b`` are the same case by case-anchored keys.

    TODO(pipeline-phase): exact CNR / (station, FIR) match, then fuzzy
    district/date(+-3d)/sections/court match via rapidfuzz.
    """
    raise NotImplementedError("is_same_case is implemented in the pipeline phase")


def merge_records(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Merge two same-case records per the merge policy.

    Court beats media; newer status beats older; ``sources[]`` is unioned.

    TODO(pipeline-phase): implement the merge policy above.
    """
    raise NotImplementedError("merge_records is implemented in the pipeline phase")


def dedupe(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deduplicate ``records`` case-anchored.

    Returns ``(deduped, review_queue)`` where ``review_queue`` holds ambiguous
    pairs destined for ``data/_review/`` rather than auto-publication.

    TODO(pipeline-phase): implement clustering + merge, routing ambiguity to review.
    """
    raise NotImplementedError("dedupe is implemented in the pipeline phase")
