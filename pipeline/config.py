"""Central pipeline configuration, paths, and cost constants.

Values that a run may legitimately override come from the environment; the rest
are fixed policy (per Phase 0.3 politeness rules). Keep this module import-safe
and side-effect-free so every stage and test can read it cheaply.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DATA_DIR: Final[Path] = REPO_ROOT / "data"
REVIEW_DIR: Final[Path] = DATA_DIR / "_review"
LOGS_DIR: Final[Path] = REPO_ROOT / "logs"
SCHEMA_DIR: Final[Path] = REPO_ROOT / "schemas"
SOURCES_CONFIG_PATH: Final[Path] = REPO_ROOT / "sources.yml"

# --- Scraping politeness (Phase 0.3 — non-negotiable) ------------------------
DEFAULT_USER_AGENT: Final[str] = "sakshi-bot/1.0 (+https://github.com/ServiceToMankind/sakshi)"
MIN_REQUEST_INTERVAL_S: Final[float] = 2.0  # at most 1 request / 2s per host
MAX_RETRIES: Final[int] = 5
BACKOFF_BASE_S: Final[float] = 1.0
BACKOFF_MAX_S: Final[float] = 60.0
REQUEST_TIMEOUT_S: Final[float] = 30.0

# --- Sharding ----------------------------------------------------------------
SUMMARY_MAX_BYTES: Final[int] = 50 * 1024  # summary.json must load fast on the landing page
SHARD_SPLIT_BYTES: Final[int] = 500 * 1024  # a shard over this splits into {STATE}-pN.json
MONTHLY_TREND_MONTHS: Final[int] = 24
TOP_PENDING_COUNT: Final[int] = 10

# --- Extraction / review -----------------------------------------------------
# Records below this confidence are quarantined to data/_review/ (never published).
CONFIDENCE_REVIEW_THRESHOLD: Final[float] = 0.8
REVIEW_QUEUE_ISSUE_THRESHOLD: Final[int] = 20
# Graduated auto-publish gate: a record at/above the review threshold still only
# AUTO-publishes (no human first) when it also clears this higher bar AND is a
# non-minor, unnamed-accused, durably-sourced case. The 0.80..0.84 band, minors,
# named accused, and live-blog-only records are held in the needs-review queue.
AUTO_PUBLISH_CONFIDENCE: Final[float] = 0.85
# A record whose ONLY provenance is a rolling live-blog is capped just below the
# publish threshold so it auto-quarantines for human confirmation (issue #7): a
# mutable, URL-decaying live-updates page is not enough to make a permanent claim.
LIVE_BLOG_CONFIDENCE_CAP: Final[float] = 0.79
# Indian Kanoon bills PER DOCUMENT, so a per-run fetch budget is the cost control
# (the shared PoliteClient additionally honours 2s/host + 429 Retry-After). Keep
# conservative; raise only with an eye on the bill.
IK_MAX_DOCS_PER_RUN: Final[int] = 100
DEFAULT_DAILY_TOKEN_CAP: Final[int] = 2_000_000
# Per-document Gemini retries (fail fast, then skip the doc) and a circuit breaker
# so sustained provider errors (503 overload) abort extraction instead of hanging.
EXTRACT_MAX_RETRIES: Final[int] = 2
EXTRACT_MAX_CONSECUTIVE_FAILURES: Final[int] = 5
# Per Gemini call: a tight timeout AND a matching SDK retry deadline, so one flaky
# document cannot stack a 30s SDK retry on top of our retries into ~90s of dead
# wall time. Separate from REQUEST_TIMEOUT_S (which bounds source fetches).
EXTRACT_CALL_TIMEOUT_S: Final[float] = 20.0
# Hard wall-clock ceiling on a single extraction pass. Once exceeded, no new call
# is issued and the run stages whatever it already has (truncated). This
# GUARANTEES the job finishes inside its runner timeout even when the provider is
# intermittently slow and per-call retries stack up — the failure mode that,
# unbounded, silently burned the whole 60-min scrape job. Sized to leave headroom
# under that job for fetch + staging + commit.
EXTRACT_WALLCLOCK_BUDGET_S: Final[float] = 2400.0  # 40 minutes
# How many runs a document whose extraction call keeps FAILING is retried before
# it is parked as failed_permanent in the processed-document ledger (its URL is
# then logged once for manual review). Bounds wasted retries on a dead URL.
EXTRACT_MAX_DOC_ATTEMPTS: Final[int] = 3

# --- Gemini model chain + cost estimation ------------------------------------
# PINNED model ids, NOT a `-latest` alias. An alias silently repoints to whatever
# Google promotes and, for a daily unattended job, turns an external model swap
# into a surprise mid-run failure. Pinned ids make a model change a reviewed
# config commit. The list is an ORDERED FALLBACK CHAIN: on sustained provider
# failure (circuit-break) of model N, extraction fails over to model N+1 before
# aborting the run. Every model gets the same schema-constrained prompt and the
# same downstream sanitize gate — the guardrails are model-agnostic by design.
DEFAULT_GEMINI_MODELS: Final[tuple[str, ...]] = ("gemini-2.5-flash", "gemini-2.5-flash-lite")
# Approximate USD per 1M tokens at flash-class rates; used only for the per-run
# cost ESTIMATE (the chain's primary model). Keep current with published pricing.
GEMINI_INPUT_USD_PER_MTOK: Final[float] = 0.30
GEMINI_OUTPUT_USD_PER_MTOK: Final[float] = 2.50


def user_agent() -> str:
    """The honest User-Agent sent with every outbound request."""
    return os.environ.get("USER_AGENT", DEFAULT_USER_AGENT)


def gemini_api_key() -> str | None:
    """The Gemini API key from the environment, or None if unset (e.g. dry-run)."""
    return os.environ.get("GEMINI_API_KEY")


def daily_token_cap() -> int:
    """Per-run-day Gemini token budget; new extraction calls stop once reached."""
    raw = os.environ.get("GEMINI_DAILY_TOKEN_CAP")
    return int(raw) if raw else DEFAULT_DAILY_TOKEN_CAP


def _models_from_sources_yml() -> list[str]:
    """Read the ordered model chain from sources.yml `extraction.models`, if present."""
    try:
        import yaml  # lazy: keep this module import-safe and dependency-light

        data = yaml.safe_load(SOURCES_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    models = (data.get("extraction") or {}).get("models") or []
    return [str(m).strip() for m in models if isinstance(m, str) and m.strip()]


def gemini_models() -> list[str]:
    """The ordered Gemini fallback chain (pinned ids), primary first.

    Resolution order (first non-empty wins): the ``GEMINI_MODELS`` env/repo
    variable (comma-separated), then ``sources.yml`` ``extraction.models``, then
    :data:`DEFAULT_GEMINI_MODELS`. Config-driven so a model swap never needs a
    code change.
    """
    raw = os.environ.get("GEMINI_MODELS", "").strip()
    if raw:
        env_models = [m.strip() for m in raw.split(",") if m.strip()]
        if env_models:
            return env_models
    return _models_from_sources_yml() or list(DEFAULT_GEMINI_MODELS)


# --- Verification stage (guardrail L) -----------------------------------------
# A STRONGER model with web-search grounding re-checks each in-scope candidate
# BEFORE publish: confirms the source supports every field, re-checks scope, and
# corroborates. It can only demote/correct/approve — it NEVER overrides the
# deterministic gates (sanitize, minor projection, pii_guard, schema).
DEFAULT_VERIFY_MODEL: Final[str] = "gemini-2.5-pro"
# gemini-2.5-pro rates (approx USD per 1M tokens) — verifier cost estimate only.
VERIFY_INPUT_USD_PER_MTOK: Final[float] = 1.25
VERIFY_OUTPUT_USD_PER_MTOK: Final[float] = 10.0
# Per-run USD cap: the verifier runs only on in-scope candidates (a handful/day);
# once spend reaches this, remaining candidates are quarantined "unverified" rather
# than published, so a runaway can never blow the bill.
DEFAULT_VERIFY_MAX_USD: Final[float] = 0.50
# Max chars of source text passed to the verifier (keeps the prompt + cost bounded).
VERIFY_SOURCE_TEXT_CHARS: Final[int] = 12000
# Per-verification call timeout (pro + grounding is slower than flash extraction).
VERIFY_CALL_TIMEOUT_S: Final[float] = 120.0
# Hard per-call output ceiling: the verdict JSON is tiny, so this bounds a single
# call's cost (the running USD cap is only checked BETWEEN calls, not within one).
VERIFY_MAX_OUTPUT_TOKENS: Final[int] = 1024


def verification_enabled() -> bool:
    """True if the verification stage runs (opt-in; the auto-flip turns it on)."""
    return os.environ.get("VERIFY_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def verification_model() -> str:
    """The pinned verifier model id (env VERIFY_MODEL > sources.yml > default)."""
    raw = os.environ.get("VERIFY_MODEL", "").strip()
    if raw:
        return raw
    try:
        import yaml

        data = yaml.safe_load(SOURCES_CONFIG_PATH.read_text(encoding="utf-8"))
        model = (data.get("verification") or {}).get("model") if isinstance(data, dict) else None
        if isinstance(model, str) and model.strip():
            return model.strip()
    except (OSError, ValueError):
        pass
    return DEFAULT_VERIFY_MODEL


def verify_max_usd() -> float:
    """Per-run USD budget cap for the verifier (env VERIFY_MAX_USD > default)."""
    raw = os.environ.get("VERIFY_MAX_USD", "").strip()
    try:
        return float(raw) if raw else DEFAULT_VERIFY_MAX_USD
    except ValueError:
        return DEFAULT_VERIFY_MAX_USD


def estimate_verify_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Estimate USD for a verifier token spend at gemini-2.5-pro rates."""
    return round(
        input_tokens / 1_000_000 * VERIFY_INPUT_USD_PER_MTOK
        + output_tokens / 1_000_000 * VERIFY_OUTPUT_USD_PER_MTOK,
        6,
    )


