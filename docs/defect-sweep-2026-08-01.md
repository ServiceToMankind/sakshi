# Defect sweep — 2026-08-01 (overnight, queue X4)

An offline sweep for the defects the audit named: two-letter state codes in
user-facing text, records with an unresolved jurisdiction, and published summaries
failing the readability gate. Findings below; nothing here was auto-applied.

## 1. State CODE in minor summaries — SYSTEMATIC (needs a human-approved issue)

All **15** published minor summaries render the two-letter **state code**, not the
full state name — e.g. `"…in Gurugram, HR (2026)…"`, `"…, TG…"`, `"…, DL…"`,
`"…, UP…"`. It is user-facing (the site renders `summary` verbatim).

- **Where:** the flat-template branch of `pipeline/sanitize.py::minor_summary`
  (`location = ", ".join((district, state))`). The **composer** branch
  (`minor_summary_compose`) already uses the district only, so a minor with ≥2
  structured facts is unaffected — only the flat-template fallback shows the code.
- **Why not fixed tonight:** `sanitize.py` is a protected file (CLAUDE.md §2; 100%
  branch coverage). The fix is a one-line **wording** change (map the code to a
  full name via `pipeline/states`, or drop the state since the district already
  localises), which NIGHT_RUN hard-stop 6 arguably permits as "wording" — but a
  protected-file change plus a 15-record **data regen (AMBER)** is an operator
  decision, not an unattended one. Tracking issue opened; see below.
- **Not a guardrail breach:** a state code/name is public, non-identifying; the
  POCSO s.23 floor is untouched. This is a readability/polish defect.

## 2. Two-letter codes in the FRONTEND — CLEAN

Every state rendered in `site/src` goes through `format.js::stateName()` (full
name). No raw `record.state` reaches user-facing text. (Only URL query params and
filter values use the code, which is correct.)

## 3. Unresolved jurisdictions — NONE

Every published record's `state` is a recognised canonical code
(`pipeline/states.CANONICAL_STATES`). The §4a jurisdiction gate quarantines any
unknown state, so none can be live.

## 4. Readability gate — CLEAN

`scripts/readability_guard.py` passes over every published non-minor summary
(part of `make check`). The new §6a pipeline gate (#107) now also quarantines a
*fresh* unreadable summary before it can publish.

## 5. Already addressed tonight

- **South District / South Delhi** dedup collision — the district canonicaliser no
  longer folds "South District" into "South Delhi" (#110). Whether to unify the two
  spellings (they belong to two distinct anchor-less minor cases) is an open
  data-modelling decision for the operator.
- **Amnesiac discovery** (records extracted from a headline/blurb the pipeline
  never re-fetches) — the article-body fetcher is built and flag-gated OFF in
  PR #112 (AMBER); enabling it needs the operator's live before/after validation.
