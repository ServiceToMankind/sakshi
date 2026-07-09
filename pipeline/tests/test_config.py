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


def test_launch_lookback_days(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAUNCH_LOOKBACK_DAYS", raising=False)
    assert config.launch_lookback_days() is None
    monkeypatch.setenv("LAUNCH_LOOKBACK_DAYS", "30")
    assert config.launch_lookback_days() == 30
    monkeypatch.setenv("LAUNCH_LOOKBACK_DAYS", "not-a-number")
    assert config.launch_lookback_days() is None


def test_estimate_cost() -> None:
    assert config.estimate_cost_usd(1_000_000, 0) == config.GEMINI_INPUT_USD_PER_MTOK
