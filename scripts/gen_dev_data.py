#!/usr/bin/env python3
"""Generate a realistic SYNTHETIC data/ tree for frontend development.

Every record is obviously fake (district "TESTVILLE-*", example.invalid URLs,
"(synthetic)" accused names). This exercises every UI state — multiple states,
years, and statuses including ACQUITTED and QUASHED, minors, and a spread of
pending durations — WITHOUT any real case data. It runs the synthetic records
through the real sanitize -> project -> dedupe -> shard stages, so the output is
byte-identical in shape to a production run.

Default output is ``site/public/data/`` (git-ignored, served by Vite at /data/ in
dev). Never commit this tree; production copies the real committed ``data/``.

Usage:
    python scripts/gen_dev_data.py [--out site/public/data] [--run-date 2026-07-09]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pipeline.dedupe import dedupe  # noqa: E402
from pipeline.sanitize import sanitize_record  # noqa: E402
from pipeline.shard import write_shards  # noqa: E402
from pipeline.validate import load_schema, project_to_schema  # noqa: E402

_STATES = ["TG", "AP", "MH", "DL", "TN", "KA", "UP", "WB"]
_YEARS = [2024, 2025, 2026]
_CATEGORIES = ["sexual_assault", "rape", "pocso", "acid_attack", "harassment"]
_STATUSES = [
    "FIR_FILED",
    "CHARGESHEETED",
    "UNDER_TRIAL",
    "APPEAL_PENDING",
    "CONVICTED",
    "ACQUITTED",
    "QUASHED",
    "CLOSED",
]
_SECTIONS = [["BNS 64"], ["BNS 64", "POCSO 6"], ["BNS 65"], ["BNS 124"], ["BNS 79"]]
_COURT_STATUSES = {"CONVICTED", "ACQUITTED", "QUASHED", "APPEAL_PENDING", "CLOSED"}


def _build_synthetic() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    serial = 0
    for si, state in enumerate(_STATES):
        for yi, year in enumerate(_YEARS):
            for k in range(2):  # two cases per state/year
                serial += 1
                status = _STATUSES[(si + yi + k) % len(_STATUSES)]
                category = _CATEGORIES[(si + k) % len(_CATEGORIES)]
                minor = (serial % 3) == 0
                month = ((serial * 5) % 12) + 1
                day = ((serial * 7) % 27) + 1
                date = f"{year}-{month:02d}-{day:02d}"
                # An accused name only exists when it comes from a court record.
                from_court = status in _COURT_STATUSES
                accused_name = (
                    f"Accused {state}{serial} (synthetic court record)" if from_court else None
                )
                publisher = "eCourts" if from_court else "The Example Herald"
                records.append(
                    {
                        "cnr": f"DEV{state}-{serial:04d}-{year}",
                        "fir_ref": {
                            "station": f"TESTVILLE {state} PS",
                            "number": f"{serial}/{year}",
                        },
                        "state": state,
                        "district": f"TESTVILLE-{state}",
                        "incident_reported_date": date,
                        "offence_sections": _SECTIONS[serial % len(_SECTIONS)],
                        "category": category,
                        "minor_involved": minor,
                        "status": status,
                        "status_history": [
                            {"status": "FIR_FILED", "date": date, "source": 0},
                            {"status": status, "date": f"{year}-12-01", "source": 0},
                        ],
                        "accused": [
                            {
                                "label": "Accused #1",
                                "name_public_court_record": accused_name,
                                "status": status,
                            }
                        ],
                        "court": {
                            "name": f"Special Court, TESTVILLE-{state}",
                            "next_hearing": f"{year + 1}-02-15"
                            if status == "UNDER_TRIAL"
                            else None,
                        },
                        "summary": (
                            f"Synthetic development fixture for {state} ({year}). Neutral, "
                            "non-graphic placeholder summary. Contains no real or victim data."
                        ),
                        "sources": [
                            {
                                "url": f"https://example.invalid/{state.lower()}/{serial}",
                                "publisher": publisher,
                                "retrieved": "2026-07-09",
                            }
                        ],
                        "confidence": 0.9,
                        "victim": None,  # forced null; dropped by the sanitizer
                    }
                )
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a synthetic dev data/ tree.")
    parser.add_argument("--out", type=Path, default=_REPO_ROOT / "site" / "public" / "data")
    parser.add_argument("--run-date", default="2026-07-09")
    args = parser.parse_args(argv)

    schema = load_schema()
    records = [project_to_schema(sanitize_record(r), schema) for r in _build_synthetic()]
    published, review = dedupe(records)
    result = write_shards(published, args.out, run_date=args.run_date)
    print(
        f"Wrote {result.published} synthetic records to {args.out} "
        f"across {len(result.shards)} shard(s); {len(review)} to review."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
