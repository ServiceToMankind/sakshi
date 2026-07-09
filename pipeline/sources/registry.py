"""Build the enabled source list from ``sources.yml`` — the per-source kill switch.

A misbehaving source is disabled by setting ``enabled: false`` in ``sources.yml``
(a config commit, no code change). This module never fabricates: an eCourts entry
with no endpoints simply yields nothing, and an rss entry with no URL is skipped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pipeline import config
from pipeline.sources.base import Source
from pipeline.sources.ecourts import EcourtsSource
from pipeline.sources.http import HttpGetter
from pipeline.sources.rss_media import Feed, RssMediaSource

__all__ = ["build_sources", "load_source_configs"]


def load_source_configs(path: Path = config.SOURCES_CONFIG_PATH) -> list[dict[str, Any]]:
    """Parse ``sources.yml`` into a list of source-config dicts (empty if absent)."""
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = data.get("sources", []) if isinstance(data, dict) else []
    return [entry for entry in entries if isinstance(entry, dict)]


def build_sources(
    client: HttpGetter,
    fetched_at: str | None = None,
    configs: list[dict[str, Any]] | None = None,
) -> list[Source]:
    """Instantiate the ENABLED sources from config (defaults to sources.yml)."""
    resolved = configs if configs is not None else load_source_configs()
    sources: list[Source] = []
    for cfg in resolved:
        if not cfg.get("enabled"):
            continue
        kind = str(cfg.get("type", ""))
        publisher = str(cfg.get("publisher", ""))
        if kind == "ecourts":
            endpoints = tuple(str(e) for e in (cfg.get("endpoints") or []))
            sources.append(
                EcourtsSource(
                    client,
                    endpoints=endpoints or None,
                    publisher=publisher or "eCourts",
                    fetched_at=fetched_at,
                )
            )
        elif kind == "rss":
            url = str(cfg.get("url", "")).strip()
            if not url:
                continue
            feeds = (Feed(url=url, publisher=publisher or "Media"),)
            sources.append(RssMediaSource(client, feeds=feeds, fetched_at=fetched_at))
    return sources
