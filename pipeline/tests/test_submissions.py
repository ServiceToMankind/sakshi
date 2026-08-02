"""Tests for community case submissions (pipeline.submissions + SubmissionsSource, §6)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pipeline.sources.submissions import SubmissionsSource, extract_page_text
from pipeline.submissions import load_submissions, parse_issue_body, parse_submission_issues

_BODY = """### Public source URL

https://ex.invalid/news/1

### State / UT

Telangana

### District

Warangal

### Reported month (YYYY-MM) or date (YYYY-MM-DD)

2026-07

### Confirmations

- [X] The URL is a PUBLIC source (court record or established media), not social media.
- [X] I have NOT included any victim-identifying detail in this submission.
"""


class _Resp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class _FakeClient:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []

    async def get(self, url: str) -> Any:
        self.calls.append(url)
        return self.mapping.get(url)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_parse_issue_body_reads_form_fields() -> None:
    fields = parse_issue_body(_BODY)
    assert fields["url"] == "https://ex.invalid/news/1"
    assert fields["state"] == "Telangana"
    assert fields["district"] == "Warangal"
    assert fields["incident_date"] == "2026-07"


def test_parse_submission_issues_needs_a_url() -> None:
    issues = [
        {"number": 7, "body": _BODY},
        {"number": 8, "body": "### Public source URL\n\n_No response_\n"},  # no URL -> skip
        {"number": 9, "body": "no headings at all"},  # skip
    ]
    subs = parse_submission_issues(issues)
    assert len(subs) == 1
    assert subs[0].url == "https://ex.invalid/news/1"
    assert subs[0].issue_number == 7 and subs[0].state == "Telangana"


def test_load_submissions_absent_or_corrupt(tmp_path: Path) -> None:
    assert load_submissions(tmp_path / "absent.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert load_submissions(bad) == []
    good = tmp_path / "subs.json"
    good.write_text(json.dumps([{"number": 7, "body": _BODY}]), encoding="utf-8")
    assert len(load_submissions(good)) == 1


def test_extract_page_text_strips_and_bounds() -> None:
    html = "<html><script>evil()</script><style>.x{}</style><p>Real case text.</p></html>"
    text = extract_page_text(html)
    assert "Real case text." in text
    assert "evil()" not in text and ".x{}" not in text and "<" not in text


def test_submissions_source_fetches_urls_and_records_robots_disallow() -> None:
    subs = parse_submission_issues(
        [
            {"number": 7, "body": _BODY},
            {"number": 8, "body": _BODY.replace("news/1", "news/2")},
            {"number": 9, "body": _BODY.replace("news/1", "news/3")},
        ]
    )
    client = _FakeClient(
        {
            "https://ex.invalid/news/1": _Resp(200, "<p>An assault case in Warangal.</p>"),
            "https://ex.invalid/news/2": None,  # robots-disallowed
            "https://ex.invalid/news/3": _Resp(404, ""),  # gone
        }
    )
    source = SubmissionsSource(client, subs, fetched_at="2026-08-03")
    docs = _run(source.fetch())
    assert len(docs) == 1
    assert docs[0].publisher == "Community submission"
    assert "assault case in Warangal" in docs[0].text
    assert source.disallowed == {"https://ex.invalid/news/2"}
