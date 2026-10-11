# Sakshi — Sākshī (साक्षी)

**Because the record must not forget.**

*A Service to Mankind initiative — [stmorg.in](https://stmorg.in)*

[![CI](https://github.com/ServiceToMankind/sakshi/actions/workflows/ci.yml/badge.svg)](https://github.com/ServiceToMankind/sakshi/actions/workflows/ci.yml)
[![Deploy](https://github.com/ServiceToMankind/sakshi/actions/workflows/deploy.yml/badge.svg)](https://github.com/ServiceToMankind/sakshi/actions/workflows/deploy.yml)
[![Code License: MIT](https://img.shields.io/badge/code-MIT-blue)](LICENSE)
[![Data License: ODbL v1.0](https://img.shields.io/badge/data-ODbL%20v1.0-green)](LICENSE-DATA)

The site: **[sakshi.stmorg.in](https://sakshi.stmorg.in/)**

---

## Why I built Sakshi

*Sakshi* is Sanskrit for *witness*. I built it to keep a public, permanent record of
**publicly reported** sexual-offence cases across India: where they happened, what the
charges were, and where each case stands in the courts.

Every day, a small program reads public court records and established news outlets,
pulls out a few plain facts about each case, and adds them to a website you can search
and filter. There is no server and no database behind it. The whole record is a set of
JSON files in this repository, and the site is a static page on GitHub Pages.

The only goal is accountability: to make the scale, the places and the pace of justice
visible, district by district, no matter who is involved.

---

## What this is, and what it isn't

Sakshi is a record of **publicly reported cases**, gathered from public court records and
credible media. The counts show what was reported and recorded in public sources. It is
**not** a crime statistic, and it is **not** a substitute for official figures such as
NCRB data. How often cases get reported differs from place to place and year to year.

An accused person is presumed innocent until proven guilty. Any status you see reflects
public court records as of the last update. Acquittals and quashed cases are shown with
the same prominence as convictions.

---

## If you need help now

| Service | Number / Link |
| --- | --- |
| National Women's Helpline | **181** |
| Police | **112** |
| Cyber Crime | **1930** |
| NCW complaint portal | **ncwapps.nic.in** |

These are on every page of the site too. If you or someone you know is in immediate
danger, call the police on **112**.

---

## How a case gets onto the site

```
                    PUBLIC SOURCES
   Indian Kanoon (court records, via its paid API)
   High Court judgment pages: Delhi · J&K and Ladakh · Meghalaya
   News RSS: English · Hindi · Telugu · Marathi · Tamil
   Case leads people send in through GitHub issues
                         │
                         ▼
   ┌─────────┐   RawDocument(url, publisher, fetched_at, text)
   │  FETCH  │   reads robots.txt · at most 1 request every 2s per site
   └─────────┘   honest User-Agent · ETag/Last-Modified · backs off on errors
                         │
                         ▼
   ┌─────────┐   Gemini (gemini-3.5-flash, falls back to gemini-3.5-flash-lite)
   │ EXTRACT │   fills a fixed form from already-public text only.
   └─────────┘   "victim" is always null · a confidence score is required
                         │
                         ▼
   ┌─────────┐   a second Gemini check against the source, when switched on
   │ VERIFY  │   (VERIFY_ENABLED). It can approve, fix a few facts, or turn a
   └─────────┘   case away. It can never touch the minor flag or the accused.
                         │
                         ▼
   ┌──────────┐   drops forbidden fields · regex-redacts Aadhaar, phone,
   │ SANITIZE │   email and PAN · removes non-English script · rewrites a
   └──────────┘   child's case into a fixed minimal form. Last gate before disk.
                         │
                         ▼
   ┌────────┐   exact match on CNR or FIR · close match on district,
   │ DEDUPE │   date ±3 days, charges, court · NEVER on the victim
   └────────┘   unsure → held back for a person to look at
                         │
                         ▼
   ┌────────────────┐   checks every record against the schema · gives
   │ VALIDATE/SHARD │   each case a fixed ID · pii_guard runs last
   └────────────────┘
                         │
                         ▼
   ┌────────┐   data/{YYYY}/{STATE}.json and a few summary files
   │ data/  │   rebuilt from scratch every run
   └────────┘
                         │
                         ▼
   ┌──────────────────────────────┐
   │ STATIC SITE on GitHub Pages  │  Vite + plain JavaScript, reads the JSON
   └──────────────────────────────┘
```

A new-cases run happens every day at 06:00 IST. Once a week, on Sunday at 07:00 IST,
a second run checks only the court sources and updates the status of cases we already
have. It never adds new cases.

What the sanitizer does is deliberately simple: it uses fixed rules and regular
expressions. It does not use a name-recognition (NER) model. It also clears victim
occupations and certain romanised Indian-language words (family terms, village office
titles, words for a locality smaller than a district) out of titles and summaries.

---

## The rules I will not bend

These aren't preferences. They are written into the code, and the checks fail if they
are broken.

### The victim is never collected, not just hidden

Victim names, photos, addresses, family members' names, school or workplace, ages
(beyond a single yes/no `minor_involved` flag), and any other detail that could identify
a victim are **never** written to disk, committed, logged, put into an AI prompt or
answer, cached, or kept in git history. We don't collect them and then remove them. We
never take them in at all.

- **The law behind this:** Section 72 of the Bharatiya Nyaya Sanhita 2023 (formerly IPC
  228A) makes it a crime to disclose the identity of a victim of a sexual offence.
  Section 23 of the POCSO Act 2012 does the same for children and covers any detail that
  could identify them.
- The extraction prompt always forces `"victim": null`, and the sanitizer strips any
  personal-looking field afterwards, whatever the model returned. For a child, a record
  keeps only the state, district, year, offence category and court status.

### Cases are matched on the case, never on the person

When two reports describe the same case, we match them on the FIR number, the court
case number (CNR), the police station, the district, the date and the court. **Never**
on anything about the victim.

### The accused are presumed innocent

An accused person's name is stored only when it appears in an official court record (a
judgment, order or cause list), never from news reports alone. If a name only came from
the media, the record stores `"name_public_court_record": null` and the site shows
*"Withheld (media-sourced, not yet in court record)"*. Every case shows this notice:
*"An accused person is presumed innocent until proven guilty. Status shown reflects
public court records as of the last update."* If a case ended in acquittal or was
quashed, you can ask me to remove it. See [TAKEDOWN.md](TAKEDOWN.md).

### Every fact has a source

Every record carries `sources[]`, each with a URL, the publisher or court, and the date
we retrieved it. If there is no public source to cite, it isn't published. Anything the
pipeline is less than 80% sure about (`confidence < 0.8`) goes to `data/_review/`
instead. That folder is never committed and never shown on the site. Nothing in it is
published automatically.

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/ServiceToMankind/sakshi.git
cd sakshi

# 2. Create a Python 3.12 environment
python3.12 -m venv .venv
source .venv/bin/activate
# (or, with uv)
#   uv venv --python 3.12 && source .venv/bin/activate

# 3. Install dependencies
pip install -e '.[dev]'
#   (or)  uv pip install -e '.[dev]'
#   (or, steps 2-3 plus the site in one go)  make setup

# 4. Configure secrets
cp .env.example .env
# then edit .env and set GEMINI_API_KEY=...   (never commit .env)

# 5. Run the full set of checks
make check

# 6. Run the site locally
cd site
npm install
npm run dev
```

`make check` runs ruff, mypy `--strict`, pytest (at least 85% coverage of the pipeline,
and 100% on `sanitize` and `pii_guard`), schema validation of every data file plus the
`summary.json` size limit, `pii_guard`, the readability check on summaries, a scan for
leaked API keys (`secret_guard`), a check that every case is counted in every total
(`counts_guard`), eslint and prettier. Lighthouse runs on the built site with
`make lighthouse` and in the deploy pipeline.

---

## Repository layout

```
sakshi/
├── README.md
├── CONTRIBUTING.md
├── TAKEDOWN.md
├── SECURITY.md
├── CODE_OF_CONDUCT.md
├── LICENSE                 # MIT, for the code
├── LICENSE-DATA            # ODbL v1.0, for everything under data/
├── .env.example
├── Makefile
├── pyproject.toml
├── sources.yml             # every source, by state, each with an on/off switch
├── schemas/
│   ├── case.schema.json         # the one true shape of a record
│   ├── extraction.schema.json   # the form Gemini fills in; it has no room for a victim
│   ├── correction.schema.json   # shape of a file in corrections/
│   └── ledger.schema.json       # shape of the processed-document ledger
├── pipeline/                   # Python 3.12, fully typed
│   ├── pii_constants.py        # the forbidden-field list and personal-data patterns
│   ├── sanitize.py             # strips personal data; last gate before disk
│   ├── verify.py               # the second Gemini check before publishing
│   ├── dedupe.py               # case-anchored matching and merging
│   ├── validate.py             # schema validation and the summary size limit
│   ├── shard.py                # assigns IDs and writes the data files
│   ├── corrections.py          # applies the files in corrections/
│   ├── extract/gemini.py       # schema-constrained extraction
│   └── sources/                # one module per source, each returns RawDocuments
├── scripts/
│   ├── pii_guard.py            # final check over everything written
│   ├── readability_guard.py    # summaries must be plain English
│   ├── counts_guard.py         # every case counted everywhere
│   └── secret_guard.py         # no API keys in tracked files
├── corrections/                # reviewed fixes to individual records
├── docs/                       # dated surveys, sweeps and proposals
├── data/                       # generated; never edited by hand (see data/README.md)
│   ├── summary.json             # front-page totals, under 50 KB
│   ├── index.json               # list of every data file
│   ├── recent.json              # the 50 most recently listed cases
│   ├── jurisdictions.json       # scorecard for every district (no cap)
│   ├── coverage.json            # which states we read sources for, and gaps
│   ├── pipeline_health.json     # per-source counts from the last run
│   └── {YYYY}/{STATE}.json      # full records, newest first
├── site/                        # Vite + plain JavaScript static site
└── .github/workflows/           # ci.yml, scrape.yml (daily run), deploy.yml
```

Nobody edits anything under `data/` by hand, me included. The whole tree is rebuilt the
same way on every run, so running it again is always safe.

---

## License

- **Code**: MIT License. See [LICENSE](LICENSE).
- **Data** (everything under `data/`): Open Database License (ODbL) v1.0. See [LICENSE-DATA](LICENSE-DATA).

---

## Getting involved

- [CONTRIBUTING.md](CONTRIBUTING.md): how to contribute, and the things that must never
  happen here (editing `data/` by hand, personal data in test fixtures, adding a
  framework to the site, getting around `sanitize.py`, loosening
  `additionalProperties: false`).
- [TAKEDOWN.md](TAKEDOWN.md): how to ask for a correction, or for removal of an acquitted
  or quashed case.
- [SECURITY.md](SECURITY.md): how to report a security problem privately.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md): how we treat each other.

---

*Sakshi is a witness, not a judge. It records what public sources say, cites them, and
lets the record stand.*
