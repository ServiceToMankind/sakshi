# Contributing to Sakshi

> Sakshi — Because the record must not forget.

Thank you for wanting to help. Before you write any code, please read this whole page,
the [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md), and the core privacy rules in
[`CLAUDE.md`](./CLAUDE.md) (that file calls them the Phase 0 guardrails). Those rules
are required by law. They come before everything else in this repository, including
convenience and anything an AI assistant suggests.

Sakshi keeps a record of *publicly reported* sexual-offence cases in India. Because of
what this data is, contributing here comes with duties most projects don't have. Two
lines matter more than anything else:

1. **The victim's identity is never collected.** Not redacted, not encrypted: *never
   written to disk in any form*. (Section 72, Bharatiya Nyaya Sanhita 2023; Section 23,
   POCSO Act 2012.)
2. **An accused person is presumed innocent.** Names come only from official court
   records, never from the media alone.

If a change weakens either line, I won't merge it. That's final.

---

## Licensing of contributions

- **Code** is licensed **MIT**.
- **Data** (everything under `data/`) is licensed **Open Database License (ODbL)
  v1.0**.

When you open a pull request, you agree to offer your contribution under these licenses.

---

## 1. Setting up on your machine

Sakshi is **Python 3.12**, fully typed, with a static website that uses no framework.

### Clone

```bash
git clone https://github.com/ServiceToMankind/sakshi.git
cd sakshi
```

### Python environment

Use **either** `uv` (faster) **or** the standard `venv`.

