#!/usr/bin/env python3
"""Report records that would benefit from a targeted RE-EXTRACTION (§2b).

The data tree is regenerated idempotently by the pipeline — it is NEVER hand-edited. So this
is a DIAGNOSTIC, not a fixer: it lists the published records whose stored facts are thin or were
mis-captured, so a re-extraction pass (with the fuller §2a prompt + the §2b offence-section
normalizer) can be seen to improve them, and an operator can spot what still needs a source.

A record is a candidate when any of:
  - it is a court-sourced MINOR with fewer than two structured accountability facts (so the
    deterministic composer fell back to the flat "A case of ... was recorded." template);
  - its ``offence_sections`` carried act-year garbage (normalising them changes the list) or
    normalises to empty (no usable charge codes → no severity);
  - it is a NON-minor whose summary is very short (a thin account, not the §2a fuller one).

Exit is always 0 — this reports, it never fails a build. Prints one line per candidate with the
reason and the source URLs to re-fetch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:  # pragma: no cover - import-time path shim
    sys.path.insert(0, str(_REPO))

from pipeline.offence_sections import normalize_sections  # noqa: E402

_THIN_SUMMARY_WORDS = 12


def _structured_fact_count(record: dict[str, Any]) -> int:
    """How many of the five structured accountability facts resolved (mirrors the composer)."""
    count = record.get("accused_count")
    has_count = isinstance(count, int) and not isinstance(count, bool) and count >= 1
    actions = [a for a in (record.get("institutional_actions") or []) if a]
    sentence = record.get("sentence_years")
    has_sentence = isinstance(sentence, int) and not isinstance(sentence, bool) and sentence >= 0
    return sum(
        [
            has_count,
            bool(actions),
            record.get("repeat_offence") is True,
            record.get("weapon_or_threat") is True,
            has_sentence,
        ]
    )


def _is_court_sourced(record: dict[str, Any]) -> bool:
    return any(s.get("source_type") == "court" for s in record.get("sources") or [])


def candidate_reasons(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    raw_sections = record.get("offence_sections") or []
    cleaned, unparsed = normalize_sections(raw_sections)
    # Flag only real trouble — junk/act-year tokens surfaced as unparsed, or a section list that
    # normalises to nothing usable — not a mere form change ("Section 376 IPC" -> "IPC 376").
    if unparsed:
        reasons.append(f"offence_sections carry unparsed/act-year junk: {unparsed}")
    if raw_sections and not cleaned:
        reasons.append(f"offence_sections normalise to empty (no usable charges): {raw_sections}")
    if record.get("minor_involved"):
        if _is_court_sourced(record) and _structured_fact_count(record) < 2:
            reasons.append("court-sourced minor with <2 structured facts (composer fell back)")
    else:
        words = len(str(record.get("summary") or "").split())
        if words < _THIN_SUMMARY_WORDS:
            reasons.append(f"non-minor summary is thin ({words} words)")
    return reasons


def scan(data_dir: Path) -> list[tuple[str, list[str], list[str]]]:
    out: list[tuple[str, list[str], list[str]]] = []
    for shard in sorted(data_dir.glob("20*/??.json")):
        for record in json.loads(shard.read_text(encoding="utf-8")):
            reasons = candidate_reasons(record)
            if reasons:
                urls = [s.get("url", "") for s in record.get("sources") or []]
                out.append((str(record.get("id", "<no-id>")), reasons, urls))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    data_dir = Path(argv[0]) if argv else _REPO / "data"
    candidates = scan(data_dir)
    if not candidates:
        print("Re-extraction candidates: none — every published record has usable facts.")
        return 0
    print(f"Re-extraction candidates ({len(candidates)}):")
    for rid, reasons, urls in candidates:
        print(f"  {rid}")
        for reason in reasons:
            print(f"      - {reason}")
        for url in urls:
            print(f"      source: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
