# RFC: Volunteer-assisted bulk historical import

**Status:** Draft (overnight, queue X3) · **Owner:** unassigned · **Decision:** pending operator

## Problem

The live pipeline discovers cases forward in time from public feeds and court
mirrors. It cannot reach the long tail of **historical** cases — reported years
ago, settled in judgments that no feed still lists — that never flow past a live
source. Volunteers (law students, journalists, NGOs) are willing to surface these,
but there is today no path for them to contribute **without hand-editing `data/`**,
which the project forbids: humans never edit the tree, and every published field
must trace to a citable public source and pass every guardrail.

This RFC proposes a volunteer import path that enters through the **exact same
gates** as the live pipeline, so a volunteer can add reach but never bypass a
protection.

## Non-goals

- No new public **fields**, and no change to the identity floor (§1a). A volunteer
  import is subject to the same `additionalProperties:false`, forbidden-field list,
  minor projection, and `pii_guard` as any other record.
- No victim-identifying input, ever — not even transiently. A volunteer submits a
  **public source URL + structured claims**, never a narrative pasted from a
  judgment (a judgment is a HIGH-PII input, §1b; only the extractor reads it, in
  memory).
- No trust in volunteer free-text. Everything is re-derived by the pipeline.

## Proposed design

A volunteer contributes an **import manifest**, not a record:

```yaml
# imports/<batch-id>.yml  (one entry per case)
- source_url: https://indiankanoon.org/doc/…/    # a PUBLIC court/media URL
  source_type: court                              # court | news_article | press_release
  # optional structured HINTS the volunteer read from the PUBLIC source — never prose:
  state: TG
  district: Warangal
  offence_sections: ["BNS 64", "POCSO 4"]
  cnr: TSHC01-001234-2019
  contributor: <handle>
  attestation: "public source; no victim-identifying content included"
```

The manifest carries **only** a URL, a provenance class, and non-identifying
structured hints (state/district/sections/CNR). It **cannot** carry a victim field
— the import schema mirrors `extraction.schema.json`'s constraints, so a manifest
is structurally incapable of holding identity.

### Flow (reuses the existing stages verbatim)

1. **Fetch.** The pipeline fetches each `source_url` with the existing
   `PoliteClient` (robots-respecting). Raw text is HIGH-PII and lives only in
   memory (§1b) — never written, logged, or cached. A robots-disallowed or dead
   URL is skipped and reported, never guessed.
2. **Extract.** The same schema-constrained extractor runs over the fetched text
   → `extraction.schema.json` structured fields only. The volunteer's hints may
   pre-fill `state`/`district`/`sections` but the extractor's own output wins on
   conflict, and the model still forces `victim: null`.
3. **Sanitize.** The unchanged last gate (`sanitize.py`) + minor projection.
4. **Dedupe.** Case-anchored (CNR/FIR/court), against the existing tree — an import
   that matches a live record MERGES (court beats media), never duplicates.
5. **Confidence + verify.** Sub-threshold or unverifiable records quarantine to
   `_review` exactly as today. A volunteer import is **never auto-published**: it
   enters `data/_review/` (or the held queue) for the same human sign-off as any
   fresh candidate — the operator approves a batch, it is not self-certifying.
6. **Validate & shard.** `jsonschema` + `pii_guard` + the summary-size + readability
   gates, unchanged.

### What is new (small, reviewable surface)

- `imports/` directory + `schemas/import-manifest.schema.json` (mirrors the
  extraction constraints; `additionalProperties:false`; no victim field).
- An import **reader** that turns a manifest entry into the same in-memory
  `RawDocument` + hint set the live sources produce — then hands off to the
  unchanged fetch→extract→…→shard path. No new extraction, sanitize, or dedupe
  logic; the import reader is a thin *source*, like `rss_media` or `ecourts`.
- A `--mode import` (alongside `discover`/`refresh`) that runs the pipeline over a
  manifest instead of live feeds, staging a review PR the operator approves.

### Attribution & audit

Each imported record's `sources[]` cites the public URL exactly as a live record
does. The manifest (contributor handle + attestation) is committed under
`imports/`, so provenance of the *contribution* is auditable in git, separate from
the record's *source* citation. No contributor identity appears in `data/`.

## Guardrail analysis

- **Victim identity:** never ingested — the manifest cannot hold it, and the
  fetched source text is read only in memory by the extractor (§1b). Same floor as
  the live path.
- **Named accused:** only from court sources, same rule. A media-URL import carries
  `name_public_court_record: null`.
- **Minors:** the minor projection runs unchanged; an imported minor is held, never
  auto-published, and rendered at the minimal shape.
- **No hand-editing `data/`:** volunteers touch `imports/` only; the pipeline
  regenerates `data/`.
- **Fabrication:** a manifest with an unreachable/robots-disallowed URL yields
  nothing — no record is invented from a hint alone.

## Open questions for the operator

1. **Contributor vetting.** Open manifests + review, or a trusted-contributor
   allowlist for larger batches?
2. **Rate/cost.** Historical batches can be large; the monthly spend cap
   (`MONTHLY_MAX_USD`) applies, but a dedicated import budget may be wanted.
3. **Court-source access.** Historical court records often need Indian Kanoon (paid
   token) — imports of judgment URLs inherit that dependency.
4. **Review load.** Every import lands in the human queue; a large batch needs a
   batch-review affordance so the queue-depth alert (>25) is not tripped by design.

## Rollout

Ship behind a flag (`--mode import`, no live-feed change), pilot with a small
operator-authored manifest of already-known cases to validate the path end-to-end,
then open to vetted contributors. No production behaviour changes until the flag is
used.
