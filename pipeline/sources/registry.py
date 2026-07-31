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
from pipeline.sources.http import HttpClient
from pipeline.sources.indiankanoon import IndianKanoonSource
from pipeline.sources.rss_media import Feed, RssMediaSource

__all__ = ["build_sources", "load_source_configs"]


def load_source_configs(path: Path = config.SOURCES_CONFIG_PATH) -> list[dict[str, Any]]:
    """Parse ``sources.yml`` into a flat list of source-config dicts, each tagged with the
    ``state`` it belongs to (§3). The file is organised BY STATE — ``national`` for
    non-state-specific sources and ``states: {DL: [...], MH: [], ...}`` where every state is a
    declared block and an empty list is a declared coverage gap. A legacy flat ``sources:``
    list is still accepted (its entries are tagged ``national``). Empty if absent."""
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return []
    if "sources" in data:  # legacy flat list
        return [{"state": "national", **e} for e in data["sources"] if isinstance(e, dict)]
    out: list[dict[str, Any]] = []
    for entry in data.get("national") or []:
        if isinstance(entry, dict):
            out.append({"state": "national", **entry})
    for state, entries in (data.get("states") or {}).items():
        for entry in entries or []:
            if isinstance(entry, dict):
                out.append({"state": str(state).strip().upper(), **entry})
    return out


# Source types that are COURT-RECORD provenance (re-checkable status), used by the weekly
# refresh (§2), which re-queries only these — never the media discovery feeds.
_COURT_SOURCE_TYPES = frozenset({"ecourts", "indiankanoon"})


def build_sources(
    client: HttpClient,
    fetched_at: str | None = None,
    configs: list[dict[str, Any]] | None = None,
    court_only: bool = False,
) -> list[Source]:
    """Instantiate the ENABLED sources from config (defaults to sources.yml).

    ``court_only`` (the weekly ``refresh`` mode, §2) restricts to court-record sources — the
    ones that carry re-checkable judicial status — and skips the media discovery feeds.
    """
    resolved = configs if configs is not None else load_source_configs()
    sources: list[Source] = []
    for cfg in resolved:
        if not cfg.get("enabled"):
            continue
        kind = str(cfg.get("type", ""))
        if court_only and kind not in _COURT_SOURCE_TYPES:
            continue
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
        elif kind == "indiankanoon":
            queries = tuple(str(q) for q in (cfg.get("queries") or []) if str(q).strip())
            if not queries:
                continue
            sources.append(
                IndianKanoonSource(
                    client,
                    queries=queries,
                    publisher=publisher or "Indian Kanoon",
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
