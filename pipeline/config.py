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
DEFAULT_DAILY_TOKEN_CAP: Final[int] = 2_000_000

# --- Gemini model + cost estimation ------------------------------------------
# A resilient ALIAS to the current flash-class model. Concrete versions (2.0,
# 2.5) get retired without notice and then 404 mid-run; the alias always resolves
# to the current model, so the pipeline does not break on rotation.
GEMINI_MODEL: Final[str] = "gemini-flash-latest"
# Approximate USD per 1M tokens for GEMINI_MODEL; used only for the per-run cost
# estimate. Keep current with published pricing.
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


# --- Supervised-launch controls ----------------------------------------------
# LAUNCH_MODE is flipped by a human via a repo variable. "staged" (default) sends
# every run's data/ to a review PR; "auto" commits + deploys directly.
def launch_mode() -> str:
    return os.environ.get("LAUNCH_MODE", "staged").strip().lower() or "staged"


def launch_states() -> frozenset[str] | None:
    """Restrict a run to these 2-letter state codes, or None for all states."""
    raw = os.environ.get("LAUNCH_STATES", "").strip()
    states = frozenset(s.strip().upper() for s in raw.split(",") if s.strip())
    return states or None


def launch_lookback_days() -> int | None:
    """Only keep cases reported within this many days, or None for no window."""
    raw = os.environ.get("LAUNCH_LOOKBACK_DAYS", "").strip()
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a token spend at the configured gemini-2.0-flash rates."""
    return round(
        input_tokens / 1_000_000 * GEMINI_INPUT_USD_PER_MTOK
        + output_tokens / 1_000_000 * GEMINI_OUTPUT_USD_PER_MTOK,
        6,
    )
