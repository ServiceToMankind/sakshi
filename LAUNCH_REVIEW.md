# Launch review — the supervised pipeline

> This is the review I wrote when Sakshi first went live, in July 2026. Every claim
> below points to the code, test, PR or run that backs it up. Nothing here is a hope: if
> something wasn't done yet, it says so. At launch, real data only reached the site after
> a person merged a staged review PR.
>
> It is kept as a record of how launch went. Some things have changed since, and those
> are listed in [What has changed since launch](#what-has-changed-since-launch) at the
> end.

**Status at launch:** live, with 4 records I had approved. The pipeline ran supervised
and staged: `LAUNCH_MODE=staged` and **`PUBLISH_APPROVED_ONLY=true`** (only records on
the approval list published), **the daily run switched on** (06:00 IST), covering **every
state with no limit on how old a case could be** (`LAUNCH_STATES=ALL`,
`LAUNCH_LOOKBACK_DAYS` unset), on the flash model. Nothing published without my explicit
approval. Running fully on its own (`auto`) was still blocked until `SCRAPE_BOT_TOKEN` was
in place (see [Running it day to day](#running-it-day-to-day-and-turning-on-auto)).

---

## Launch night — 14 July 2026 (the first real run)

The site went **live** at https://sakshi.stmorg.in/ and the pipeline ran end to end on
real data. What shipped that session to keep things safe:

- **Records can no longer be lost (PR #27).** A published record only counts as
  `published` once it is confirmed on `main`. Until then it's `staged_pending` and comes
  back every run, so a force-pushed staging branch can never wipe out the only copy. It
  went through three rounds of adversarial review, and it fixed the four-day loss of 3
  records.
- **A graded publishing gate (PR #28).** A record publishes on its own only if it is
  about an adult, **and** no accused is named, **and** it has a lasting source (court,
  news article or press release), **and** confidence is at least 0.85, **and** POCSO
  charges don't contradict the minor flag. Everything else (children's cases, named
  accused, live-blog-only, the 0.80–0.84 band) is **held** in
  `data/_needs_review/queue.json`: never on the public site, carried over so it's never
  lost, and re-checked every run so a court update can move it forward. Three rounds of
  adversarial review caught more than 15 real defects (including a child's day-precise
  date about to publish on its own, and two distinct cases being fused under one ID). All
  were fixed with regression tests. Deciding whether a case involves a child **fails
  safe**: if it's missing, empty or the charges are POCSO, it's treated as a child's case
  (reduced to the minimal form and held).
- **The deploy leaves held records out (PR #28).** The Pages deploy skips `_needs_review`
  and `_meta`, so held records (including any named accused) **can't be reached on the
  web**. I checked: `GET /data/_needs_review/queue.json` returns 404.
- **The run has to know its scope (PR #28).** A run refuses to start unless
  `LAUNCH_STATES` is set explicitly, so it's never silently unscoped. Every day the
  heartbeat on ops issue #24 shows the scope, how many records auto-published, how many
  were held, and how deep the needs-review queue is (with a warning above 25).

### The first real records went live (15 July 2026)
The run fetched **520** news documents and found real sexual-offence cases. The city
news available was mostly about **children / POCSO** cases, which the gate rightly held
(children's cases are never auto-published; Section 23, POCSO). I reviewed the held
queue and **approved 4 cases** (DL/HR/TG/UP). They went **live** at
https://sakshi.stmorg.in, each in the minimal form that identifies no one
(state/district/**year**/offence/status and the POCSO wording, with no name, age or
address). `pii_guard` and schema validation were clean.

How publishing worked at launch:
- **The approval list** (`data/_needs_review/approved.json`, by source URL): a held
  record whose URL I've approved is published, still in its reduced form. Approval never
  undoes that. Copies of the same article are merged only within the approved set.
- **`PUBLISH_APPROVED_ONLY=true`** (supervised): during launch, even a record that
  qualified to auto-publish (an adult's case) was HELD unless I approved it, so nothing
  reached the site without my explicit approval. A fresh run would otherwise have
  auto-published 3 unreviewed adult cases (one with charges that didn't fit, likely
  misclassified); this flag held them. Setting it to `false` lets the safe class
  auto-publish again.
- Both went through three rounds of adversarial review. Every record that gets promoted
  goes through the full last gate again (treat-as-child check, then sanitize and reduce,
  then withhold names).

### Still to do after launch
- **Issue #29**: an edge case where a case ID could be reused (not triggered by the
  news-only launch).
- A warning when a held record has waited more than 7 days. That needs a `first_seen`
  date per held record; the warning by queue depth (more than 25) already shipped.
- Court sources (eCourts / Indian Kanoon) weren't connected yet (one is behind a CAPTCHA,
  the other needs a paid token). All data at launch came from the media, so accused names
  were always withheld.

## Running it day to day, and turning on `auto`

At launch the daily run was **staged**: it opened or updated the data-review PR, and a
person merging it was what published. **Running unattended in `auto` was blocked because
`github-actions[bot]` can't get around the `main-protection` ruleset** (which requires a
PR plus the `Python checks (3.12)` and `Frontend checks` checks). The plan to enable it:
provide **an admin PAT or GitHub App token as the `SCRAPE_BOT_TOKEN` secret** (the
workflow already prefers it), then set `LAUNCH_MODE=auto`. The next scheduled run would
then auto-commit ONLY the class the graded gate allows, and deploy. Until then, staged PR
plus a human merge was the safe way to run it.

---

## A. The victim's identity is never collected (Section 72, BNS)

- The extraction schema (`schemas/extraction.schema.json`) has no place to hold a
  victim's identity: no victim, name, address or contact fields, and a required `victim`
  field that must be `null`. `additionalProperties: false` is set at every level.
- `pipeline/sanitize.py` (the last gate) drops every forbidden field name and redacts
  personal-data patterns before anything is written; `scripts/pii_guard.py` checks the
  written files again.
- **Evidence:** `sanitize.py` and `pii_guard.py` held at **100% branch coverage**
  (`make check`); `test_orchestrator.py::test_assert_no_pii_blocks_planted_leak`.

## B. Protecting children — Section 23, POCSO (issue #7, PR #8)

- **Two separate layers.** (1) `sanitize.project_minor_record` replaces a child's case
  summary with fixed wording and cuts the date, `pending_days`, `next_hearing` and history
  down to a level that identifies no one. (2) `case.schema.json` uses an
  `allOf/if-then-else` on `minor_involved` to reject any child's record that hasn't been
  reduced, at validation. Both would have to fail for a leak to ship.
- A further layer: spotting age expressions quarantines an adult's record whose text
  still states an age (`age_detail_present`), and `pii_guard` checks that no
  **published** file carries an age.
- **Evidence:** `test_sanitize.py` (including a made-up version of the shape of the first
  leaking record), `test_validate.py` (the minor rule), `test_pii_guard.py` (the age
  scan). Checked live: a real child's / live-blog record was reduced AND quarantined, and
  never published.

## C. Accused names only from court records (PR #15)

- Records from the media carry `name_public_court_record: null`. Names are only added
  from official court sources, in `dedupe.merge_records`. As a fixed backstop that
  doesn't depend on the model, `validate.withhold_unsourced_accused_names` blanks any
  accused name on a record that has NEITHER a court name NOR a case reference (CNR/FIR),
  so a bare index entry or news item can never publish a name.
- **Evidence:** the first record that could have published (from the media) had
  `accused: null`; `test_validate.py::test_withhold_unsourced_accused_names`;
  `test_dedupe.py::test_merge_unions_sources_and_remaps_status_history`.

## D. Matching on the case, never the person

- Matches on CNR, FIR with year, police station, district, date and court, never on
  anything about the victim. **Evidence:** `test_dedupe.py` (exact, strong, weak and
  close matches, FIR year).

## E. Low confidence goes to quarantine

- Records with `confidence < 0.8` go to `data/_review` and are never published.
  **Evidence:** `test_dedupe.py::test_low_confidence_goes_to_review`; checked live.

## F. Where a source came from (issue #7, PR #8 / #11)

- Each source is labelled `court | news_article | live_blog | press_release`. A record
  whose only source is a rolling live blog is capped at `confidence 0.79` and quarantined
  automatically. A page that keeps changing and whose URL decays isn't solid enough for a
  permanent public claim.
- **Evidence:** `test_provenance.py`, `test_gemini.py`; checked live: a real live-blog
  case (source_type=live_blog, confidence 0.79) was quarantined.

## G. Turning away cases that aren't sexual offences (PR #10)

- This record covers **sexual offences only**. Two separate layers: (a) the extractor
  returns a required `in_scope` yes/no and drops other cases before the sanitizer
  (counted as `rejected_out_of_scope`); (b) `dedupe` quarantines (`scope_review`) any
  record whose `offence_sections` cite no qualifying BNS 63–79 / POCSO / IPC
  354, 375–377, 509 section.
- **Evidence:** a cheque-bounce case (`NI Act 138`) is turned away by BOTH layers on their
  own (`test_gemini.py::test_extract_rejects_out_of_scope_offence`,
  `test_dedupe.py::test_out_of_scope_offence_is_quarantined`); the run stats report
  `rejected_out_of_scope` in `run.log` / `run_report.md` / `run_summary.env`.

## H. Staying up when the provider struggles (PRs #3, #5, #6)

- A fixed list of models to fall back on, a time limit on each call and a circuit
  breaker, and a hard 40-minute budget so a run always finishes inside its 60-minute job.
  **Evidence:** every recent staged run finished (it trims gracefully when the provider is
  struggling, and the job is never killed); `test_gemini.py`.

## I. How staging worked

- Each run committed `data/` to `data-staging` and opened or updated a review PR to
  `main`. Auto-publishing was skipped unless `LAUNCH_MODE=auto`. `data/_review` is in
  `.gitignore` (unreviewed data is never committed); quarantined records travel with the
  run's logs instead. Nothing reached the live site without a human merge.
- **Evidence:** review PR #4; `scrape.yml`.

## J. Which court sources we could reach (PR #11, #15)

- Searching eCourts directly is **behind a CAPTCHA, so it's out** (we never get around a
  CAPTCHA). It's only used through endpoints someone has found by hand. NJDG only has
  statistics. Indian Kanoon (a documented API that mirrors court records) was **fully
  connected**, with a cost budget per run and a rule that a judgment's *docsource* (the
  court) counts as a court record while a news item indexed on Indian Kanoon still counts
  as media. It was **switched off** until I had a token and had decided on their terms.
  Accused names publish only with a court name **and** a case reference
  (`validate.withhold_unsourced_accused_names`). News intake moved to the Delhi and
  Telangana crime and city feeds. **Evidence:** `sources.yml`, `test_indiankanoon.py`,
  `test_provenance.py`, `test_validate.py`.

## K. Not losing ground when the provider struggles (PR #13)

- A committed processed-document ledger with no personal data
  (`data/_meta/processed.json`, keyed by `sha256(url)`) lets a cut-short run skip
  documents it has already settled, so the next 40-minute budget goes to the rest. Delay,
  not loss. Only final outcomes (`published`/`out_of_scope`/`not_a_case`) count as
  settled; a quarantined or filtered-out document is never settled and comes back next
  run. Documents that keep failing are retried for 3 runs, then parked as
  `failed_permanent` with the URL logged for review.
- **Kept on its own unprotected `ledger-state` branch** (loaded before each run, saved
  after), so it works however long PRs take to merge, without touching protected `main`
  (`github-actions[bot]` can't be given a ruleset bypass; GitHub returns 422). Protected
  three separate ways: (a) validated against `schemas/ledger.schema.json` (sha256 keys,
  a fixed list of outcomes, ISO dates, `additionalProperties: false`) plus a scan for
  URLs; (b) `pii_guard` over `data/_meta/`; (c) the Contents API writes exactly one path.
  A case outside the scope is settled as `out_of_window` (final, for coverage);
  quarantined documents never settle. Provider errors are recorded each run
  (`error_samples`) so it's clear why a run stopped (429 RESOURCE_EXHAUSTED or 503
  UNAVAILABLE).
- **Evidence:** `test_ledger.py`, `test_orchestrator.py` (settled documents skipped,
  quarantined ones coming back), `test_validate.py::test_validate_ledger_*`. A review by
  14 adversarial agents caught and fixed three serious ways of losing data in the first
  version.

---

## L. Checking each case against its source before it publishes (issue #41, PRs #42 / #43 / #44)

This is what lets records publish WITHOUT a person reading each one first, while keeping
every privacy rule intact. At launch, a second, stronger model (`gemini-2.5-pro` with
Google Search grounding, set in config) re-checked each in-scope case against its cited
source BEFORE publishing and marked it `verified`.

- **What the check may do:** (a) confirm the source text supports every field;
  (b) re-check scope (a real, specific reported sexual-offence case, not commentary, a
  trend piece or an editorial); (c) run one search and attach a second source that backs
  it up; (d) return `verified` and a one-sentence `verification_note`, or turn the case
  down (`verified:false`). It may only correct a small set of FACTUAL fields
  (`CORRECTABLE_FIELDS` in `pipeline/verify.py`).
- **What it can NEVER do** (the fixed rules always win): it can't touch `minor_involved`,
  `accused`, `id`, a source URL, or a child's fixed `title`/`summary`. If it thinks
  `minor_involved` is wrong, it must turn the case down, not change the flag. A child's
  case text is never written by a model; the check only decides whether the *reduced*
  record can publish, never what it says.
- **Publishing rules when the check is on (`VERIFY_ENABLED=true`):**
  - A NEW record must be `verified:true` to publish. Otherwise it goes to `data/_review/`
    with the check's note, never onto the site.
  - A verified record still goes through the full last gate and the graded publishing
    gate, **except** the `minor_involved` rule: a verified **child's** case DOES publish
    (its title and summary are fixed and identify no one, as Section 23 of POCSO
    requires), but a **named accused (from a court)** still goes to me for review (because
    of defamation), and so do `pocso_minor_mismatch`, live-blog-only and low confidence.
  - Every published record goes through `coerce_minor`, then sanitize and reduce, then
    withhold-unsourced-names again, so if a merge flips `minor_involved` after the
    per-case sanitize, the record is reduced to the minimal form before it reaches either
    a data file **or** `data/recent.json`.
  - **Records already live stay live:** turning on the check never unpublishes a record
    that's already on the site, even if its source has dropped off the feed and it can't
    be checked again this run (so records aren't lost). Only genuinely new cases face the
    check.
  - **Held records are never lost:** the check only runs on new cases, so a held record
    carried over from before can never become `verified`. It stays HELD in the review
    queue and is never swept into `_review`; only a *brand-new* case the check turns down
    is quarantined. My approvals work with the check on exactly as they did in the
    supervised phase.
- **Reviewed adversarially from three angles** (personal-data leaks, losing records, the
  check's own logic), which found and fixed: a child's model-written `verification_note`
  reaching the data file without being scanned (now removed; the proper fix was tracked in
  issue #44); turning on the check sweeping the whole held queue into `_review`
  (permanent loss); approval logic that had stopped working with the check on; `verified`
  being lost when records merged; the second source's empty date quarantining verified
  records; `verified` being read as true from any non-empty value; no limit on cost per
  call; and second-source URLs that weren't http. All have regression tests.
- **A decision I hadn't made yet: should unattended publishing need a second source?**
  The check was designed to attach a second source from its search. At launch, a *single
  source* new verified record still auto-published ("verified plus the gates means
  publish"). A stronger defence against made-up or manipulated cases would HOLD any new
  verified record with fewer than 2 independent sources for review (nothing is lost; it
  just waits). That trades away auto-publishing (none at all when search isn't available)
  for stronger backing. It wasn't enforced yet, and I meant to decide before switching to
  `auto`. The source text is already marked as untrusted data in the check's prompt, and
  second-source URLs that aren't http are rejected when they come in.
- **Something to be aware of: `verified` carries across a merge.** A case counts as
  verified if ANY copy in its group was verified (so a new verified copy isn't lost because
  another copy hit the budget or had no source). One harmless corner: a record verified
  earlier and HELD *only* because it was `live_blog_only` can pick up a lasting source from
  a new copy the check turned down this run, merge to `verified:True` with nothing left
  holding it, and auto-publish, even though its latest verdict was "not verified." It
  leaks nothing (the published form is reduced again and unsourced names are withheld) and
  loses or duplicates nothing. It's a policy detail, not a broken rule. A follow-up review
  confirmed the record-loss fixes didn't add any new loss, duplication or leak.
- **Failing safe, and cost:** every error (an answer it can't read, a provider error,
  missing source text, budget used up) leaves a record `verified:false` (quarantined).
  It only runs on in-scope cases (a handful a day) under a hard cap per run
  (`VERIFY_MAX_USD`, default $0.50); a case not checked within budget stays quarantined.
  The daily heartbeat has a `verify` line (verified / turned down / estimated $).
- **Evidence:** `test_verify.py` (reading answers, applying them, budget, errors, no
  source), `test_orchestrator.py` (a verified child's case publishes, an unverified one is
  quarantined, a named accused is held, a record already live stays live when the check
  is turned on, a POCSO case marked adult is safely treated as a child's case and
  reduced). Reviewed adversarially from the same three angles before merging.

## M. The weekly refresh only updates status, never rewrites a summary

The weekly `refresh` run (court sources only, `--mode refresh`) exists to move an
existing record's court status forward, not to find new cases or rewrite text. Two things
are now **tested against a fixture**, each guarded separately:

- **A status change is recorded once, in both date fields.** When a court source reports
  that an existing record's status has really moved on, `shard._record_status_transition`
  adds exactly one `status_history` point (adding the previous status as the starting
  point if the history was empty) and sets `last_status_change` to the run date. Seeing
  the same status again adds nothing (the entry just carries forward). A change that
  isn't about status (a corrected section) only updates the date. `first_published` is
  written once and never changes. Before this, a status change updated the `status`
  field but left `status_history` empty, so the timeline never showed when justice moved.
- **The reviewed summary stays as it is.** `_preserve_refresh_narrative` puts back each
  refreshed **adult's** `title`/`summary` as it already appears on the site, so a new
  court **judgment**'s model-written text can never replace the reviewed summary
  (`dedupe._order` makes the court copy the main one, which would otherwise win the
  merge). This puts into code the rule that a judgment is a *source* full of personal
  detail, not text to republish. A genuinely new summary belongs to the daily `discover`
  run and its review. Children's summaries are fixed wording that gets rebuilt (never
  model text), so they're left alone.
- **Refresh never creates a record.** A new case that a court source turns up during a
  refresh is dropped (finding cases is the daily run's job).
- **Evidence:** `test_orchestrator.py::test_refresh_status_change_is_status_only_never_narrative`
  (one addition, one date change, no rewrite, no new record; shown to FAIL if either guard
  is removed), `::test_refresh_mode_never_creates_a_new_record`, `test_shard.py`.

## N. A monthly cap on Gemini spending

A running cap per calendar month (`config.monthly_max_usd`, env `MONTHLY_MAX_USD`,
default $10) limits spending across every run in a month, on top of the existing token
cap per run. The month-to-date total is kept in `data/_meta/spend.json` on the
`ledger-state` branch (dollar totals only, with no room for case content or personal
data). If a run starts and the month is already at the cap, it makes **no new Gemini
calls** (it stops cleanly instead of extracting half the documents), still rebuilds the
existing records for free, says the budget is exhausted in the heartbeat, and opens an
issue. A new month starts the count again.

- **Evidence:** `test_spend.py` (adding up, monthly buckets, a corrupt file, totals only),
  `test_orchestrator.py::test_monthly_budget_exhausted_makes_no_paid_calls` (a client that
  blows up on any call shows zero paid calls are made at the cap) and
  `::test_monthly_budget_under_cap_runs_and_records_spend`.

---

## Staged-run evidence

_Two states (TG, DL), 30-day scope, `staged` mode. Every run finished inside its job time
(the time budget trims gracefully under provider load; the job was never killed)._

| run | sources | fetched | extracted | published | review | cost | note |
|---|---|---|---|---|---|---|---|
| `29099657465` | national RSS | 260 | 16 | 0 | 1 | $0.087 | trimmed; live blog quarantined |
| `29104649205` | crime/city RSS | 520 | 0 | 0 | 0 | $0.045 | trimmed; 1 out-of-scope case turned away |
| `29110062044` | crime/city RSS | 520 | 0 | 0 | 0 | $0.000 | **stopped** (quota / free tier, before the billing fix) |
| `29112065032` | crime/city RSS | 520 | 6 | 0 | 0 | $0.413 | **full coverage** (billing fixed); 0 in TG/DL in 30 days |

Fixing billing brought the key back: run `29112065032` processed the **whole** set of
520 documents (not trimmed, not stopped) at `serviceTier: standard`, and found 6 real
sexual-offence cases, **none in the TG/DL 30-day window**, so 0 published. Only 13 of the
520 calls hit brief `503`/`504` errors (recorded in `error_samples`), which the fallbacks
handled without stopping. That was **the first full-coverage empty run** towards the
launch target. **No court-sourced records**: eCourts is behind a CAPTCHA and Indian
Kanoon was switched off, so court records were waiting on a credential from me (see J).

---

## What I needed to decide before switching to `auto`

1. **Indian Kanoon**: accept the terms, provide `INDIANKANOON_API_TOKEN`, then turn on
   `indian-kanoon` in `sources.yml`. This is the main legitimate route to court records.
2. **eCourts endpoints**: provide official-API or hand-found DL and TG endpoints (or a
   High Court judgment listing that robots.txt allows). Searching directly stays off
   (CAPTCHA).
3. **Approving CI by hand: wired up (PR #14), waiting for the secret.** The scheduled job
   now pushes and opens the staged PR with `SCRAPE_BOT_TOKEN` (a fine-grained PAT or App
   token) so its checks run on their own. Until the secret is set it falls back to
   `GITHUB_TOKEN` (approving by hand, as at launch). Set it up as described in
   CONTRIBUTING.md, under "Running it day to day".
4. **A person reviewing every staged record** was still required. The plan was not to
   turn on the schedule or `LAUNCH_MODE=auto` until that review was signed off.

## The launch target (not met at the time)

Under the pre-launch plan, `auto` waited for either **at least 1 published**
court-sourced or news-article record in the TG/DL 30-day window, **or three
full-coverage runs in a row** (the ledger shows the whole fetched set settled) proving
the window really was empty. No run had yet reached full coverage with a healthy
provider; the ledger now lets runs spaced apart arrive at that answer.

## Sign-off

- [ ] Privacy rules (A–B) checked against the code and tests.
- [ ] Accused names, matching, confidence, sources and scope (C–G) checked.
- [ ] Staying up and staging (H–I) checked.
- [ ] Court-source plan (J), coverage ledger (K) and the decisions above accepted.
- [ ] Launch target met (at least 1 published, or 3 full-coverage empty runs).
- [ ] At least one full staged review PR checked record by record.

---

## What has changed since launch

These are later changes that are visible in the code today. The review above is left as
it was written.

- **Court records are connected.** Indian Kanoon is turned on in `sources.yml` (since
  12 August 2026), with searches for the Delhi, Telangana, Punjab & Haryana, Madhya
  Pradesh, Madras and Jharkhand High Courts. The judgment pages of the Delhi, J&K and
  Ladakh, and Meghalaya High Courts are read directly (`hc_judgments` sources in
  `sources.yml`).
- **Different models.** The gemini-2.5 models stopped being available to new keys
  (`pipeline/config.py`). Extraction now uses `gemini-3.5-flash`, falling back to
  `gemini-3.5-flash-lite` (`DEFAULT_GEMINI_MODELS` in `pipeline/config.py`, and
  `extraction.models` in `sources.yml`).
- **The verification check changed.** It now uses `gemini-3.5-flash` rather than
  `gemini-2.5-pro`, which was retired (`DEFAULT_VERIFY_MODEL` in `pipeline/config.py`).
  It also no longer uses Google Search grounding: answers with grounding weren't valid
  JSON, which turned down almost every case. It now judges each case against the source
  text it's given (`default_verify_client` in `pipeline/verify.py`). It can still
  attach a second source if it names one.
- **`auto` doesn't need an admin token.** In `auto` mode the scheduled job opens its own
  PR, re-runs the full `make check` on exactly that data, and only then marks the two
  required checks as passed and merges, without bypassing the ruleset. If anything fails,
  nothing publishes and the PR stays open (`.github/workflows/scrape.yml`).
- **Regional-language news.** Hindi, Telugu, Marathi and Tamil feeds are turned on in
  `sources.yml`. Bengali, Gujarati, Kannada and Malayalam feeds are set up but switched
  off.
- **Issue #29 is fixed.** The highest case number used for each year and state is kept in
  `data/_meta/serials.json`, so a case number is never reused (PR #145, and PR #254 made
  sure the file reaches `main`).
