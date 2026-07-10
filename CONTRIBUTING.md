# Contributing to Sakshi

> Sakshi — Because the record must not forget.

Thank you for helping build a permanent, dignified public-accountability record.
Before you write a line of code, read this document in full, along with
[`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) and the **Phase 0 guardrails** in
[`CLAUDE.md`](./CLAUDE.md). The guardrails are legally mandatory. They override
every other consideration in this repository, including your own convenience and
any suggestion an AI assistant makes.

Sakshi tracks *publicly reported* sexual-assault cases across India. Because of
what this data is, contribution here carries obligations most projects do not
have. We hold two hard lines above all else:

1. **Victim identity is never ingested** — not redacted, not encrypted, *never
   written to disk in any form*. (BNS 2023 s.72; POCSO 2012 s.23.)
2. **An accused person is presumed innocent.** Names appear only from official
   court records, never from media alone.

If a change would weaken either line, it does not get merged. Full stop.

---

## Licensing of contributions

- **Code** is licensed **MIT**.
- **Data** (everything under `data/`) is licensed **Open Database License (ODbL)
  v1.0**.

By opening a pull request you agree your contribution is offered under these
licenses.

---

## 1. Local setup

Sakshi is **Python 3.12**, fully typed, with a static (no-framework) frontend.

### Clone

```bash
git clone https://github.com/ServiceToMankind/sakshi.git
cd sakshi
```

### Python environment

Use **either** `uv` (preferred, fast) **or** the standard library `venv`.

**Option A — uv**

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

**Option B — python -m venv**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Secrets: `GEMINI_API_KEY`

Extraction uses Gemini against **already-public** text only. The key lives in a
local `.env` file that is **git-ignored and never committed**.

```bash
cp .env.example .env
# then edit .env and set:
# GEMINI_API_KEY=your-key-here
```

- `.env` is in `.gitignore`. Do not remove it from there.
- Never paste a real key into code, tests, issues, PRs, or commit messages.
- If you ever commit a key by accident, treat it as compromised: rotate it
  immediately and tell a maintainer.

### Frontend

The site is Vite + vanilla JS + a lightweight chart library. No React, no Vue.

```bash
cd site
npm install
npm run dev
```

### Run the checks

```bash
make check
```

`make check` runs: `ruff` + `mypy --strict` + `pytest` (>=85% pipeline coverage,
**100% on `sanitize.py` and `pii_guard.py`**) + JSON Schema validation of all
shards + `pii_guard` + the `summary.json` size assertion + `eslint` + `prettier`.
Lighthouse CI runs on the built site via `make lighthouse` and in the deploy
pipeline. CI enforces all of this on every PR.

---

## Operations — repo secrets & the scrape job

The scheduled scrape (`.github/workflows/scrape.yml`) reads these **repository
secrets**. Each is optional; the job degrades safely when one is absent.

| Secret | Purpose | Scope | Owner | Expiry |
|---|---|---|---|---|
| `GEMINI_API_KEY` | Extraction (Gemini over already-public text). | Gemini API only. | Maintainers (org). | Rotate on suspicion; no fixed expiry. |
| `SCRAPE_BOT_TOKEN` | Push `data-staging` + open/update the review PR **as a real actor** so the PR's CI runs automatically. | A fine-grained PAT (or GitHub App token) with **Contents: read/write** + **Pull requests: read/write** on this repo only. Nothing else. | A maintainer or a dedicated `sakshi-bot` machine account. | ≤90 days; rotate before expiry and update the secret. |
| `INDIANKANOON_API_TOKEN` | Enable the Indian Kanoon court-record source. | Indian Kanoon API only (paid; accept their ToS first). | Maintainer who accepted the ToS. | Per Indian Kanoon; rotate on suspicion. |

**Why `SCRAPE_BOT_TOKEN` exists:** a push made with the default `GITHUB_TOKEN`
cannot trigger another workflow (GitHub's recursion guard), so the staged-review
PR's checks park as *"Action required"* and must be approved by hand every run.
Pushing/opening the PR with a real-actor token makes that CI run automatically.
Until the secret is set, the workflow falls back to `GITHUB_TOKEN` and a maintainer
approves the staged PR's CI manually.

**Merge discipline for data PRs:** once `SCRAPE_BOT_TOKEN` is set and staged-PR CI
runs on its own, **data-review PRs merge only through the normal reviewed path**
(required checks green + human review). Admin bypass is for emergencies only and
every use must be noted in the PR.

### The processed-document ledger on `main`

`data/_meta/processed.json` is the processed-document ledger — **operational
metadata only** (a `sha256(url)` per document + outcome + dates; never a URL,
never PII). Committing it to `main` each run lets coverage accounting work across
runs independently of when data-review PRs are merged.

- **Enable it** by setting the repo **variable** `LEDGER_TO_MAIN=true`. Off by
  default, the ledger simply rides along in the review branch instead.
- The push targets protected `main`, so the token's account must be able to
  **bypass main branch protection** — either `SCRAPE_BOT_TOKEN` belongs to an
  account with the admin role (already in the ruleset bypass list) or that account
  is added to the ruleset's bypass list. The fallback `GITHUB_TOKEN`
  (`github-actions[bot]`) is *not* an admin and will be blocked.
- **Fencing (enforced by the workflow, not convention):** (a) the ledger is
  validated against `schemas/ledger.schema.json` — `sha256` keys, an outcome enum,
  ISO dates, `additionalProperties:false` — and scanned for URL-shaped strings;
  (b) `pii_guard` runs over `data/_meta/`; (c) the commit uses the **Contents API**,
  which writes exactly one path, so it is structurally incapable of touching
  anything but `data/_meta/processed.json`. The reviewed data PR excludes
  `data/_meta` when this is on.

---

## 2. The data lifecycle

Data flows in one direction, from public sources to published shards. Every
record is traceable to a citable public source, and **PII is stripped before
anything touches disk**. Humans never hand-edit `data/`; the entire tree is
regenerated idempotently each run.

```
   PUBLIC SOURCES                                            PUBLISHED (GitHub Pages)
   official first, media second                              read-only, regenerated each run
 ┌──────────────────────────┐                              ┌──────────────────────────────┐
 │ eCourts / NJDG           │                              │ data/summary.json  (<50 KB)   │
 │ High Court portals       │                              │ data/index.json    (manifest) │
 │ Indian Kanoon (per ToS)  │                              │ data/{YYYY}/{STATE}.json      │
 │ NCRB / PIB / police PR   │                              └──────────────────────────────┘
 │ RSS of established media  │                                            ▲
 └────────────┬─────────────┘                                            │
              │                                                          │
              ▼                                                          │
  ┌───────────────────────┐   robots.txt honored, honest UA,             │
  │ FETCH                 │   <=1 req / 2s per host, ETag cache,          │
  │ pipeline/sources/*    │   exponential backoff on 429/5xx             │
  │ Source.fetch()        │                                              │
  │  -> [RawDocument]     │                                              │
  └──────────┬────────────┘                                              │
             │  RawDocument(url, publisher, fetched_at, text)            │
             ▼                                                           │
  ┌───────────────────────┐   Gemini, response_schema-constrained,      │
  │ EXTRACT               │   victim ALWAYS null by construction;        │
  │ extract/gemini.py     │   confidence required                        │
  └──────────┬────────────┘                                              │
             │  extraction.schema.json (structurally cannot hold PII)    │
             ▼                                                           │
  ┌───────────────────────┐   *** LAST GATE BEFORE DISK ***              │
  │ SANITIZE              │   regex + NER PII strip on EVERY string      │
  │ sanitize.py           │   field; 100% branch coverage                │
  └──────────┬────────────┘                                              │
             ▼                                                           │
  ┌───────────────────────┐   exact on CNR/FIR; fuzzy on                 │
  │ DEDUPE                │   district/date±3d/sections/court;           │
  │ dedupe.py             │   court beats media, newer status wins;      │
  └──────────┬────────────┘   ambiguous -> data/_review/                 │
             ▼                                                           │
  ┌───────────────────────┐   jsonschema every record, assign IDs,      │
  │ VALIDATE & SHARD      │   atomic temp->validate->rename;             │
  │                       │   pii_guard as FINAL assertion ─────────────►│
  └──────────┬────────────┘                                             (write)
             ▼
  ┌───────────────────────┐   confidence < 0.8  OR  ambiguous merge
  │ data/_review/         │   -> quarantined, excluded from Pages,
  │ (human review queue)  │      never auto-published
  └───────────────────────┘

  COMMIT: Action commits data/ ("data: daily update YYYY-MM-DD (+N new, ~M updated)"),
          auto-opens an issue on failure or if the review queue exceeds 20.
```

Two things to internalize from this diagram:

- **`sanitize.py` is the last gate before disk.** Nothing reaches `data/`
  without passing through it. `pii_guard` then runs again as a final assertion.
- **`data/_review/` is a dead end for anything uncertain** (confidence < 0.8 or
  ambiguous dedup). It is excluded from Pages and only a human moves records out
  of it.

---

## 3. Adding a new source module

Sources live in **`pipeline/sources/`**. Prefer official/structured sources
first; media is RSS of established outlets only. **No social-media scraping.**

### The interface contract

A source is a class (or module) that exposes a single method:

```python
async def fetch(self) -> list[RawDocument]: ...
```

`RawDocument` carries exactly four things: `url`, `publisher`, `fetched_at`,
and `text`. A source's only job is to return well-formed `RawDocument`s from a
public source. It does **not** extract fields, classify, dedupe, or write to
disk — later stages own all of that.

### Skeleton

```python
# pipeline/sources/example_highcourt.py
from pipeline.types import RawDocument


class ExampleHighCourtSource:
    """Fetches public cause lists from the Example High Court portal."""

    host = "example-hc.gov.in"

    async def fetch(self) -> list[RawDocument]:
        docs: list[RawDocument] = []
        # ... polite httpx calls here ...
        return docs
```

### Rules every source must follow

- **Respect `robots.txt`.** Do not fetch disallowed paths.
- **Honest User-Agent** naming the project and repo URL.
- **Rate-limit to <= 1 request / 2 s per host.** Use the shared politeness
  helper; do not roll your own faster path.
- **Cache** with ETag / Last-Modified where the server supports it.
- **Back off exponentially** on `429`/`5xx`.
- **Only public data.** If access requires a login, a paywall bypass, or
  anything a member of the public could not lawfully read, it is out of scope.
- **Respect source ToS** (e.g. Indian Kanoon via their API/ToS).
- Add tests with **clearly synthetic** fixtures (`"district": "TESTVILLE"`).
  Never commit a real case record, even as a fixture.

Register the source where the pipeline discovers sources (see existing entries
in `pipeline/sources/`), and add a short note in your PR describing the source,
its access terms, and why it qualifies.

---

## 4. Commit convention

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

### DO NOT add a Claude / AI co-author trailer

**Org policy:** never add a `Co-Authored-By: Claude` trailer (or any AI
co-author trailer) to a commit, and never put such a trailer in documentation or
commit-message examples. If your tooling adds one automatically, remove it before
you push. This applies even when an AI assistant wrote most of the change.

---

## 5. Pull request checklist

Before you request review, confirm **every** item:

- [ ] `make check` passes locally.
- [ ] Tests pass and coverage holds (>=85% pipeline; **100% on `sanitize.py`
      and `pii_guard.py`**).
- [ ] Types are clean under **`mypy --strict`**.
- [ ] **`pii_guard` is green.**
- [ ] **No hand edits to `data/`.** The tree is machine-generated; if your
      change affects data, it must flow through the pipeline.
- [ ] `additionalProperties: false` stays `false` at **every** object level in
      every schema. You did not loosen it.
- [ ] **`sanitize.py`, `pii_guard.py`, and the forbidden-field list are
      untouched** — unless you are acting on a specific, human-approved issue
      that authorizes the change (link it in the PR).
- [ ] Any new fixtures are clearly synthetic and contain **no PII** and no real
      case data.
- [ ] No secrets, keys, or `.env` contents committed.
- [ ] No Claude/AI co-author trailer on any commit.
- [ ] Commits follow Conventional Commits.

PRs that touch a guardrail file without a linked approving issue will be closed
with a request to open that issue first. This is not personal; it is how we keep
the guardrails auditable.

---

## 6. Review SLAs

We aim to be predictable so contributors are not left waiting.

| Change type | First maintainer response |
| --- | --- |
| Guardrail-touching (`sanitize.py`, `pii_guard.py`, forbidden list, schemas) | within **2 business days**, reviewed by a maintainer who did **not** author the change |
| New source module | within **3 business days** |
| Frontend / docs / tooling | within **5 business days** |
| Security or PII concern | **same day** — see below |

**Security / PII fast path.** If you believe PII has been or could be published,
do **not** open a public PR describing the leak. Contact a maintainer privately
(see `SECURITY.md`) so it can be handled immediately. Suspected published victim
identity is a same-day, drop-everything issue.

Takedown and correction requests are handled per [`TAKEDOWN.md`](./TAKEDOWN.md),
including removal-on-request for acquitted/quashed cases.

---

## 7. Vibe-coder onboarding

New here and leaning on an AI assistant? Welcome. Read this section carefully —
it exists so that AI-assisted contributions come out consistent with the rest of
the codebase instead of subtly wrong.

### What Sakshi actually is, in plain language

Sakshi is a **fully static** website backed by **JSON files in git**. There is no
live server, no database at runtime, no user accounts. Once a day, an automated
pipeline reads public court records and reputable news, extracts a few neutral
facts about each *publicly reported* case, strips anything that could identify a
victim, deduplicates, validates, and writes plain JSON into `data/`. GitHub Pages
serves that JSON, and the browser draws charts and tables from it.

So there are really two worlds:

```
   ┌───────────────────────────────┐        ┌──────────────────────────────┐
   │  THE PIPELINE (Python)        │        │  THE SITE (static frontend)  │
   │  pipeline/ , extract/ ,       │  ───►  │  site/ : Vite + vanilla JS   │
   │  sanitize.py , pii_guard.py   │  data/ │  reads data/*.json only      │
   │  runs on a schedule / CI      │  JSON  │  no framework, no backend    │
   └───────────────────────────────┘        └──────────────────────────────┘
        writes data/  (machine only)              reads data/  (never writes)
                    │                                      ▲
                    └──────────  data/  (JSON in git) ─────┘
              summary.json  ·  index.json  ·  {YYYY}/{STATE}.json
```

The `data/` directory is the contract between the two worlds. The pipeline is the
**only** writer. The site is a **reader**. You almost never edit `data/` by hand —
if you feel the urge to, stop, because that is a sign you are solving the problem
in the wrong place.

### Where things live

- `pipeline/sources/` — one module per public source, each exposing
  `fetch() -> list[RawDocument]`.
- `extract/gemini.py` — turns public text into structured, schema-constrained
  fields (victim always `null`).
- `sanitize.py` — the last PII gate before disk. **Guardrail file.**
- `pii_guard.py` — the final assertion that no PII slipped through. **Guardrail
  file.**
- `schemas/case.schema.json` — the single source of truth for a record's shape.
- `schemas/extraction.schema.json` — the pre-sanitized Gemini response shape,
  structurally incapable of holding victim data.
- `data/` — machine-generated JSON. Do not hand-edit.
- `site/` — the static frontend.

### Things AI assistants get wrong here

AI assistants are trained on generic web projects and will confidently suggest
things that are correct elsewhere and **wrong here**. Watch for all of these and
reject them:

1. **Hand-editing `data/`.** Assistants love to "just fix the JSON." Never. The
   pipeline regenerates `data/` idempotently; a hand edit is overwritten and, worse,
   bypasses validation and PII checks. Fix the pipeline instead.
2. **Storing PII in fixtures.** An assistant will happily invent a realistic
   victim name, age, or address to make a test "look real." That is exactly what
   this project forbids. Fixtures must be obviously synthetic (`"district":
   "TESTVILLE"`) and contain no real or realistic personal data.
3. **Adding frameworks to the static site.** Suggestions to "just add React" or
   pull in a heavy dependency break the no-framework, Lighthouse >=95 constraint.
   The site stays Vite + vanilla JS + a lightweight chart library.
4. **Bypassing `sanitize.py`.** Any path that writes to `data/` *must* go through
   sanitize. An assistant proposing a shortcut that writes records directly is
   introducing a PII leak. There are no exceptions and no "fast paths."
5. **Loosening `additionalProperties: false`.** When a field "doesn't validate,"
   an assistant's reflex is to relax the schema. Do not. `additionalProperties`
   stays `false` at every object level — it is part of how forbidden fields are
   made impossible. Fix the data or add the field deliberately.
6. **Editing the guardrail files** (`sanitize.py`, `pii_guard.py`, the
   forbidden-field list) without a human-approved issue. These files are the legal
   backbone of the project. Changes require a linked, approved issue and review by
   a maintainer who did not author the change.

Also: **never let an assistant add a `Co-Authored-By: Claude` trailer** to your
commits. Remove it if it appears.

When in doubt, re-read the Phase 0 guardrails in `CLAUDE.md` and ask in an issue
before you build. Getting it right slowly is always better than getting it wrong
fast here.

---

## Helplines

If you or someone you know needs help:

- **National Women's Helpline — 181**
- **Police — 112**
- **Cyber Crime — 1930**
- **NCW complaint portal — ncwapps.nic.in**

---

This is a civic-accountability record of publicly reported cases, compiled from public
judicial records and credible media. It is not a substitute for official crime statistics
such as NCRB data. Contribute with the care the subject demands.
