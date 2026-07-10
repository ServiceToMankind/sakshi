"""Gemini-based extraction.

Converts already-public source text into structured, pre-sanitize case
candidates. Gemini SUMMARIZES and CLASSIFIES public text; it never invents facts.

Phase 0 obligations enforced here:
- Output is constrained to ``schemas/extraction.schema.json`` (a schema with no
  victim/name/address fields), and the prompt forces ``"victim": null``.
- ``sources[]`` is attached programmatically from the source document, never
  trusted from the model.
- Every candidate still passes through ``pipeline.sanitize`` downstream (this
  module never writes to disk).
- Each candidate carries ``confidence``; < 0.8 is quarantined by the dedupe stage.

Operational: one request per document (so each candidate's source is attributed
exactly), jittered exponential backoff, a per-run token cap, and a cost estimate.
The concrete Gemini client is injectable so the whole flow is unit-tested with a
fake and no network.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pipeline import config
from pipeline.sources.base import RawDocument

__all__ = ["ExtractionClient", "ExtractionResponse", "ExtractionResult", "build_prompt", "extract"]

_SCHEMA_PATH = config.SCHEMA_DIR / "extraction.schema.json"

_PROMPT_TEMPLATE = """You extract structured facts from a single piece of ALREADY-PUBLIC \
Indian court-record or news text about a reported sexual-offence case.

Hard rules:
- Do NOT invent, infer, or embellish. Only report what the text states.
- "victim" MUST be null. Never output any victim, survivor, complainant, address,
  family, school, workplace, photo, phone, email, or age (beyond minor true/false).
- If the text is not about a specific reported case, output {{"category": null}}.
- Output ONLY a single JSON object matching this schema (no prose, no code fences):

{schema}

Text to extract from:
\"\"\"
{text}
\"\"\"
"""


@dataclass(frozen=True)
class ExtractionResponse:
    """A raw model response: JSON text plus token usage."""

    text: str
    input_tokens: int
    output_tokens: int


@dataclass
class ExtractionResult:
    """The outcome of an extraction run: candidates plus token/cost accounting."""

    records: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    documents: int = 0
    truncated: bool = False
    truncated_reason: str | None = None  # "token_cap" | "time_budget" when truncated
    failed: int = 0
    aborted: bool = False
    failovers: int = 0

    @property
    def estimated_usd(self) -> float:
        return config.estimate_cost_usd(self.input_tokens, self.output_tokens)


class ExtractionClient(Protocol):
    """A minimal Gemini-like client: turn a prompt into an :class:`ExtractionResponse`."""

    def generate(self, prompt: str) -> ExtractionResponse: ...


def _load_schema_text() -> str:
    return _SCHEMA_PATH.read_text(encoding="utf-8")


def build_prompt(doc: RawDocument, schema_text: str) -> str:
    """Build the schema-constrained extraction prompt for one document."""
    return _PROMPT_TEMPLATE.format(schema=schema_text, text=doc.text)


def _parse(text: str, doc: RawDocument) -> dict[str, Any] | None:
    """Parse a model response into a candidate, forcing victim=null and real sources."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or not obj.get("category"):
        return None
    if not (obj.get("state") and obj.get("district") and obj.get("status")):
        return None
    obj["victim"] = None  # forced; the sanitizer drops the key before disk
    obj["sources"] = [{"url": doc.url, "publisher": doc.publisher, "retrieved": doc.fetched_at}]
    obj.setdefault("confidence", 0.0)
    return obj


def _call_with_backoff(
    client: ExtractionClient,
    prompt: str,
    *,
    sleep: Callable[[float], None],
    jitter: Callable[[], float],
    max_retries: int,
) -> ExtractionResponse:
    attempt = 0
    while True:
        try:
            return client.generate(prompt)
        except Exception:
            attempt += 1
            if attempt > max_retries:
                raise
            backoff = min(config.BACKOFF_BASE_S * (2 ** (attempt - 1)), config.BACKOFF_MAX_S)
            sleep(backoff + jitter())


def _resolve_clients(
    client: ExtractionClient | None, clients: list[ExtractionClient] | None
) -> list[ExtractionClient]:
    """The ordered client chain: explicit list, single injected client, or the real chain."""
    if clients is not None:
        return list(clients)
    if client is not None:
        return [client]
    return [_default_client(model) for model in config.gemini_models()]


