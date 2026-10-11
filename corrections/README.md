# Corrections

This folder holds fixes that a person has written and reviewed, for the few things the
pipeline can't fix on its own: for example, two cases it merged and can't separate
again, or a summary whose source article has dropped off the feed and can't be read
again.

Nobody edits `data/` by hand; the pipeline rebuilds it. A correction file is the
**only** approved way for a person to change a published record, and the pipeline
applies it (`pipeline/corrections.py`). Nobody changes `data/` directly.

Every `.yml` file in this folder is an active correction.

## Format

One file per record: `corrections/<record-id>.yml`, checked against
[`../schemas/correction.schema.json`](../schemas/correction.schema.json).

This example is illustrative only. The ID, district and link are placeholders, not a
real case.

```yaml
record_id: SKS-2026-XX-000000 # required: the record this applies to
author: <name or handle> # required
date: 2026-08-01 # required: YYYY-MM-DD
reason: <one line, in plain words: why this correction exists> # required
evidence: # optional: the sources you relied on
  - https://indiankanoon.org/doc/…/
# --- then EITHER quarantine, OR overrides (or both) ---
quarantine: true # take the record OFF the public site and into review
overrides: # OR: fix specific fields (applied before the sanitizer)
  status: ACQUITTED
  district: TESTVILLE
resolution: <optional: when this file can be removed>
```

## Rules

- Corrections are applied **after extraction and before the sanitizer**, so a corrected
  value still has to pass every check (the sanitizer, the schema, `pii_guard`).
- An override can **never** set a field that identifies a victim, an `id`, or
  `minor_involved`. Those keys are thrown away before the override is applied.
- A corrected record is marked `corrected: true` and shows a **"Corrected"** label on the
  site. The committed file is the record of what changed and why.
- Adding a correction is a **data change**. It goes through a reviewed PR, like any other
  change to what the public record says about a real case.
