"""Tests for the processed-document ledger (skip-settled, retry-failed)."""

from __future__ import annotations

from pathlib import Path

from pipeline import config
from pipeline.ledger import Ledger, load_ledger, save_ledger


def test_new_url_should_process() -> None:
    assert Ledger().should_process("https://x/a")


def test_settled_outcomes_are_skipped() -> None:
    led = Ledger()
    for url, outcome in (
        ("https://x/a", "published"),
        ("https://x/b", "rejected"),
        ("https://x/c", "out_of_scope"),
        ("https://x/d", "not_a_case"),
    ):
        led.record(url, outcome, "2026-07-09")
        assert not led.should_process(url)


def test_failed_retries_then_parks_permanent() -> None:
    led = Ledger()
    for _ in range(config.EXTRACT_MAX_DOC_ATTEMPTS - 1):
        assert led.record("https://x/a", "failed", "2026-07-09") == "failed"
        assert led.should_process("https://x/a")  # still within the retry budget
    assert led.record("https://x/a", "failed", "2026-07-10") == "failed_permanent"
    assert not led.should_process("https://x/a")  # parked, skipped from now on


def test_stores_only_hashes_not_urls_or_pii() -> None:
    led = Ledger()
    led.record("https://secret.example/a-17-year-old-victim", "published", "2026-07-09")
    blob = str(led.to_dict())
    assert "secret.example" not in blob
    assert "17-year-old" not in blob and "victim" not in blob


def test_load_save_roundtrip(tmp_path: Path) -> None:
    led = Ledger()
    led.record("https://x/a", "published", "2026-07-09")
    save_ledger(tmp_path, led)
    assert (tmp_path / "_meta" / "processed.json").exists()
    assert not load_ledger(tmp_path).should_process("https://x/a")


def test_load_missing_and_malformed_are_empty(tmp_path: Path) -> None:
    assert load_ledger(tmp_path).should_process("https://x/a")  # missing file -> empty
    (tmp_path / "_meta").mkdir()
    (tmp_path / "_meta" / "processed.json").write_text("{bad json", encoding="utf-8")
    assert load_ledger(tmp_path).should_process("https://x/a")  # unparseable -> empty


def test_settled_count(tmp_path: Path) -> None:
    led = Ledger()
    led.record("https://x/a", "published", "2026-07-09")
    led.record("https://x/b", "failed", "2026-07-09")
    assert led.settled_count == 1  # published counts, failed does not
