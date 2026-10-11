# Proposal: letting volunteers add historical cases in bulk

**Status:** draft, written overnight · **Owner:** not assigned yet · **Decision:** still
mine to make

> **Status, October 2026:** not built yet. The pipeline's `--mode` still accepts only
> `discover` and `refresh`, and there is no `imports/` folder.

## The problem

The live pipeline finds cases going forward, from public feeds and court-record mirrors.
It can't reach the long tail of **older** cases: ones reported years ago and decided in
judgments that no feed lists any more, so they never pass through a live source.
Volunteers (law students, journalists, NGOs) are willing to find these, but right now
there's no way for them to contribute **without editing `data/` by hand**, which this
project doesn't allow. Nobody edits that tree by hand, and every published field has to
trace to a public source and pass every check.

This proposal is for a way for volunteers to add cases that goes through **exactly the
same checks** as the live pipeline, so a volunteer can widen our reach but can never get
around a protection.

## What this is not

- No new public **fields**, and no change to the identity protections (CLAUDE.md, section
  1a). A volunteer's case goes through the same `additionalProperties: false`,
  forbidden-field list, children's-case reduction and `pii_guard` as any other record.
- No victim-identifying input, ever, not even for a moment. A volunteer sends a **public
  source URL and structured hints**, never text pasted from a judgment (a judgment is a
  source full of personal detail, CLAUDE.md section 1b; only the extractor reads it, in
  memory).
- No trust in what volunteers write. The pipeline works everything out again itself.

## The design I'm proposing

A volunteer sends an **import list**, not a record:

```yaml
# imports/<batch-id>.yml  (one entry per case; values below are illustrative placeholders)
- source_url: https://indiankanoon.org/doc/…/    # a PUBLIC court or news URL
  source_type: court                              # court | news_article | press_release
  # optional structured HINTS the volunteer read from the PUBLIC source, never prose:
  state: TG
  district: TESTVILLE
  offence_sections: ["BNS 64", "POCSO 4"]
  cnr: TSHC01-000000-2019
  contributor: <handle>
  attestation: "public source; no victim-identifying content included"
```

The list holds **only** a URL, the kind of source, and structured hints that identify no
one (state, district, sections, CNR). It **can't** hold a victim field. The import schema
copies the limits of `extraction.schema.json`, so an import list has no room for anyone's
identity.

### How it would flow (reusing the existing steps exactly)

1. **Fetch.** The pipeline fetches each `source_url` with the existing `PoliteClient`
   (which follows robots.txt). The raw text is full of personal detail and lives only in
   memory (CLAUDE.md, section 1b): never written, logged or cached. A URL that robots.txt
   disallows, or that's dead, is skipped and reported, never guessed at.
2. **Extract.** The same schema-constrained extractor reads the fetched text and returns
   only the structured fields in `extraction.schema.json`. The volunteer's hints may
   pre-fill `state`, `district` and `sections`, but the extractor's own answer wins if they
   disagree, and the model still has to return `victim: null`.
3. **Sanitize.** The same last gate (`sanitize.py`) and the children's-case reduction.
4. **Dedupe.** Matched on the case (CNR, FIR, court) against the existing record. An
   import that matches a live record is MERGED into it (court beats media), never added
   twice.
5. **Confidence and verification.** Records below the threshold, or that can't be
   checked, go to `_review` exactly as they do today. A volunteer's case is **never
   published automatically**: it goes into `data/_review/` (or the held queue) for the
   same human sign-off as any new case. I approve a batch; it can't approve itself.
6. **Validate and write.** `jsonschema`, `pii_guard`, the summary size limit and the
   plain-English check, unchanged.

### What's new (small, and easy to review)

- An `imports/` folder and `schemas/import-manifest.schema.json` (copying the extraction
  limits; `additionalProperties: false`; no victim field).
- An import **reader** that turns each entry into the same in-memory `RawDocument` and
  hints that the live sources produce, then hands off to the unchanged
  fetch → extract → … → write path. No new extraction, sanitizing or matching logic. The
  import reader is just a thin *source*, like `rss_media` or `ecourts`.
- A `--mode import` (next to `discover` and `refresh`) that runs the pipeline over an
  import list instead of live feeds, and stages a review PR for me to approve.

### Credit and checking

Each imported record's `sources[]` cites the public URL exactly as a live record does.
The import list (contributor handle and attestation) is committed under `imports/`, so
who contributed what can be checked in git, separately from the record's *source*
citation. No contributor's identity appears in `data/`.

## Does it keep every protection?

- **Victim identity:** never collected. The import list can't hold it, and the fetched
  source text is only read in memory by the extractor (CLAUDE.md, section 1b). Same
  protection as the live path.
- **Named accused:** only from court sources, same rule. An import from a news URL carries
  `name_public_court_record: null`.
- **Children:** the children's-case reduction runs unchanged; an imported child's case is
  held, never published automatically, and shown in the minimal form.
- **No hand edits to `data/`:** volunteers only touch `imports/`; the pipeline rebuilds
  `data/`.
- **Made-up cases:** an entry whose URL can't be reached or is disallowed by robots.txt
  produces nothing. No record is ever made from a hint alone.

## Questions I still need to answer

1. **Vetting contributors.** Open import lists plus review, or a list of trusted
   contributors for bigger batches?
2. **Volume and cost.** Historical batches can be big. The monthly spending cap
   (`MONTHLY_MAX_USD`) applies, but a separate budget for imports might be wanted.
3. **Access to court records.** Older court records often need Indian Kanoon (a paid
   token), so imports of judgment URLs depend on it too.
4. **Review load.** Every import lands in the human queue. A big batch needs a way to
   review a whole batch at once, so the queue-size warning (over 25) isn't set off by
   design.

## Rolling it out

Build it behind a setting (`--mode import`, with no change to the live feeds), try it with
a small import list I write myself of cases we already know about to check it end to end,
then open it to vetted contributors. Nothing changes in the live pipeline until that
setting is used.
