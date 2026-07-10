"""Tests for the Gemini extractor (offline, via a fake client)."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline import config
from pipeline.extract import gemini
from pipeline.extract.gemini import ExtractionResponse
from pipeline.sources.base import RawDocument

_DOC = RawDocument(
    url="https://example.invalid/testville/1",
    publisher="eCourts",
    fetched_at="2026-07-09",
    text="A TESTVILLE case under trial.",
)

_VALID_JSON = json.dumps(
    {"category": "pocso", "state": "TG", "district": "TESTVILLE", "status": "UNDER_TRIAL"}
)


class _FakeClient:
    def __init__(self, responses: list[ExtractionResponse | Exception]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def generate(self, prompt: str) -> ExtractionResponse:
        self.calls += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _resp(text: str, tin: int = 100, tout: int = 50) -> ExtractionResponse:
    return ExtractionResponse(text=text, input_tokens=tin, output_tokens=tout)


def test_build_prompt_embeds_schema_and_text() -> None:
    prompt = gemini.build_prompt(_DOC, "THE-SCHEMA")
    assert "THE-SCHEMA" in prompt
    assert "TESTVILLE case under trial" in prompt


def test_parse_forces_victim_null_and_attaches_source() -> None:
    record = gemini._parse(_VALID_JSON, _DOC)
    assert record is not None
    assert record["victim"] is None
    assert record["sources"] == [
        {"url": _DOC.url, "publisher": _DOC.publisher, "retrieved": _DOC.fetched_at}
    ]
    assert record["confidence"] == 0.0  # defaulted when absent


def test_parse_rejects_malformed_and_incomplete() -> None:
    assert gemini._parse("{bad", _DOC) is None
    assert gemini._parse('"a string"', _DOC) is None
    assert gemini._parse('{"category": null}', _DOC) is None  # not a case
    assert gemini._parse('{"category":"pocso","state":"TG"}', _DOC) is None  # missing status


def test_extract_accumulates_tokens_and_writes_cost_log(tmp_path: Path) -> None:
    client = _FakeClient([_resp(_VALID_JSON), _resp(_VALID_JSON)])
    cost_log = tmp_path / "cost.json"
    result = gemini.extract(
        [_DOC, _DOC], client=client, cost_log_path=cost_log, sleep=lambda _s: None
    )
    assert len(result.records) == 2
    assert result.input_tokens == 200 and result.output_tokens == 100
    assert result.estimated_usd > 0
    logged = json.loads(cost_log.read_text())
    assert logged["documents"] == 2 and logged["models"] == config.gemini_models()


def test_extract_stops_at_token_cap() -> None:
    client = _FakeClient([_resp(_VALID_JSON), _resp(_VALID_JSON)])
    result = gemini.extract([_DOC, _DOC], client=client, token_cap=100, sleep=lambda _s: None)
    assert result.truncated is True
    assert len(result.records) == 1  # second doc never issued


def test_extract_retries_on_error_then_succeeds() -> None:
    client = _FakeClient([RuntimeError("boom"), _resp(_VALID_JSON)])
    slept: list[float] = []
    result = gemini.extract([_DOC], client=client, sleep=slept.append, jitter=lambda: 0.0)
    assert len(result.records) == 1
    assert slept  # a backoff sleep happened
    assert client.calls == 2


def test_extract_empty_docs_returns_empty() -> None:
    result = gemini.extract([], client=_FakeClient([]))
    assert result.records == [] and result.documents == 0


def test_failing_doc_is_skipped_not_fatal(tmp_path: Path) -> None:
    client = _FakeClient([RuntimeError("boom")] * 20)  # every call fails
    cost_log = tmp_path / "cost.json"
    result = gemini.extract(
        [_DOC, _DOC],
        client=client,
        cost_log_path=cost_log,
        sleep=lambda _s: None,
        jitter=lambda: 0.0,
    )
    assert result.records == [] and result.failed == 2 and result.aborted is False
    assert cost_log.exists()  # spend/attempts recorded even though both docs failed


def test_circuit_breaker_aborts_on_sustained_failures() -> None:
    client = _FakeClient([RuntimeError("boom")] * 50)
    result = gemini.extract([_DOC] * 10, client=client, sleep=lambda _s: None, jitter=lambda: 0.0)
    assert result.aborted is True
    assert result.failovers == 0  # single-model chain, nowhere to fail over
    assert result.failed == config.EXTRACT_MAX_CONSECUTIVE_FAILURES  # stopped early


def test_failover_to_next_model_when_primary_circuit_breaks() -> None:
    n = config.EXTRACT_MAX_CONSECUTIVE_FAILURES
    primary = _FakeClient([RuntimeError("503 overload")] * 50)  # always fails
    fallback = _FakeClient([_resp(_VALID_JSON)] * 50)  # healthy
    result = gemini.extract(
        [_DOC] * 10, clients=[primary, fallback], sleep=lambda _s: None, jitter=lambda: 0.0
    )
    assert result.aborted is False  # fallback rescued the run
    assert result.failovers == 1
    assert result.failed == n  # the primary's circuit-break window
    assert len(result.records) == 10 - n  # remaining docs extracted on the fallback


def test_all_models_exhausted_stays_aborted() -> None:
    n = config.EXTRACT_MAX_CONSECUTIVE_FAILURES
    a = _FakeClient([RuntimeError("boom")] * 50)
    b = _FakeClient([RuntimeError("boom")] * 50)
    result = gemini.extract([_DOC] * 20, clients=[a, b], sleep=lambda _s: None, jitter=lambda: 0.0)
    assert result.aborted is True  # both models broke
    assert result.failovers == 1
    assert result.failed == 2 * n  # one circuit-break window per model
    assert result.records == []
