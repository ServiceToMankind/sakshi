"""Sakshi data pipeline: fetch -> extract -> sanitize -> dedupe -> validate -> shard.

Sakshi ("witness") aggregates PUBLICLY REPORTED sexual-assault cases across India
from public judicial records and credible media into a static, filterable record.

Phase 0 obligations are non-negotiable and encoded as automation throughout this
package: victim identity is NEVER ingested, the accused are presumed innocent, and
every published data point carries a citable public source.
"""
