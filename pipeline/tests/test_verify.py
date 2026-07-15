"""Tests for the verification stage (guardrail L). Synthetic TESTVILLE data; the
verifier client is injected, so no network / key is touched."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pipeline.verify import (
    Verdict,
    VerificationResponse,
    apply_verdict,
    parse_verdict,
    verify_records,
)


def _record(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "SKS-2026-TG-000001",
        "title": "Sexual assault case — TESTVILLE (2026)",
        "state": "TG",
        "district": "TESTVILLE",
        "category": "sexual_assault",
        "status": "FIR_FILED",
        "minor_involved": False,
        "incident_reported_date": "2026-06-14",
        "accused": [
            {"label": "Accused #1", "name_public_court_record": None, "status": "FIR_FILED"}
        ],
        "sources": [
            {"url": "https://ex.invalid/a", "publisher": "The Hindu", "retrieved": "2026-07-09"}
        ],
        "confidence": 0.9,
        "last_verified": "2026-07-09",
    }
    base.update(overrides)
    return base


class _Client:
    def __init__(self, payload: str, tokens: tuple[int, int] = (100, 20)) -> None:
        self._payload = payload
        self._tokens = tokens

    def verify(self, prompt: str) -> VerificationResponse:
        return VerificationResponse(self._payload, self._tokens[0], self._tokens[1])


# --- parse_verdict ---


def test_parse_verdict_valid_and_code_fenced() -> None:
    v = parse_verdict(
        '{"verified": true, "verification_note": "corroborated", '
        '"corrections": {"status": "UNDER_TRIAL"}}'
    )
    assert v and v.verified is True and v.corrections == {"status": "UNDER_TRIAL"}
    fenced = parse_verdict('```json\n{"verified": false}\n```')
    assert fenced and fenced.verified is False


def test_parse_verdict_unparseable_returns_none() -> None:
    assert parse_verdict("not json") is None
    assert parse_verdict("[1,2,3]") is None  # not an object


# --- apply_verdict: corrections restricted to CORRECTABLE_FIELDS ---


def test_apply_verdict_applies_only_correctable_fields() -> None:
    rec = _record()
    verdict = Verdict(
        verified=True,
        corrections={
            "status": "UNDER_TRIAL",  # correctable
            "district": "Central TESTVILLE",  # correctable
            "minor_involved": True,  # NOT correctable -> ignored
            "id": "HACKED",  # NOT correctable -> ignored
            "accused": [{"name_public_court_record": "Someone"}],  # NOT correctable -> ignored
        },
        note="looks good",
    )
    out = apply_verdict(rec, verdict)
    assert out["status"] == "UNDER_TRIAL" and out["district"] == "Central TESTVILLE"
    assert out["minor_involved"] is False  # guardrail field untouched
    assert out["id"] == "SKS-2026-TG-000001"  # id untouched
    assert out["accused"] == rec["accused"]  # accused untouched
    assert out["verified"] is True and out["verification_note"] == "looks good"


def test_apply_verdict_unions_second_source_only_when_verified() -> None:
    rec = _record()
    v = Verdict(
        True, {}, "corroborated", second_source={"url": "https://ex.invalid/b", "publisher": "IE"}
    )
    out = apply_verdict(rec, v)
    assert [s["url"] for s in out["sources"]] == ["https://ex.invalid/a", "https://ex.invalid/b"]
    # A demoted verdict never adds a corroborating source.
    v2 = Verdict(
        False, {}, "unsupported", second_source={"url": "https://ex.invalid/c", "publisher": "X"}
    )
    out2 = apply_verdict(rec, v2)
    assert [s["url"] for s in out2["sources"]] == ["https://ex.invalid/a"]


def test_apply_verdict_second_source_has_valid_retrieved_date() -> None:
    """A FRESH record has no `last_verified` yet — the corroborating source must borrow
    the primary source's `retrieved` (a schema-valid date), NOT publish an empty one that
    fails the sources[].retrieved pattern and quarantines the verified record."""
    rec = _record()
    del rec["last_verified"]  # fresh extraction: assigned only later in write_shards
    v = Verdict(True, {}, "ok", second_source={"url": "https://ex.invalid/b", "publisher": "IE"})
    out = apply_verdict(rec, v)
    appended = out["sources"][-1]
    assert appended["url"] == "https://ex.invalid/b"
    # Borrowed from the primary source's retrieved date — a valid YYYY-MM-DD, not "".
    assert appended["retrieved"] == "2026-07-09"


def test_parse_verdict_verified_must_be_boolean_true() -> None:
    """`verified` is fail-closed: only a real boolean `true` verifies. A model that emits
    the STRING "false" (or any truthy non-bool) must NOT publish."""
    assert parse_verdict('{"verified": "false"}').verified is False  # type: ignore[union-attr]
    assert parse_verdict('{"verified": 1}').verified is False  # type: ignore[union-attr]
    assert parse_verdict('{"verified": "true"}').verified is False  # type: ignore[union-attr]
    assert parse_verdict('{"verified": true}').verified is True  # type: ignore[union-attr]


def test_parse_verdict_rejects_non_http_second_source() -> None:
    """A model-supplied corroborating source URL is published as a link — reject
    javascript:/data:/file: schemes before they can enter the data."""
    bad = parse_verdict('{"verified": true, "second_source": {"url": "javascript:alert(1)"}}')
    assert bad and bad.second_source is None
    data = parse_verdict('{"verified": true, "second_source": {"url": "data:text/html,x"}}')
    assert data and data.second_source is None
    ok = parse_verdict('{"verified": true, "second_source": {"url": "https://ex.invalid/b"}}')
    assert ok and ok.second_source == {"url": "https://ex.invalid/b"}


# --- verify_records ---


def test_verify_records_verified_and_demoted() -> None:
    recs = [_record(cnr="C-1"), _record(cnr="C-2")]
    texts = {"https://ex.invalid/a": "A reported sexual assault case; FIR filed in TESTVILLE."}
    client = _Client('{"verified": true, "verification_note": "ok"}')
    result = verify_records(recs, texts, client)
    assert result.verified_count == 2 and result.demoted_count == 0
    assert all(r["verified"] is True for r in result.records)


def test_verify_records_no_source_text_stays_unverified() -> None:
    recs = [_record()]
    result = verify_records(recs, {}, _Client('{"verified": true}'))  # no matching source text
    assert result.records[0]["verified"] is False and result.verified_count == 0
    # Accounted so verified + demoted + skipped_budget + skipped_no_source == len.
    assert result.skipped_no_source == 1 and result.demoted_count == 0
    assert (
        result.verified_count
        + result.demoted_count
        + result.skipped_budget
        + result.skipped_no_source
        == len(recs)
    )


def test_verify_records_provider_error_demotes() -> None:
    class _Boom:
        def verify(self, prompt: str) -> VerificationResponse:
            raise RuntimeError("503 overloaded")

    result = verify_records([_record()], {"https://ex.invalid/a": "text"}, _Boom())
    assert result.records[0]["verified"] is False and result.demoted_count == 1
    assert result.error_samples


def test_verify_records_budget_cap_quarantines_remainder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERIFY_MAX_USD", "0.0000001")  # cap after the first call
    recs = [_record(cnr=f"C-{i}") for i in range(3)]
    texts = {"https://ex.invalid/a": "A reported sexual assault case."}
    # Each call reports enough tokens to exceed the tiny cap immediately.
    result = verify_records(recs, texts, _Client('{"verified": true}', tokens=(1000, 1000)))
    assert result.verified_count == 1  # only the first was verified within budget
    assert result.skipped_budget == 2 and all(not r["verified"] for r in result.records[1:])


def test_verify_records_writes_cost_log(tmp_path: Path) -> None:
    result = verify_records(
        [_record()],
        {"https://ex.invalid/a": "text"},
        _Client('{"verified": true, "verification_note": "ok"}'),
        cost_log_path=tmp_path / "verify_cost.json",
    )
    cost = json.loads((tmp_path / "verify_cost.json").read_text())
    assert cost["verified"] == 1 and cost["estimated_usd"] == result.estimated_usd
