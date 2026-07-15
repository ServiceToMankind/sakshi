# Launch Review — Sākshī supervised pipeline

> Evidence-based launch-readiness review. Every claim below cites the code, test,
> PR, or staged-run stat that establishes it. Nothing here is aspirational — if an
> item is not yet met, it says so. Real data ships only after a human merges a
> staged review PR.

**Status:** 🟢 LIVE with 4 operator-approved records. Supervised / staged:
`LAUNCH_MODE=staged`, **`PUBLISH_APPROVED_ONLY=true`** (only records on the approval
allowlist publish), **daily cron enabled** (06:00 IST), scope **ALL states, no
incident-age window** (`LAUNCH_STATES=ALL`, `LAUNCH_LOOKBACK_DAYS` unset), flash model.
Nothing publishes without an explicit operator approval. Unattended `auto` still
blocked pending `SCRAPE_BOT_TOKEN` (see §Standing operations).

---

## Launch night — 2026-07-14 (real first run)

The site is **live** at https://sakshi.stmorg.in/ and the pipeline runs end-to-end on
real data. Guardrail summary of what shipped this session:

- **Record-loss fix (PR #27).** A published record settles `published` only once it is
  confirmed on `main`; until then it is `staged_pending` and re-surfaces every run, so a
  force-pushed staging branch can never destroy the only copy. Three adversarial review
  rounds. Fixed the 4-day loss of 3 records.
- **Graduated auto-publish gate (PR #28).** A record AUTO-publishes only if non-minor
  **and** no accused named **and** durably sourced (court/news_article/press_release)
  **and** confidence ≥ 0.85 **and** no POCSO→non-minor mismatch. Everything else —
  minors, named accused, live-blog-only, the 0.80–0.84 band — is **held** in
  `data/_needs_review/queue.json` (never on the public site, carried over so never lost,
  re-split each run so a court update can promote it). Three adversarial review rounds
  caught 15+ real defects (incl. a minor's day-precise detail auto-publishing, id-fusion
  between distinct cases) — all fixed with regression tests. Minor determination fails
  **closed**: absent/None/POCSO ⇒ treated as minor (projected + held).
- **Deploy guardrail (PR #28).** The Pages deploy excludes `_needs_review` + `_meta`;
  held records (incl. named accused) are **not web-reachable** — verified
  `GET /data/_needs_review/queue.json` → 404.
- **Scope guard (PR #28).** A run refuses to start unless `LAUNCH_STATES` explicitly
  resolves (never silently unscoped). The heartbeat shows scope, auto-published, held,
  and needs-review queue depth (⚠ > 25) every day on ops issue #24.

### First real records LIVE (2026-07-15)
Fetched **520** media documents; extracted real sexual-offence cases — the available
city-media is dominated by **minor/POCSO** cases, which the gate correctly holds
(minors are never auto-published, POCSO s.23). The operator reviewed the held queue and
**approved 4 cases** (DL/HR/TG/UP); they are now **live** at https://sakshi.stmorg.in,
each projected to the non-identifying minimal shape (state/district/**year**/offence/
status + POCSO template, no name/age/address). `pii_guard` + schema validation clean.

Publication mechanics (this launch):
- **Approval allowlist** (`data/_needs_review/approved.json`, by raw source URL): a
  held record whose URL is approved is published, still projected — approval never
  un-projects. Same-article duplicates are merged only within the approved set.
- **`PUBLISH_APPROVED_ONLY=true`** (supervised): during the launch, even an
  auto-publish-eligible (adult) record is HELD unless approved, so nothing reaches the
  site without an explicit operator approval. A fresh run auto-cleared 3 unreviewed
  adult cases (one with mismatched sections — a likely misclassification); this flag
  holds them. Set it `false` to resume normal auto-publish of the safe class.
- Both went through three adversarial review rounds; the promotion path re-runs the
  full last gate (coerce-minor → sanitize/project → withhold names) on every promoted
  record.

### Known follow-ups
- **Issue #29** — id reuse via serial-HWM regression (edge case; not triggered by the
  media-only launch).
- Age-based review-queue warning (> 7 days) — needs a `first_seen` per held record;
  depth-based (> 25) already ships.
- Court sources (eCourts / Indian Kanoon) remain unwired (CAPTCHA / paid token); all
  current data is media-sourced, so accused names are always withheld.

## Standing operations & enabling unattended auto

The daily cron runs **staged**: it opens/updates the data-review PR; a human merge
publishes. **Unattended `auto` is blocked because `github-actions[bot]` cannot bypass the
`main-protection` ruleset** (PR + `Python checks (3.12)` + `Frontend checks` required).
To enable it: provision an **admin PAT / GitHub-App token as the `SCRAPE_BOT_TOKEN`
secret** (the workflow already prefers it), then set `LAUNCH_MODE=auto`; the next cron
will auto-commit ONLY the graduated-gate auto-eligible class and deploy. Until then, the
staged-PR → human-merge model is the safe standing operation.

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

## C. Accused names only from court records (PR #15)

- Media-sourced records carry `name_public_court_record: null`; names are unioned
  only from official court sources in `dedupe.merge_records`. As a deterministic,
  model-independent backstop, `validate.withhold_unsourced_accused_names` nulls any
  accused name on a record lacking BOTH a court name and a case anchor (CNR/FIR) —
  so a bare index entry or media item can never publish a name.
- **Evidence:** the first published-candidate record (media) had `accused: null`;
  `test_validate.py::test_withhold_unsourced_accused_names`;
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

## J. Court-source accessibility (PR #11, #15)

- Direct eCourts case-search is **CAPTCHA-gated → unavailable** (we never bypass a
  CAPTCHA); consumed only via operator-resolved endpoints. NJDG is stats-only.
  Indian Kanoon (documented API, court-record mirror) is **fully wired** — per-run
  cost budget, and the provenance ruling that its *docsource* (the court) confers
  court-grade while an IK-indexed news item stays media-grade — but **disabled**
  pending an operator token + ToS decision. Accused names publish only with a court
  name **and** a case anchor (`validate.withhold_unsourced_accused_names`). RSS
  intake moved to DL+TG crime/city section feeds. **Evidence:** `sources.yml`,
  `test_indiankanoon.py`, `test_provenance.py`, `test_validate.py`.

## K. Coverage under provider degradation (PR #13)

- A committed, PII-safe processed-document ledger (`data/_meta/processed.json`,
  keyed by `sha256(url)`) lets a truncated run skip already-settled documents so its
  next 40-min budget goes to the backlog tail — "delay, not loss". Only terminal
  outcomes (`published`/`out_of_scope`/`not_a_case`) settle; a quarantined or
  scope-filtered document is never settled and re-surfaces next run. Failing docs
  retry 3 runs, then park as `failed_permanent` with the URL logged for review.
- **Persisted on a dedicated unprotected `ledger-state` branch** (restored before
  each run, persisted after), so cross-run coverage accounting works regardless of
  PR-merge timing without touching protected `main` (`github-actions[bot]` cannot be
  granted ruleset bypass — GitHub 422). Fenced three independent ways: (a) validated
  against `schemas/ledger.schema.json` (sha256 keys, outcome enum, ISO dates,
  `additionalProperties:false`) + a no-URL scan; (b) `pii_guard` over `data/_meta/`;
  (c) the Contents API writes exactly one path. A scope-filtered case settles
  `out_of_window` (terminal for coverage); quarantined docs never settle. Provider
  errors are captured per run (`error_samples`) so an abort is diagnosable
  (429 RESOURCE_EXHAUSTED vs 503 UNAVAILABLE).
- **Evidence:** `test_ledger.py`, `test_orchestrator.py` (settled-skip +
  quarantine-re-surface), `test_validate.py::test_validate_ledger_*`. Hardened by a
  14-agent adversarial review that caught and fixed three high-severity data-loss
  paths in the first cut.

---

## L. Grounded verification before publish (issue #41, PRs #42 / #43 / #44)

The bridge that lets records publish WITHOUT a human reading each one first, while
keeping every Phase 0 guardrail intact. A second, stronger model
(`gemini-2.5-pro` + Google Search grounding, config-pinned) re-checks each in-scope
candidate against its cited source BEFORE publish and stamps `verified`.

- **What the verifier may do:** (a) confirm the source text supports every field;
  (b) re-check scope (a real, specific reported sexual-offence case — not a
  commentary/trend/editorial piece); (c) run one grounded search and attach a second
  corroborating source; (d) emit `verified` + a one-sentence `verification_note`, or
  DEMOTE (`verified:false`). It may correct only a small set of FACTUAL fields
  (`CORRECTABLE_FIELDS` in `pipeline/verify.py`).
- **What it can NEVER do** (deterministic gates are supreme): it cannot touch
  `minor_involved`, `accused`, `id`, a source URL, or a minor's deterministic
  `title`/`summary`. A verifier that believes `minor_involved` is wrong must DEMOTE,
  not flip it. A minor's content is never model-written; the verifier only decides
  whether the *projected* minor record is publishable, never what it says.
- **Publish rules (verifier-live, `VERIFY_ENABLED=true`):**
  - A FRESH record must be `verified:true` to publish; otherwise it is quarantined to
    `data/_review/` with the verifier's note — never onto the site.
  - A verified record still passes the full last gate + the graduated auto-publish
    gate **minus** `minor_involved`: a verified **minor** DOES publish (its
    title/summary are deterministic, non-identifying — POCSO s.23 projection), but a
    **named (court) accused** still routes to the human queue (defamation), as do
    `pocso_minor_mismatch`, live-blog-only, and sub-threshold confidence.
  - Every published record is re-run through `coerce_minor → sanitize/project →
    withhold-unsourced-names`, so a dedupe merge that flips `minor_involved` after the
    per-candidate sanitize is re-projected to the minimal shape before it reaches
    either a shard **or** `data/recent.json`.
  - **Grandfathering:** a record already live on the site is never unpublished by the
    verifier flip — even if its source has rolled off the feed and it cannot be
    re-verified this run (record-loss guardrail). Only genuinely fresh cases face the
    verified-gate.
  - **Carryover never lost:** the verifier runs only on fresh candidates, so a
    carried-over held record can never earn `verified`. It is therefore HELD (kept in
    the review queue), never swept to the `_review` quarantine — only a *purely-fresh*
    candidate the verifier declines is quarantined. Human approval is honoured in
    verifier-live mode exactly as in the supervised phase.
- **Hardened by a 3-lens adversarial review** (PII-leak, record-loss, verifier-logic)
  which found and fixed: a minor's model-written `verification_note` reaching the shard
  un-scanned (stripped now; canonical fix tracked in issue #44); the verifier flip
  sweeping the entire held queue into `_review` (permanent loss); dead approval logic
  under the verifier; `verified` lost across a dedupe merge; the corroborating source's
  empty date quarantining verified records; truthy-coerced `verified`; an unbounded
  per-call cost; and non-http `second_source` URLs. All with regression tests.
- **OPEN OPERATOR DECISION — require corroboration for unattended publish?** The
  verifier is designed to attach a grounded second source. Today a *single-source*
  fresh verified record still auto-publishes (per the "verified + gates → publish"
  spec). A stronger anti-fabrication / anti-injection posture is to HOLD any fresh
  verified record with `< 2` independent sources for human review (no record is lost —
  it just waits). This trades auto-publish reach (nil when grounding is unavailable)
  for stronger corroboration. Not enforced yet; decide before flipping to auto. The
  source text is already fenced as untrusted data in the verifier prompt, and non-http
  corroborating URLs are rejected at ingestion.
- **OPERATOR NOTE — `verified` OR-fold across a merge.** A case is verified if ANY copy
  in its dedupe cluster was verified (so a fresh verified copy is never lost to a
  budget/no-source skip on another copy). A benign corner: a record previously verified
  and HELD *only* for `live_blog_only`, if a fresh copy the verifier declined this run
  adds a durable source, merges to `verified:True` with no remaining hold and
  auto-publishes — even though its freshest verdict was "not verified." It leaks nothing
  (the publish form is re-projected and unsourced names withheld) and loses/duplicates
  nothing; it is a policy nuance to be aware of, not a guardrail breach. A fix-verification
  pass confirmed the record-loss fixes introduce no new loss/duplication/leak.
- **Fail-safety & cost:** every error path (unparseable verdict, provider exception,
  missing source text, budget exhausted) leaves a record `verified:false`
  (quarantined) — fail-closed. Runs only on in-scope candidates (a handful/day) under
  a hard per-run USD cap (`VERIFY_MAX_USD`, default $0.50); a candidate not verified
  within budget stays quarantined. The daily heartbeat carries a `verify (guardrail
  L)` line (verified / demoted / est. $).
- **Evidence:** `test_verify.py` (parse/apply/budget/error/no-source paths),
  `test_orchestrator.py` (verified minor publishes, unverified quarantined, named
  accused held, legacy live record grandfathered across a verifier flip,
  POCSO-nonminor fail-closed coerced to a projected minor). Hardened by a 3-lens
  adversarial review (PII-leak, record-loss, verifier-logic) before merge.

---

## Staged-run evidence

_Two-state (TG, DL), 30-day scope, `staged` mode. Every run finished inside its
job window (the wall-clock budget truncates gracefully under provider load — never
a job kill)._

| run | sources | fetched | extracted | published | review | cost | note |
|---|---|---|---|---|---|---|---|
| `29099657465` | national RSS | 260 | 16 | 0 | 1 | $0.087 | truncated; live-blog quarantined |
| `29104649205` | crime/city RSS | 520 | 0 | 0 | 0 | $0.045 | truncated; 1 out-of-scope rejected |
| `29110062044` | crime/city RSS | 520 | 0 | 0 | 0 | $0.000 | **aborted** (quota/free-tier, pre-billing-fix) |
| `29112065032` | crime/city RSS | 520 | 6 | 0 | 0 | $0.413 | **full coverage** (billing fixed); 0 in TG/DL·30d |

The billing fix restored the key: run `29112065032` processed the **entire** 520-doc
set (not truncated, not aborted) at `serviceTier: standard`, extracting 6 real
sexual-offence cases — **none in the TG/DL 30-day window** → 0 published. Only
13/520 calls hit transient `503`/`504` blips (captured in `error_samples`), handled
by the resilience without aborting. This is **full-coverage empty run #1** toward
the launch-eligibility target. **Zero court-sourced records** — eCourts is
CAPTCHA-gated and Indian Kanoon is disabled, so court records await an operator
credential (§J).

---

## Operator decisions required before flipping to `auto`

1. **Indian Kanoon**: accept ToS + provision `INDIANKANOON_API_TOKEN`, then enable
   `indian-kanoon` in `sources.yml` — the primary legitimate court-record path.
2. **eCourts endpoints**: supply official-API / manually-resolved DL+TG endpoints
   (or a robots-permitted High Court judgment listing) — direct search stays off
   (CAPTCHA).
3. **CI approval friction — wired (PR #14), awaits secret**: the scrape job now
   pushes/opens the staged PR with `SCRAPE_BOT_TOKEN` (fine-grained PAT / App token)
   so its CI runs automatically; it falls back to `GITHUB_TOKEN` (today's manual
   approval) until the secret is set. Provision it per CONTRIBUTING.md §Operations.
4. **Human review of every staged record** remains mandatory. Do not enable the
   schedule or `LAUNCH_MODE=auto` until this review is signed off.

## Launch-eligibility target (not yet met)

Per the pre-launch plan, `auto` is gated on either **≥1 published** court-sourced or
news_article record in the TG/DL·30-day window, **or three consecutive
full-coverage runs** (the ledger shows the whole fetch set settled) proving the
window is genuinely empty. No run has yet completed full coverage under a healthy
provider; the ledger now makes spaced runs converge on that answer.

## Sign-off

- [ ] Phase 0 guardrails (A–B) reviewed against code + tests.
- [ ] Accused-name, dedup, confidence, provenance, scope gates (C–G) reviewed.
- [ ] Resilience + staged mechanism (H–I) reviewed.
- [ ] Court-source plan (J) + coverage ledger (K) + operator decisions accepted.
- [ ] Launch-eligibility target met (≥1 published, or 3 full-coverage empty runs).
- [ ] At least one full staged review PR inspected record-by-record.