def _run_model(
    active: ExtractionClient,
    docs: list[RawDocument],
    result: ExtractionResult,
    *,
    cap: int,
    deadline: float,
    clock: Callable[[], float],
    schema_text: str,
    sleep: Callable[[float], None],
    jitter: Callable[[], float],
) -> list[RawDocument]:
    """Run one model over ``docs``, mutating ``result``.

    Returns the documents still unprocessed. That is ``[]`` when the queue drains
    (or a hard limit — token cap or wall-clock budget — is hit); when the provider
    circuit-breaks, it is the slice AFTER the break so the caller can fail over to
    the next model.
    """
    consecutive_failures = 0
    for i, doc in enumerate(docs):
        if result.input_tokens + result.output_tokens >= cap:
            result.truncated = True
            result.truncated_reason = "token_cap"
            return []
        if clock() >= deadline:
            # Out of wall-clock budget: stop issuing calls on every model and
            # stage what we have. A time-out is global, not a per-model failure.
            result.truncated = True
            result.truncated_reason = "time_budget"
            return []
        try:
            response = _call_with_backoff(
                active,
                build_prompt(doc, schema_text),
                sleep=sleep,
                jitter=jitter,
                max_retries=config.EXTRACT_MAX_RETRIES,
            )
        except Exception:
            # One document's persistent failure never aborts the whole run; skip
            # it. But circuit-break if the provider is sustainedly failing.
            result.failed += 1
            consecutive_failures += 1
            if consecutive_failures >= config.EXTRACT_MAX_CONSECUTIVE_FAILURES:
                result.aborted = True
                return docs[i + 1 :]
            continue
        consecutive_failures = 0
        result.input_tokens += response.input_tokens
        result.output_tokens += response.output_tokens
        record = _parse(response.text, doc)
        if record is not None:
            result.records.append(record)
    return []


def extract(
    docs: list[RawDocument],
    *,
    client: ExtractionClient | None = None,
    clients: list[ExtractionClient] | None = None,
    token_cap: int | None = None,
    budget_s: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] | None = None,
    clock: Callable[[], float] = time.monotonic,
    cost_log_path: Path | None = None,
) -> ExtractionResult:
    """Extract pre-sanitize candidates from already-public documents.

    Bounded three ways so an unattended run always finishes inside its job window:
    a token cap, a hard wall-clock budget (:data:`config.EXTRACT_WALLCLOCK_BUDGET_S`),
    and an ordered model fallback chain (:func:`pipeline.config.gemini_models`) —
    if one model circuit-breaks under sustained provider failure, extraction fails
    over to the next for the remaining documents before giving up. Returns an
    :class:`ExtractionResult`; callers MUST still run each record through
    :func:`pipeline.sanitize.sanitize_record` before anything touches disk.
    """
    result = ExtractionResult(documents=len(docs))
    if not docs:
        return result

    chain = _resolve_clients(client, clients)
    cap = token_cap if token_cap is not None else config.daily_token_cap()
    budget = budget_s if budget_s is not None else config.EXTRACT_WALLCLOCK_BUDGET_S
    deadline = clock() + budget
    jitter_fn = jitter if jitter is not None else (lambda: random.uniform(0.0, 0.5))
    schema_text = _load_schema_text()

    remaining = list(docs)
    try:
        for idx, active in enumerate(chain):
            remaining = _run_model(
                active,
                remaining,
                result,
                cap=cap,
                deadline=deadline,
                clock=clock,
                schema_text=schema_text,
                sleep=sleep,
                jitter=jitter_fn,
            )
            if not result.aborted:
                break  # queue drained or token cap hit — done
            if idx + 1 < len(chain):
                # This model circuit-broke; fail over to the next one for the
                # still-unprocessed documents before aborting the whole run.
                result.aborted = False
                result.failovers += 1
                continue
            break  # last model in the chain also broke — stay aborted
    finally:
        # Record spend even if a call raises mid-run — money already spent is logged.
        if cost_log_path is not None:
            _write_cost_log(result, cost_log_path)
    return result


def _write_cost_log(result: ExtractionResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "models": config.gemini_models(),
        "documents": result.documents,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "estimated_usd": result.estimated_usd,
        "records": len(result.records),
        "failed": result.failed,
        "failovers": result.failovers,
        "truncated": result.truncated,
        "truncated_reason": result.truncated_reason,
        "aborted": result.aborted,
    }
    path.write_text(json.dumps(entry, indent=2), encoding="utf-8")


def _default_client(model_id: str) -> ExtractionClient:  # pragma: no cover - live SDK + key
    """Build the real Gemini client for one pinned model (lazy import; tests skip it)."""
    import importlib

    # Imported dynamically as Any: the SDK is untyped and only present at runtime.
    genai: Any = importlib.import_module("google.generativeai")
    g_retry: Any = importlib.import_module("google.api_core.retry")

    api_key = config.gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set; cannot run live extraction.")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_id,
        generation_config={"response_mime_type": "application/json"},
    )

    class _GeminiClient:
        def generate(self, prompt: str) -> ExtractionResponse:
            # Bound BOTH the per-call timeout AND the SDK's internal retry deadline,
            # so a 503-overloaded model fails in seconds rather than blocking 600s.
            response = model.generate_content(
                prompt,
                request_options={
                    "timeout": config.EXTRACT_CALL_TIMEOUT_S,
                    "retry": g_retry.Retry(deadline=config.EXTRACT_CALL_TIMEOUT_S),
                },
            )
            usage = getattr(response, "usage_metadata", None)
            return ExtractionResponse(
                text=response.text,
                input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            )

    return _GeminiClient()