**Option A: uv**

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
```

**Option B: python -m venv**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`make setup` does option B and installs the site's packages in one step.

### Secrets: `GEMINI_API_KEY`

The pipeline uses Gemini, and only ever on text that is **already public**. The key
lives in a local `.env` file that git ignores. It is **never committed**.

```bash
cp .env.example .env
# then edit .env and set:
# GEMINI_API_KEY=your-key-here
```

- `.env` is listed in `.gitignore`. Please don't remove it from there.
- Never paste a real key into code, tests, issues, PRs or commit messages.
- If you ever commit a key by accident, treat it as stolen: replace it straight away and
  tell a maintainer. `make check` runs `scripts/secret_guard.py`, which fails if a key
  shows up in any tracked file.

### The website

The site is Vite and plain JavaScript. No React, no Vue, and no chart library: the
charts are hand-drawn SVG in `site/src/charts.js`, and the site has no runtime
dependencies at all.

```bash
cd site
npm install
npm run dev
```

### Run the checks

```bash
make check
```

`make check` runs `ruff`, `mypy --strict`, `pytest` (at least 85% coverage of the
pipeline, and **100% on `sanitize.py` and `pii_guard.py`**), schema validation of every
data file, the `summary.json` size limit, `pii_guard`, the readability check
(`scripts/readability_guard.py`), the key scan (`scripts/secret_guard.py`), the count
check (`scripts/counts_guard.py`), `eslint` and `prettier`. Lighthouse runs on the built
site through `make lighthouse` and in the deploy pipeline. CI runs all of this on every
pull request.

---

## Running it day to day: secrets and the scheduled job

The scheduled job (`.github/workflows/scrape.yml`) reads these **repository secrets**.
Each one is optional; the job carries on safely without it.

| Secret | What it's for | What it may access | Who holds it | Expiry |
|---|---|---|---|---|
| `GEMINI_API_KEY` | Extraction (Gemini over already-public text). | The Gemini API only. | Maintainers (org). | Replace if you suspect a leak; no fixed expiry. |
| `SCRAPE_BOT_TOKEN` | Pushes `data-staging` and opens or updates the data PR **as a real account**, so the PR's checks run on their own. | A fine-grained PAT (or GitHub App token) with **Contents: read/write** and **Pull requests: read/write** on this repo only. Nothing else. | A maintainer or a dedicated `sakshi-bot` account. | 90 days or less; renew before it expires and update the secret. |
| `INDIANKANOON_API_TOKEN` | Turns on the Indian Kanoon court-record source. | The Indian Kanoon API only (paid; accept their terms first). | The maintainer who accepted the terms. | Set by Indian Kanoon; replace if you suspect a leak. |

**Why `SCRAPE_BOT_TOKEN` exists.** A push made with GitHub's built-in `GITHUB_TOKEN`
can't start another workflow (GitHub blocks that to stop loops). Without a real-account
token, the data PR's checks sit at *"Action required"* and someone has to approve them
by hand on every run. With the token set, they run on their own. Until it is set, the
workflow falls back to `GITHUB_TOKEN` and a maintainer approves the checks manually.

**How to tell the `SCRAPE_BOT_TOKEN` has expired.** The data PR is opened by
`github-actions[bot]` instead of the bot account. Its required checks never run (they sit
at *"Action required"*), and the PR shows **`mergeable: MERGEABLE`, state `BLOCKED`**. It
can't merge because the required checks are missing, so `main` stops getting new data and
the site says it was *"last generated over 48 hours ago"*. **To fix it:** create a new
fine-grained PAT (Contents and Pull requests, read/write, this repo only), update the
`SCRAPE_BOT_TOKEN` secret, and run the job again. As a one-off, a maintainer may run
`gh pr merge <n> --admin`, but only **after** checking the staged data locally
(`scripts/pii_guard.py` and schema validation) and noting the admin merge in the PR.

The daily heartbeat (below) shows the token's expiry date, and in its last week the job
opens an issue titled "Bot token expiring" so it doesn't catch anyone by surprise.

**How data PRs get merged.** The repository variable `LAUNCH_MODE` decides this:

- `staged` (the default): each run pushes to `data-staging` and opens or updates a PR to
  `main`. Nothing is published until a person reviews and merges it.
- `auto`: the run opens the same PR, then re-runs the full `make check` on exactly that
  data inside the job. Only if every check passes does it mark the PR's two required
  checks as passed and merge it, then start the deploy. If anything fails, nothing is
  published and the PR stays open for a person.

An admin merge that skips the required checks is for emergencies only, and every use
must be noted in the PR.

### The processed-document ledger (the `ledger-state` branch)

`data/_meta/processed.json` is the processed-document ledger. It is **bookkeeping
only**: a `sha256(url)` for each document, what happened to it, and dates. It never
holds a URL and never holds personal data. It lives on its own **unprotected**
`ledger-state` branch so the pipeline remembers what it has already handled from one run
to the next, however long the data PRs take to merge. `main` is never touched:
`github-actions[bot]` can't be given a way around `main`'s protection (GitHub refuses to
add the built-in Actions app to a ruleset bypass, with an HTTP 422), and a separate,
unprotected branch avoids needing one.

- Each run **loads** the ledger from `ledger-state` before extraction and **saves** it
  back afterwards, both through the GitHub Contents API. `github-actions[bot]` /
  `GITHUB_TOKEN` is enough for that; no bypass needed.
- `ledger-state` is **never merged**. It is a storage branch, not code. Please don't open
  PRs from it. The data PR leaves out `data/_meta`, except the case-number counter
  `data/_meta/serials.json`, which has to reach `main` so an old case number is never
  given to a new case.
- **Three checks run before every save:** (a) the ledger is validated against
  `schemas/ledger.schema.json` (`sha256` keys, a fixed list of outcomes, ISO dates,
  `additionalProperties: false`) and scanned for anything that looks like a URL;
  (b) `pii_guard` runs over `data/_meta/`; (c) the Contents API call writes exactly one
  path, so it can't touch anything except `data/_meta/processed.json`.
- **Widening the window starts coverage over.** A sexual-offence case outside the current
  `LAUNCH_STATES` / `LAUNCH_LOOKBACK_DAYS` is marked `out_of_window` and skipped from then
  on under that window. If you later widen the states or the lookback, **delete the
  `ledger-state` branch** so those documents are looked at again.

### Run modes, the monthly spending cap, and corrections

- **`discover` and `refresh` (`--mode`, `PIPELINE_MODE`).** The daily run (06:00 IST) is
  `discover`: it reads every enabled source and may add new records. The weekly run
  (Sunday, 07:00 IST) is `refresh`: it reads **court sources only** and only **updates**.
  It moves an existing record's status forward (adding one point to `status_history` and
  updating `last_status_change`), but it **never creates a record and never rewrites the
  reviewed summary of an adult's case**. A court judgment is a source full of personal
  detail, not text to republish; a new summary belongs to `discover` and its review.
- **Monthly Gemini spending cap (`MONTHLY_MAX_USD`, default $10).** The month's total
  spend is tracked in `data/_meta/spend.json` (dollar totals only, never case content)
  and saved on the `ledger-state` branch like the document ledger. If a run starts and
  the month is already at the cap, it makes **no new Gemini calls** (it stops cleanly
  rather than doing half a run), still rebuilds the existing records, shows the
  month-to-date figure in the heartbeat, and opens an issue. The count starts again each
  month. The pipeline reads the cap from the `MONTHLY_MAX_USD` environment variable, but
  `scrape.yml` doesn't pass a repository variable through to it yet. So for now, raising
  the cap for the daily job means changing `DEFAULT_MONTHLY_MAX_USD` in
  `pipeline/config.py`, or adding `MONTHLY_MAX_USD` to the job's `env:` block.
- **Corrections (`corrections/<record-id>.yml`).** This is the only approved way for a
  person to change a published record. Never by editing `data/` by hand. A correction can
  `quarantine` a record (take it off the site and into review) or `override` specific
  fields. Overrides are applied before the sanitizer, so they still go through every
  check, and they can never set a victim field, the `id`, or `minor_involved`. See
  [`TAKEDOWN.md`](./TAKEDOWN.md) and [`corrections/README.md`](./corrections/README.md).
  Adding a correction is a **data change** and goes through a reviewed PR.

### Checking on the daily run

Every run of the scheduled job posts one **heartbeat** comment on the pinned ops-log
issue (its number is in the `OPS_ISSUE` repository variable). It does this for scheduled
and manual runs, whether or not anything was found.

- **Read the heartbeat every day.** It shows the date, a link to the run, document counts
  (fetched, processed, skipped because already settled, and the ledger totals), extraction
  counts (extracted, in scope, published, held, quarantined, out of scope), cost,
  month-to-date spend, the size of the held queue, any court source that returned errors,
  the bot token's expiry, and a status (`ok`, `truncated`, `aborted`, `RUN FAILED`) with
  sample provider errors. It holds no personal data, just counts and a link.
- **A scheduled day with no comment is itself the warning**: it means the run didn't
  start.
- **Look at the data PR whenever there is one.** What to do on an empty day, when a
  record is ready to publish, when a check fails, or when the provider stops a run, is
  written in that pinned issue.

The job also opens an issue on its own when a run fails or is cancelled, when a court
source returns errors, when the monthly budget runs out, or when more than 20 records
land in `data/_review/` in one run.

---

## 2. How data moves through Sakshi

Data flows one way, from public sources to the published files. Every record can be
traced to a public source you can cite, and **personal data is stripped before anything
touches disk**. Nobody edits `data/` by hand; the whole tree is rebuilt the same way on
every run.

```
   PUBLIC SOURCES                                            PUBLISHED (GitHub Pages)
   court records first, media second                         read-only, rebuilt each run
 ┌──────────────────────────────┐                          ┌──────────────────────────────┐
 │ Indian Kanoon (paid API)     │                          │ data/summary.json (<50 KB)   │
 │ High Court judgment pages    │                          │ data/index.json   (file list)│
 │ eCourts (hand-found links)   │                          │ data/recent.json, and others │
 │ RSS of established media     │                          │ data/{YYYY}/{STATE}.json     │
 │ case-submission issues       │                          └──────────────────────────────┘
 └──────────────┬───────────────┘                                         ▲
                │                                                         │
                ▼                                                         │
  ┌───────────────────────┐   reads robots.txt, honest User-Agent,        │
  │ FETCH                 │   1 request / 2s per site, ETag cache,        │
  │ pipeline/sources/*    │   backs off on 429 and 5xx errors             │
  │ Source.fetch()        │                                               │
  │  -> [RawDocument]     │                                               │
  └──────────┬────────────┘                                               │
             │  RawDocument(url, publisher, fetched_at, text)             │
             ▼                                                            │
  ┌───────────────────────┐   Gemini fills a fixed form; victim is        │
  │ EXTRACT               │   ALWAYS null by design; a confidence         │
  │ extract/gemini.py     │   score is required                           │
  └──────────┬────────────┘                                               │
             │  extraction.schema.json (has no room for personal data)    │
             ▼                                                            │
  ┌───────────────────────┐   a second Gemini check against the source    │
  │ VERIFY                │   (when VERIFY_ENABLED is on); approves,      │
  │ verify.py             │   fixes a few facts, or turns a case away     │
  └──────────┬────────────┘                                               │
             ▼                                                            │
  ┌───────────────────────┐   *** LAST GATE BEFORE DISK ***               │
  │ SANITIZE              │   drops forbidden fields, regex-redacts       │
  │ sanitize.py           │   personal data in EVERY text field;          │
  │                       │   100% branch coverage                        │
  └──────────┬────────────┘                                               │
             ▼                                                            │
  ┌───────────────────────┐   exact on CNR/FIR; close match on            │
  │ DEDUPE                │   district/date ±3 days/charges/court;        │
  │ dedupe.py             │   court beats media, furthest status wins;    │
  └──────────┬────────────┘   unsure -> data/_review/                     │
             ▼                                                            │
  ┌───────────────────────┐   schema check on every record, IDs,          │
  │ VALIDATE & SHARD      │   write to temp file -> check -> rename;      │
  │                       │   pii_guard as the FINAL check ──────────────►│
  └──────────┬────────────┘                                            (write)
             ▼
  ┌───────────────────────┐   confidence < 0.8  OR  unsure match
  │ data/_review/         │   -> held back, not committed, not on
  │ (for a person to see) │      the site, never published on its own
  └───────────────────────┘

  COMMIT: the job commits data/ ("data: daily update YYYY-MM-DD (+N new, ~M updated)"),
          and opens an issue if a run fails or more than 20 records need review.
```

Two things to take away from this:

- **`sanitize.py` is the last gate before disk.** Nothing reaches `data/` without going
  through it. `pii_guard` then checks everything again at the end.
- **`data/_review/` is where anything uncertain stops** (confidence below 0.8, or an
  unclear match). It's never on the site, and only a person moves a record out of it.

The sanitizer works by fixed rules and regular expressions. It doesn't use a
name-recognition (NER) model. On top of dropping forbidden fields and redacting Aadhaar,
phone, email and PAN patterns, it removes any non-English script, clears victim
occupations and certain romanised Indian-language words (family terms, village office
titles, words for a place smaller than a district) out of titles and summaries, and
rewrites a child's case into a fixed minimal form.

---

## 3. Adding a new source

Sources live in **`pipeline/sources/`**. Official, structured sources come first. Media
means RSS feeds of established outlets only. **No social-media scraping.**

### What a source has to do

A source is a class with one method:

```python
async def fetch(self) -> list[RawDocument]: ...
```

`RawDocument` (in `pipeline/sources/base.py`) holds exactly four things: `url`,
`publisher`, `fetched_at` and `text`. A source's only job is to return well-formed
`RawDocument`s from a public source. It does **not** pull out fields, classify, dedupe or
write to disk. Later steps handle all of that.

### Skeleton

```python
# pipeline/sources/example_highcourt.py
from pipeline.sources.base import RawDocument
from pipeline.sources.http import HttpGetter


class ExampleHighCourtSource:
    """Fetches public cause lists from the Example High Court portal."""

    def __init__(self, client: HttpGetter) -> None:
        self._client = client  # the shared polite client; never make your own

    async def fetch(self) -> list[RawDocument]:
        docs: list[RawDocument] = []
        # ... polite calls through self._client here ...
        return docs
```

### Rules every source must follow

- **Respect `robots.txt`.** Don't fetch paths it disallows.
- **Use an honest User-Agent** that names the project and links the repo.
- **At most 1 request every 2 seconds per site.** Use the shared polite client in
  `pipeline/sources/http.py` (`PoliteClient`). Don't write your own faster path.
- **Cache** with ETag / Last-Modified when the site supports it.
- **Back off** more and more on `429` and `5xx` errors.
- **Public data only.** If it needs a login, gets around a paywall, or is something a
  member of the public couldn't lawfully read, it's out. Never get around a CAPTCHA.
- **Follow the source's terms** (for example, Indian Kanoon through its API and terms).
- Add tests with **obviously fake** fixtures (`"district": "TESTVILLE"`). Never commit a
  real case record, not even as a fixture.

Hook your source up in `pipeline/sources/registry.py` (`build_sources`), add an entry
under the right state (or `national:`) in `sources.yml`, and in your PR write a short
note about the source, its terms of access, and why it qualifies.

---

## 4. Commit messages

We use **[Conventional Commits](https://www.conventionalcommits.org/)**.

Format: `type(optional-scope): summary`

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `perf`.

**Examples**

```
feat(sources): add Telangana High Court cause-list source
fix(sanitize): strip Aadhaar values split across whitespace
docs(contributing): clarify data-lifecycle diagram
test(pii_guard): cover PAN regex boundary cases
chore(deps): bump rapidfuzz to 3.9
```

### Don't add a Claude or AI co-author line

**Org policy:** never add a `Co-Authored-By: Claude` line (or any AI co-author line) to a
commit, and never put one in documentation or commit-message examples. If your tools add
one automatically, remove it before you push. This holds even when an AI assistant wrote
most of the change.

---

## 5. Pull request checklist

Before you ask for a review, please check **every** item:

- [ ] `make check` passes locally.
- [ ] Tests pass and coverage holds (85% or more on the pipeline; **100% on `sanitize.py`
      and `pii_guard.py`**).
- [ ] Types are clean under **`mypy --strict`**.
- [ ] **`pii_guard` passes.**
- [ ] **Nothing under `data/` was edited by hand.** The pipeline writes that tree; if
      your change affects data, it has to come through the pipeline.
- [ ] `additionalProperties: false` is still `false` at **every** level of every schema.
- [ ] **`sanitize.py`, `pii_guard.py` and the forbidden-field list are unchanged**, unless
      a specific, human-approved issue allows the change (link it in the PR).
- [ ] Any new fixtures are obviously fake and contain **no personal data** and no real
      case data.
- [ ] No secrets, keys or `.env` contents are committed.
- [ ] No Claude/AI co-author line on any commit.
- [ ] Commits follow Conventional Commits.

If a PR touches one of the protected files without a linked, approved issue, I'll close
it and ask you to open that issue first. It isn't personal. It's how we keep every change
to these rules on the record.

---

## 6. How quickly you'll hear back

I want you to know what to expect, so nobody is left waiting.

| Change type | First maintainer response |
| --- | --- |
| Touches a protected file (`sanitize.py`, `pii_guard.py`, the forbidden list, schemas) | within **2 business days**, reviewed by a maintainer who did **not** write the change |
| New source | within **3 business days** |
| Website, docs or tooling | within **5 business days** |
| Security or personal-data concern | **same day**, see below |

**Security and personal-data concerns.** If you think personal data has been published,
or could be, please **don't** open a public PR describing the leak. Contact a maintainer
privately (see `SECURITY.md`) so it can be handled right away. A suspected published
victim identity is a same-day, drop-everything problem.

Corrections and takedown requests are handled as described in
[`TAKEDOWN.md`](./TAKEDOWN.md), including removal on request for acquitted or quashed
cases.

---

## 7. New here and using an AI assistant?

Welcome. Please read this part carefully. It's here so that AI-assisted changes fit the
rest of the code instead of being quietly wrong.

### What Sakshi actually is

Sakshi is a **fully static** website backed by **JSON files in git**. There is no live
server, no database and no user accounts. Once a day, a program reads public court
records and reputable news, pulls out a few neutral facts about each *publicly reported*
case, strips anything that could identify a victim, removes duplicates, checks the
result, and writes plain JSON into `data/`. GitHub Pages serves that JSON, and your
browser draws the charts and tables from it.

So there are really two halves:

```
   ┌───────────────────────────────┐        ┌──────────────────────────────┐
   │  THE PIPELINE (Python)        │        │  THE SITE (static frontend)  │
   │  pipeline/ , extract/ ,       │  ───►  │  site/ : Vite + plain JS     │
   │  sanitize.py , pii_guard.py   │  data/ │  reads data/*.json only      │
   │  runs on a schedule / CI      │  JSON  │  no framework, no backend    │
   └───────────────────────────────┘        └──────────────────────────────┘
        writes data/  (machine only)              reads data/  (never writes)
                    │                                      ▲
                    └──────────  data/  (JSON in git) ─────┘
              summary.json  ·  index.json  ·  {YYYY}/{STATE}.json
```

`data/` is the agreement between the two halves. The pipeline is the **only** thing that
writes it. The site only **reads** it. If you ever feel the urge to edit `data/` by
hand, stop: it means you're fixing the problem in the wrong place.

### Where things live

- `pipeline/sources/`: one module per public source, each with
  `fetch() -> list[RawDocument]`.
- `pipeline/extract/gemini.py`: turns public text into structured fields in a fixed form
  (the victim is always `null`).
- `pipeline/sanitize.py`: the last personal-data gate before disk. **Protected file.**
- `scripts/pii_guard.py`: the final check that no personal data slipped through.
  **Protected file.**
- `schemas/case.schema.json`: the one true shape of a record.
- `schemas/extraction.schema.json`: the form Gemini fills in, which has no place to put
  victim data.
- `data/`: machine-written JSON. Don't edit it by hand.
- `site/`: the static website.

### Things AI assistants get wrong here

AI assistants learned from ordinary web projects. They will confidently suggest things
that are right elsewhere and **wrong here**. Watch for all of these and say no:

1. **Editing `data/` by hand.** Assistants love to "just fix the JSON." Never. The
   pipeline rebuilds `data/` every run, so a hand edit gets overwritten, and worse, it
   skips validation and the personal-data checks. Fix the pipeline instead.
2. **Personal data in fixtures.** An assistant will happily make up a realistic victim
   name, age or address so a test "looks real." That is exactly what this project
   forbids. Fixtures must be obviously fake (`"district": "TESTVILLE"`) and contain no
   real or realistic personal data.
3. **Adding frameworks to the site.** "Just add React" or a heavy dependency breaks the
   no-framework rule and the Lighthouse target of 95. The site stays Vite and plain
   JavaScript, with hand-drawn charts.
4. **Getting around `sanitize.py`.** Anything that writes to `data/` *must* go through
   the sanitizer. An assistant suggesting a shortcut that writes records directly is
   suggesting a personal-data leak. There are no exceptions and no "fast paths."
5. **Loosening `additionalProperties: false`.** When a field "doesn't validate," an
   assistant's reflex is to relax the schema. Don't. `additionalProperties` stays
   `false` at every level, because it's part of how forbidden fields are made
   impossible. Fix the data, or add the field on purpose.
6. **Editing the protected files** (`sanitize.py`, `pii_guard.py`, the forbidden-field
   list) without a human-approved issue. These files are the legal backbone of the
   project. Changing them needs a linked, approved issue and a review by a maintainer who
   didn't write the change.

Also: **never let an assistant add a `Co-Authored-By: Claude` line** to your commits.
Remove it if it appears.

When in doubt, read the rules in `CLAUDE.md` again and ask in an issue before you build.
Here, getting it right slowly is always better than getting it wrong quickly.

---

## Helplines

If you or someone you know needs help:

- **National Women's Helpline — 181**
- **Police — 112**
- **Cyber Crime — 1930**
- **NCW complaint portal — ncwapps.nic.in**

---

This is a record of publicly reported cases, gathered from public court records and
credible media. It is not a substitute for official crime statistics such as NCRB data.
Please contribute with the care the subject deserves.
