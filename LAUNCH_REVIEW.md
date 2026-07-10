# Launch Review — Sākshī supervised pipeline

> Evidence-based launch-readiness review. Every claim below cites the code, test,
> PR, or staged-run stat that establishes it. Nothing here is aspirational — if an
> item is not yet met, it says so. Real data ships only after a human merges a
> staged review PR.

**Status:** supervised / staged. `LAUNCH_MODE=staged`, cron disabled, scope limited
to **TG + DL, 30-day** lookback. No auto-publish, no schedule, until this review is
signed off.

---

## A. Phase 0 — victim identity is never ingested (BNS s.72)

- The extraction schema (`schemas/extraction.schema.json`) is structurally
  incapable of holding victim identity: no victim/name/address/contact fields, and
  a required `victim` const that must be `null`. `additionalProperties:false` at
  every object level.
- `pipeline/sanitize.py` (the last gate) drops every forbidden field name and
  redacts PII value-patterns before disk; `scripts/pii_guard.py` re-asserts over
  the written tree.
- **Evidence:** `sanitize.py` + `pii_guard.py` held at **100% branch coverage**
  (`make check`); `test_orchestrator.py::test_assert_no_pii_blocks_planted_leak`.

## B. Minor protection — POCSO s.23 (issue #7, PR #8)

- **Two independent layers.** (1) `sanitize.project_minor_record` structurally
  replaces a minor case's summary with a fixed template and truncates
  date/`pending_days`/`next_hearing`/history to a non-identifying granularity.
  (2) `case.schema.json` `allOf/if-then-else` on `minor_involved` rejects any
  non-projected minor record at validation. Both must fail for a leak to ship.
- Defence in depth: age-expression detection quarantines a non-minor record whose
  free text still states an age (`age_detail_present`); `pii_guard` asserts no
  **published** shard carries an age.
- **Evidence:** `test_sanitize.py` (incl. the synthetic-ified shape of the first
  leaking record), `test_validate.py` (minor conditional), `test_pii_guard.py`
  (age scan). Verified live: a real minor/live-blog record was projected AND
  quarantined, never published.

## C. Accused names only from court records

- Media-sourced records carry `name_public_court_record: null`; names are unioned
  only from official court sources in `dedupe.merge_records`.
- **Evidence:** the first published-candidate record (media) had `accused: null`;
  `test_dedupe.py::test_merge_unions_sources_and_remaps_status_history`.

## D. Case-anchored deduplication (never identity)

- Matches on CNR, year-qualified FIR, station, district, date, court — never on
  victim identity. **Evidence:** `test_dedupe.py` (exact/strong/weak/fuzzy, FIR-year).

## E. Confidence quarantine

- Records with `confidence < 0.8` are routed to `data/_review`, never published.
  **Evidence:** `test_dedupe.py::test_low_confidence_goes_to_review`; verified live.

## F. Source provenance (issue #7, PR #8 / #11)

- Each source is stamped `court | news_article | live_blog | press_release`. A
  record whose only provenance is a rolling live-blog is capped at `confidence
  0.79` and auto-quarantined — a mutable, URL-decaying page is not durable enough
  for a permanent public claim.
- **Evidence:** `test_provenance.py`, `test_gemini.py`; verified live — a real
  live-blog case (source_type=live_blog, confidence 0.79) was quarantined.

## G. Out-of-scope offence rejection (PR #10)

- This record tracks **sexual offences only**. Two independent layers: (a) the
  extractor emits a required `in_scope` boolean and drops non-sexual cases
  pre-sanitize (counted `rejected_out_of_scope`); (b) `dedupe` quarantines
  (`scope_review`) any record whose cited `offence_sections` reference no
  qualifying BNS 63-79 / POCSO / IPC 354,375-377,509 statute.
- **Evidence:** the cheque-bounce shape (`NI Act 138`) is rejected by BOTH layers
  independently (`test_gemini.py::test_extract_rejects_out_of_scope_offence`,
  `test_dedupe.py::test_out_of_scope_offence_is_quarantined`); run stats report
  `rejected_out_of_scope` in `run.log` / `run_report.md` / `run_summary.env`.

## H. Resilience (PRs #3, #5, #6)

- Pinned model chain with provider failover; bounded per-call timeout + circuit
  breaker; a hard 40-min wall-clock budget so a run always finishes inside its
  60-min job window. **Evidence:** every recent staged run completed (graceful
  truncation under provider degradation, never a job kill); `test_gemini.py`.

## I. Staged-launch mechanism

- Each run commits `data/` to `data-staging` and opens/updates a review PR to
  `main`; auto-publish is skipped unless `LAUNCH_MODE=auto`. `data/_review` is
  gitignored (unreviewed data is never committed); quarantined records ride in the
  run artifact. Nothing reaches the live site without a human merge.
- **Evidence:** review PR #4; `scrape.yml`.

## J. Court-source accessibility (PR #11)

- Direct eCourts case-search is **CAPTCHA-gated → unavailable** (we never bypass a
  CAPTCHA); consumed only via operator-resolved endpoints. NJDG is stats-only.
  Indian Kanoon (documented API, court-record mirror) is wired but **disabled**
  pending an operator token + ToS decision. RSS intake moved to DL+TG crime/city
  section feeds. **Evidence:** `sources.yml` accessibility note; `test_indiankanoon.py`.

---

## Staged-run evidence

_Two-state (TG, DL), 30-day scope, `staged` mode. Every run finished inside its
job window (the wall-clock budget truncates gracefully under provider load — never
a job kill)._

| run | sources | fetched | extracted | rejected (scope) | published | review | cost |
|---|---|---|---|---|---|---|---|
| `29099657465` | national RSS | 260 | 16 | n/a (pre-gate) | 0 | 1 (live-blog → quarantined) | $0.087 |
| `29104649205` | crime/city RSS | 520 | 0 | **1** | 0 | 0 | $0.045 |

Both runs truncated at the 40-min budget under transient Gemini-flash degradation,
so each processed only a subset of documents. Observed live: the source-provenance
gate quarantined a live-blog record (run 1), and the **out-of-scope offence gate
rejected a non-sexual case** (run 2, `rejected_out_of_scope=1`). **Zero
court-sourced records** so far — eCourts is CAPTCHA-gated and Indian Kanoon is
disabled, so court records await an operator credential (§J). Whether the TG/DL
30-day window yields a publishable news_article case is not yet established: no run
has completed the full document set under a healthy provider.

---

## Operator decisions required before flipping to `auto`

1. **Indian Kanoon**: accept ToS + provision `INDIANKANOON_API_TOKEN`, then enable
   `indian-kanoon` in `sources.yml` — the primary legitimate court-record path.
2. **eCourts endpoints**: supply official-API / manually-resolved DL+TG endpoints
   (or a robots-permitted High Court judgment listing) — direct search stays off
   (CAPTCHA).
3. **CI approval friction**: the staged-run PR's CI parks as "Action required"
   because the `github-actions[bot]` token can't self-trigger workflows. Switch the
   scrape job to push/open the PR with a **PAT or GitHub App token** so CI runs
   automatically.
4. **Human review of every staged record** remains mandatory. Do not enable the
   schedule or `LAUNCH_MODE=auto` until this review is signed off.

## Sign-off

- [ ] Phase 0 guardrails (A–B) reviewed against code + tests.
- [ ] Accused-name, dedup, confidence, provenance, scope gates (C–G) reviewed.
- [ ] Resilience + staged mechanism (H–I) reviewed.
- [ ] Court-source plan (J) + operator decisions accepted.
- [ ] At least one full staged review PR inspected record-by-record.
