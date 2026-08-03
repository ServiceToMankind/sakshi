"""Tests for the sources.yml-driven source registry (the per-source kill switch)."""

from __future__ import annotations

from typing import Any

from pipeline.sources import registry
from pipeline.sources.ecourts import EcourtsSource
from pipeline.sources.hc_judgments import HcJudgmentsSource
from pipeline.sources.indiankanoon import IndianKanoonSource
from pipeline.sources.rss_media import RssMediaSource


class _FakeClient:
    async def get(self, url: str) -> Any:  # pragma: no cover - never called in these tests
        return None

    async def post(self, url: str, **kwargs: Any) -> Any:  # pragma: no cover - never called
        return None


def test_build_sources_respects_enabled_and_types() -> None:
    configs = [
        {
            "id": "ecourts",
            "type": "ecourts",
            "enabled": True,
            "publisher": "eCourts",
            "endpoints": [],
        },
        {
            "id": "ik",
            "type": "indiankanoon",
            "enabled": True,
            "publisher": "Indian Kanoon",
            "queries": ["rape doctypes:delhi"],
        },
        {"id": "ik-empty", "type": "indiankanoon", "enabled": True, "queries": []},  # no queries
        {
            "id": "hindu",
            "type": "rss",
            "enabled": True,
            "publisher": "The Hindu",
            "url": "https://x/rss",
        },
        {"id": "off", "type": "rss", "enabled": False, "publisher": "Off", "url": "https://y/rss"},
        {"id": "nourl", "type": "rss", "enabled": True, "publisher": "NoURL", "url": ""},
    ]
    sources = registry.build_sources(_FakeClient(), fetched_at="2026-07-10", configs=configs)
    kinds = [type(s).__name__ for s in sources]
    # disabled, empty-url rss, and query-less indiankanoon are all dropped
    assert kinds == ["EcourtsSource", "IndianKanoonSource", "RssMediaSource"]
    assert isinstance(sources[0], EcourtsSource)
    assert isinstance(sources[1], IndianKanoonSource)
    assert isinstance(sources[2], RssMediaSource)

    # §2 refresh: court_only keeps only court-record sources, dropping the media feed.
    court = registry.build_sources(
        _FakeClient(), fetched_at="2026-07-10", configs=configs, court_only=True
    )
    assert [type(s).__name__ for s in court] == ["EcourtsSource", "IndianKanoonSource"]


def test_build_sources_wires_hc_judgments_as_a_court_source() -> None:
    configs = [
        {
            "id": "delhi-hc",
            "type": "hc_judgments",
            "enabled": True,
            "state": "DL",
            "courts": [
                {
                    "court": "Delhi High Court",
                    "listing_url": "https://delhihighcourt.nic.in/web/judgement",
                    "base_url": "https://delhihighcourt.nic.in",
                }
            ],
        },
        # court-less entry (and one with no listing_url) contribute no court -> dropped
        {"id": "empty-hc", "type": "hc_judgments", "enabled": True, "courts": []},
        {
            "id": "nolisting-hc",
            "type": "hc_judgments",
            "enabled": True,
            "courts": [{"court": "X HC", "listing_url": ""}],
        },
        {
            "id": "off-hc",
            "type": "hc_judgments",
            "enabled": False,
            "courts": [{"listing_url": "u"}],
        },
    ]
    sources = registry.build_sources(_FakeClient(), fetched_at="2026-08-03", configs=configs)
    assert [type(s).__name__ for s in sources] == ["HcJudgmentsSource"]
    assert isinstance(sources[0], HcJudgmentsSource)
    # §2 refresh re-queries court sources — hc_judgments is one (re-checkable judicial status).
    court = registry.build_sources(
        _FakeClient(), fetched_at="2026-08-03", configs=configs, court_only=True
    )
    assert [type(s).__name__ for s in court] == ["HcJudgmentsSource"]


def test_repo_yaml_hc_judgments_entries_are_all_disabled() -> None:
    # The standing rule: a source lands enabled:false, always. Enabling is the operator's.
    configs = registry.load_source_configs()
    hc = [c for c in configs if c.get("type") == "hc_judgments"]
    assert hc, "expected the §4a HC judgment sources to be present"
    assert all(c.get("enabled") is False for c in hc)
    ids = {c["id"] for c in hc}
    assert {"delhi-hc-judgments", "jk-hc-judgments", "meghalaya-hc-judgments"} <= ids


def test_load_source_configs_reads_repo_yaml() -> None:
    configs = registry.load_source_configs()
    by_id = {c.get("id"): c for c in configs}
    assert "ecourts-njdg" in by_id and "indian-kanoon" in by_id
    assert "the-hindu-delhi" in by_id
    # §3: every source is tagged with the state block it came from.
    assert by_id["indian-kanoon"]["state"] == "national"
    assert by_id["the-hindu-delhi"]["state"] == "DL"
    assert by_id["the-hindu-hyderabad"]["state"] == "TG"


def test_load_source_configs_by_state_and_legacy(tmp_path: Any) -> None:
    by_state = tmp_path / "s.yml"
    by_state.write_text(
        "national:\n  - {id: n1, type: rss}\nstates:\n  DL:\n    - {id: d1, type: rss}\n  MH: []\n",
        encoding="utf-8",
    )
    configs = registry.load_source_configs(by_state)
    tagged = {c["id"]: c["state"] for c in configs}
    assert tagged == {"n1": "national", "d1": "DL"}  # empty MH block contributes nothing

    legacy = tmp_path / "legacy.yml"
    legacy.write_text("sources:\n  - {id: x, type: rss}\n", encoding="utf-8")
    assert registry.load_source_configs(legacy) == [{"state": "national", "id": "x", "type": "rss"}]


def test_load_source_configs_missing_file(tmp_path: Any) -> None:
    assert registry.load_source_configs(tmp_path / "nope.yml") == []
