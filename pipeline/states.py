"""Canonical Indian state / UT 2-letter codes + alias normalisation.

The extractor sometimes emits a common ALTERNATE code — "TS" for Telangana (canonical
"TG"), "CG" for Chhattisgarh ("CT"), "OR" for Odisha ("OD"), "UK"/"UA" for Uttarakhand
("UT"). Left un-normalised, one state splits into two everywhere it is keyed by code:
the id (``SKS-2026-TS-…`` vs ``…-TG-…``), the per-state shard file, the jurisdiction
scorecard, and ``state_counts``. Normalising to the ONE canonical code (ISO 3166-2:IN,
matching ``site/src/format.js``) keeps a state whole.
"""

from __future__ import annotations

__all__ = ["CANONICAL_STATES", "STATE_ALIASES", "STATE_NAMES", "normalize_state", "state_name"]

# Canonical code -> full display name. MIRRORS site/src/format.js STATE_NAMES exactly (a
# parity test asserts it) so a state reads the same on the site and in the pipeline's
# deterministic minor projection. A state name is public, non-identifying geography.
STATE_NAMES: dict[str, str] = {
    "AP": "Andhra Pradesh",
    "AR": "Arunachal Pradesh",
    "AS": "Assam",
    "BR": "Bihar",
    "CT": "Chhattisgarh",
    "GA": "Goa",
    "GJ": "Gujarat",
    "HR": "Haryana",
    "HP": "Himachal Pradesh",
    "JH": "Jharkhand",
    "KA": "Karnataka",
    "KL": "Kerala",
    "MP": "Madhya Pradesh",
    "MH": "Maharashtra",
    "MN": "Manipur",
    "ML": "Meghalaya",
    "MZ": "Mizoram",
    "NL": "Nagaland",
    "OD": "Odisha",
    "PB": "Punjab",
    "RJ": "Rajasthan",
    "SK": "Sikkim",
    "TN": "Tamil Nadu",
    "TG": "Telangana",
    "TR": "Tripura",
    "UP": "Uttar Pradesh",
    "UT": "Uttarakhand",
    "WB": "West Bengal",
    "DL": "Delhi",
    "JK": "Jammu & Kashmir",
    "LA": "Ladakh",
    "PY": "Puducherry",
    "CH": "Chandigarh",
    "AN": "Andaman & Nicobar",
    "DN": "Dadra & Nagar Haveli and Daman & Diu",
    "LD": "Lakshadweep",
}

# The canonical 2-letter codes the site knows (mirrors site/src/format.js STATE_NAMES).
CANONICAL_STATES = frozenset(
    {
        "AP",
        "AR",
        "AS",
        "BR",
        "CT",
        "GA",
        "GJ",
        "HR",
        "HP",
        "JH",
        "KA",
        "KL",
        "MP",
        "MH",
        "MN",
        "ML",
        "MZ",
        "NL",
        "OD",
        "PB",
        "RJ",
        "SK",
        "TN",
        "TG",
        "TR",
        "UP",
        "UT",
        "WB",
        "DL",
        "JK",
        "LA",
        "PY",
        "CH",
        "AN",
        "DN",
        "LD",
    }
)

# Alternate code -> canonical code.
STATE_ALIASES = {
    "TS": "TG",  # Telangana (Telangana State vehicle code)
    "TL": "TG",  # Telangana (common mis-code / abbreviation; canonical TG)
    "CG": "CT",  # Chhattisgarh
    "OR": "OD",  # Odisha (pre-2011 spelling)
    "UK": "UT",  # Uttarakhand
    "UA": "UT",  # Uttarakhand (older Uttaranchal code)
    "PD": "PY",  # Puducherry
    "DD": "DN",  # Daman & Diu -> Dadra & Nagar Haveli and Daman & Diu (merged)
}


def normalize_state(code: str) -> str:
    """Return the canonical 2-letter state code for ``code`` (upper-cased + aliased).

    An unknown/non-alias code is returned upper-cased as-is (never dropped — a wrong
    code is a data-quality signal a human can catch, not something to silently mangle).
    """
    upper = str(code or "").strip().upper()
    return STATE_ALIASES.get(upper, upper)


def state_name(code: str) -> str:
    """Return the full display name for a state code (canonicalised first), or the
    upper-cased code if it is unrecognised. Used so user-facing text — including the
    deterministic minor projection — never shows a bare two-letter code."""
    canonical = normalize_state(code)
    return STATE_NAMES.get(canonical, canonical)
