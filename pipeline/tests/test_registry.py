"""Tests for the sources.yml-driven source registry (the per-source kill switch)."""

from __future__ import annotations

from typing import Any

from pipeline.sources import registry
from pipeline.sources.ecourts import EcourtsSource
from pipeline.sources.rss_media import RssMediaSource


class _FakeClient:
    async def get(self, url: str) -> Any:  # pragma: no cover - never called in these tests
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
    assert kinds == ["EcourtsSource", "RssMediaSource"]  # disabled + empty-url dropped
    assert isinstance(sources[0], EcourtsSource)
    assert isinstance(sources[1], RssMediaSource)


def test_load_source_configs_reads_repo_yaml() -> None:
    configs = registry.load_source_configs()
    ids = {c.get("id") for c in configs}
    assert "ecourts-njdg" in ids and "the-hindu" in ids


def test_load_source_configs_missing_file(tmp_path: Any) -> None:
    assert registry.load_source_configs(tmp_path / "nope.yml") == []