# --- Supervised-launch controls ----------------------------------------------
# LAUNCH_MODE is flipped by a human via a repo variable. "staged" (default) sends
# every run's data/ to a review PR; "auto" commits + deploys directly.
def launch_mode() -> str:
    return os.environ.get("LAUNCH_MODE", "staged").strip().lower() or "staged"


def publish_approved_only() -> bool:
    """Supervised-phase control: publish ONLY human-approved records.

    When true, an auto-publish-eligible record that is NOT on the approval allowlist is
    HELD for review instead of published, so nothing reaches the public site during the
    supervised launch without an explicit operator approval. Default false (the
    graduated gate's normal auto-publish of the safe class).
    """
    return os.environ.get("PUBLISH_APPROVED_ONLY", "").strip().lower() in {"1", "true", "yes"}


def launch_states() -> frozenset[str] | None:
    """Restrict a run to these 2-letter state codes, or None for all states.

    The literal ``ALL`` is an EXPLICIT "all states" (no filter) — distinct from an
    unset variable, which :func:`scope_is_configured` refuses so a run can never be
    silently unscoped (the cron-without-inputs failure that once ran unscoped).
    """
    raw = os.environ.get("LAUNCH_STATES", "").strip()
    if raw.upper() == "ALL":
        return None
    states = frozenset(s.strip().upper() for s in raw.split(",") if s.strip())
    return states or None


def scope_is_configured() -> bool:
    """True iff the launch scope RESOLVES to an explicit selection — never silently
    unscoped.

    LAUNCH_STATES must be ``ALL`` (all states, intentional) or resolve to a non-empty
    state set. A bare truthiness check is NOT enough: a malformed value like ``","`` or
    ``"  "`` is truthy but ``launch_states()`` parses it to the empty set -> ``None``
    (all states), which would silently run all-states-all-time. Aligning with the real
    resolution makes such a value trigger the hard scope gate's refusal instead.
    """
    raw = os.environ.get("LAUNCH_STATES", "").strip()
    return raw.upper() == "ALL" or launch_states() is not None


def launch_lookback_days() -> int | None:
    """Only keep cases reported within this many days, or None for no window."""
    raw = os.environ.get("LAUNCH_LOOKBACK_DAYS", "").strip()
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a token spend at the configured flash-class rates."""
    return round(
        input_tokens / 1_000_000 * GEMINI_INPUT_USD_PER_MTOK
        + output_tokens / 1_000_000 * GEMINI_OUTPUT_USD_PER_MTOK,
        6,
    )
