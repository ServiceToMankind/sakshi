"""Tests for the supervised-launch config helpers (env-driven scope controls)."""

from __future__ import annotations

import pytest

from pipeline import config


def test_launch_mode_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAUNCH_MODE", raising=False)
    assert config.launch_mode() == "staged"
    monkeypatch.setenv("LAUNCH_MODE", "Auto")
    assert config.launch_mode() == "auto"


def test_launch_states(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAUNCH_STATES", raising=False)
    assert config.launch_states() is None
    monkeypatch.setenv("LAUNCH_STATES", "tg, dl ,")
    assert config.launch_states() == frozenset({"TG", "DL"})
    # ALL is an explicit "all states" (no filter), case-insensitive.
    monkeypatch.setenv("LAUNCH_STATES", "all")
    assert config.launch_states() is None


def test_scope_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAUNCH_STATES", raising=False)
    assert config.scope_is_configured() is False  # unset -> never silently unscoped
    monkeypatch.setenv("LAUNCH_STATES", "   ")
    assert config.scope_is_configured() is False  # blank -> still unresolved
    # Malformed comma/whitespace-only values resolve to no states -> must be refused,
    # not silently treated as all-states.
    monkeypatch.setenv("LAUNCH_STATES", ",")
    assert config.scope_is_configured() is False
    monkeypatch.setenv("LAUNCH_STATES", " , ,")
    assert config.scope_is_configured() is False
    monkeypatch.setenv("LAUNCH_STATES", "ALL")
    assert config.scope_is_configured() is True  # explicit all-states
    monkeypatch.setenv("LAUNCH_STATES", "TG,DL")
    assert config.scope_is_configured() is True


def test_launch_lookback_days(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAUNCH_LOOKBACK_DAYS", raising=False)
    assert config.launch_lookback_days() is None
    monkeypatch.setenv("LAUNCH_LOOKBACK_DAYS", "30")
    assert config.launch_lookback_days() == 30
    monkeypatch.setenv("LAUNCH_LOOKBACK_DAYS", "not-a-number")
    assert config.launch_lookback_days() is None


def test_estimate_cost() -> None:
    assert config.estimate_cost_usd(1_000_000, 0) == config.GEMINI_INPUT_USD_PER_MTOK


def test_gemini_models_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODELS", " gemini-x , gemini-y ,")
    assert config.gemini_models() == ["gemini-x", "gemini-y"]


def test_gemini_models_reads_sources_yml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_MODELS", raising=False)
    # sources.yml (repo root) pins the real chain; empty env falls through to it.
    models = config.gemini_models()
    assert models and all(m.startswith("gemini-") for m in models)
    assert "-latest" not in " ".join(models)  # pinned ids, never an alias


def test_gemini_models_default_when_no_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.delenv("GEMINI_MODELS", raising=False)
    monkeypatch.setattr(config, "SOURCES_CONFIG_PATH", config.REPO_ROOT / "no-such-file.yml")
    assert config.gemini_models() == list(config.DEFAULT_GEMINI_MODELS)
