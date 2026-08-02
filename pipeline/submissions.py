"""Community case submissions — a LEAD, never a published record (§6).

Anyone can file a "Case submission" issue (label ``case-submission``) with a public source
URL + non-identifying hints. This module parses those issues into structured submissions;
:class:`pipeline.sources.submissions.SubmissionsSource` then fetches each URL so it enters
the daily ``discover`` run as a seed and passes through EVERY existing gate — extraction,
grounded verification, the minor projection, sanitize, ``pii_guard``. A submission is never
published as-is, and a URL that cannot be fetched or extracted yields nothing (no
fabrication from a bare hint).

Non-identifying by construction: only a URL + state/district/month are read here. Any victim
detail a submitter nonetheless typed is stripped downstream exactly like any source text.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["Submission", "load_submissions", "parse_issue_body", "parse_submission_issues"]

_URL_RE = re.compile(r"https?://[^\s)]+")

# GitHub issue-form field HEADINGS (the rendered label) -> submission field. The form's field
# `id` is not in the issue body; the label heading is, as "### <label>".
_FIELD_HEADINGS = {
    "Public source URL": "url",
    "State / UT": "state",
    "District": "district",
    "Reported month (YYYY-MM) or date (YYYY-MM-DD)": "incident_date",
}


@dataclass(frozen=True)
class Submission:
    """One parsed case submission: a public source URL + non-identifying hints."""

    url: str
    state: str = ""
    district: str = ""
    incident_date: str = ""
    issue_number: int = 0


def parse_issue_body(body: str) -> dict[str, str]:
    """Parse a case-submission issue-form body into ``{field: value}`` by its ``###`` headings."""
    out: dict[str, str] = {}
    parts = re.split(r"(?m)^###[ \t]+(.+?)[ \t]*$", body or "")
    # parts == ['', heading1, value1, heading2, value2, ...]
    for i in range(1, len(parts) - 1, 2):
        field = _FIELD_HEADINGS.get(parts[i].strip())
        value = parts[i + 1].strip()
        if field and value and value != "_No response_":
            out[field] = value
    return out


def parse_submission_issues(issues: list[dict[str, Any]]) -> list[Submission]:
    """Turn GitHub issue objects (each with ``number`` + ``body``) into Submissions that carry
    a usable URL. An issue with no parseable URL is skipped — a lead needs a source."""
    subs: list[Submission] = []
    for issue in issues:
        fields = parse_issue_body(str(issue.get("body", "")))
        match = _URL_RE.search(fields.get("url", ""))
        if not match:
            continue
        subs.append(
            Submission(
                url=match.group(0),
                state=fields.get("state", ""),
                district=fields.get("district", ""),
                incident_date=fields.get("incident_date", ""),
                issue_number=int(issue.get("number", 0) or 0),
            )
        )
    return subs


def load_submissions(path: Path) -> list[Submission]:
    """Load submissions from a JSON dump of open case-submission issues (a ``gh issue list``
    output). Returns ``[]`` if the file is absent or unreadable."""
    if not path.exists():
        return []
    try:
        issues = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return parse_submission_issues(issues if isinstance(issues, list) else [])
