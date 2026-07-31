"""Tests for the sources.yml-driven source registry (the per-source kill switch)."""

from __future__ import annotations

from typing import Any

from pipeline.sources import registry
from pipeline.sources.ecourts import EcourtsSource
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
