# Sakshi — Sākshī (साक्षी)

**Because the record must not forget.**

*A Service to Mankind initiative — [stmorg.in](https://stmorg.in)*

[![CI](https://github.com/ServiceToMankind/sakshi/actions/workflows/ci.yml/badge.svg)](https://github.com/ServiceToMankind/sakshi/actions/workflows/ci.yml)
[![Deploy](https://github.com/ServiceToMankind/sakshi/actions/workflows/deploy.yml/badge.svg)](https://github.com/ServiceToMankind/sakshi/actions/workflows/deploy.yml)
[![Code License: MIT](https://img.shields.io/badge/code-MIT-blue)](LICENSE)
[![Data License: ODbL v1.0](https://img.shields.io/badge/data-ODbL%20v1.0-green)](LICENSE-DATA)

---

## Mission

Sakshi — Sanskrit for *witness* — is an open-source, fully static public-accountability
platform that tracks **publicly reported** sexual-assault cases across India. It is
aggregated daily from public judicial records (eCourts / NJDG, High Court portals,
Indian Kanoon) and credible media (RSS of established outlets), and presented on a fast,
filterable dashboard hosted on GitHub Pages. Its single purpose is civic accountability:
to make the scale, geography, and judicial status of these cases permanently visible,
jurisdiction by jurisdiction — irrespective of anyone's identity, community, or politics.

---

## What this is

Sakshi is a civic-accountability record of **publicly reported cases**, compiled from public
judicial records and credible media. Counts reflect what was reported and recorded in public
sources. It is not a substitute for official crime statistics such as NCRB data — reporting
rates vary across regions and over time.

An accused person is presumed innocent until proven guilty. Any status shown reflects
public court records as of the last update. Acquittals and quashed cases are shown with
equal prominence.

---

## If you need help now

| Service | Number / Link |
| --- | --- |
| National Women's Helpline | **181** |
| Police | **112** |
| Cyber Crime | **1930** |
| NCW complaint portal | **ncwapps.nic.in** |

These are shown on every page of the site as well. If you or someone you know is in
immediate danger, contact the police on **112**.

---

## Architecture

```
                 PUBLIC SOURCES
   eCourts / NJDG · High Court portals · Indian Kanoon
        NCRB · PIB / police press · RSS (established media)
                        │
                        ▼
   ┌─────────┐   RawDocument(url, publisher, fetched_at, text)
   │  FETCH  │   httpx + asyncio · robots.txt · <=1 req / 2s per host
   └─────────┘   honest User-Agent · ETag/Last-Modified · backoff
                        │
                        ▼
   ┌────────────────┐   Gemini (gemini-2.5-flash), response_schema-
   │ GEMINI EXTRACT │   constrained JSON over ALREADY-PUBLIC text only.
   └────────────────┘   victim := null enforced · confidence required
                        │
                        ▼
   ┌──────────┐   regex + NER PII stripping on EVERY string field.
   │ SANITIZE │   Last gate before disk. 100% branch coverage.
   └──────────┘
                        │
                        ▼
   ┌────────┐   exact on CNR/FIR · fuzzy on district/date±3d/sections/court
   │ DEDUPE │   CASE-ANCHORED (never victim) · ambiguous -> data/_review/
   └────────┘
                        │
                        ▼
   ┌────────────────┐   jsonschema every record · assign deterministic IDs
   │ VALIDATE/SHARD │   write shards + summary.json + index.json
   └────────────────┘   pii_guard as final assertion · atomic writes
                        │
                        ▼
   ┌────────┐   data/summary.json · data/index.json
   │ data/  │   data/{YYYY}/{STATE}.json  (regenerated idempotently)
   └────────┘
                        │
                        ▼
   ┌──────────────────────────────┐
   │ STATIC SITE on GitHub Pages  │  Vite + vanilla JS · reads JSON shards
   └──────────────────────────────┘
```

---

## Phase-0 guardrails (legally mandatory)

These are not preferences. They are encoded as automation, not merely prose.

### Victim identity is never ingested — not merely redacted

Victim names, photos, addresses, family-member names, school / workplace, ages (beyond
the boolean `minor`), and any re-identifying detail are **never** written to disk,
committed, logged, placed in model outputs, cached, or kept in git history.

- **Legal basis:** Section 72 of the Bharatiya Nyaya Sanhita 2023 (formerly IPC 228A)
  criminalizes disclosing the identity of victims of sexual offences; Section 23 of the
  POCSO Act 2012 does the same for minors, extending to any identifying detail.
- The extraction prompt always forces `"victim": null`, and a post-extraction sanitizer
  strips any PII-shaped field regardless. For minors, a record stores only: state,
  district, year, offence category, and judicial status.

### Case-anchored deduplication

Cases are matched and deduplicated on FIR number, court case number (CNR), police
station, district, date, and court — **never** on victim identity.

### Presumption of innocence

Accused names are stored only when present in an official court record (judgment, order,
or cause list) — never from media alone. Media-only sourcing yields
`"name_public_court_record": null` and the label *"Withheld (media-sourced, not yet in
court record)"*. Every case carries the persistent banner: *"An accused person is
presumed innocent until proven guilty. Status shown reflects public court records as of
the last update."* Removal-on-request is supported for acquitted / quashed cases; see
[TAKEDOWN.md](TAKEDOWN.md).

### Sources are mandatory

Every data point carries `sources[]` — `{url, publisher/court, retrieved date}`. Nothing
without a citable public source is published. Extractions with confidence `< 0.8` are
quarantined to `data/_review/` (excluded from Pages) for human review and are never
auto-published.

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

# 4. Configure secrets
cp .env.example .env
# then edit .env and set GEMINI_API_KEY=...   (never commit .env)

# 5. Run the full quality gate
make check

# 6. Run the site locally
cd site
npm install
npm run dev
```

`make check` runs ruff, mypy `--strict`, pytest (>=85% pipeline coverage, 100% on
`sanitize` / `pii_guard`), jsonschema validation of all shards, `pii_guard`, the
`summary.json` size assertion, eslint, and prettier. Lighthouse CI runs on the
built site via `make lighthouse` (and in the deploy pipeline).

---

## Repository layout

```
sakshi/
├── README.md
├── CONTRIBUTING.md
├── TAKEDOWN.md
├── SECURITY.md
├── CODE_OF_CONDUCT.md
├── LICENSE                 # MIT — applies to code
├── LICENSE-DATA            # ODbL v1.0 — applies to everything under data/
├── .env.example
├── Makefile
├── pyproject.toml
├── schemas/
│   ├── case.schema.json         # single source of truth for record shape
│   └── extraction.schema.json   # pre-sanitized Gemini response schema
├── pipeline/                   # Python 3.12, fully typed
│   ├── pii_constants.py        # canonical forbidden-field list + PII regexes
│   ├── sanitize.py             # PII stripping — last gate before disk
│   ├── validate.py             # jsonschema validation + summary-size gate
│   ├── dedupe.py               # case-anchored dedup + merge policy
│   ├── shard.py                # validate, assign IDs, write shards
│   ├── extract/gemini.py       # response_schema-constrained extraction
│   └── sources/                # one module per source -> RawDocument
├── scripts/pii_guard.py        # final assertion over written data
├── data/                        # generated — never hand-edited
│   ├── summary.json             # < 50 KB (CI-asserted)
│   ├── index.json               # shard manifest
│   ├── _review/                 # low-confidence / ambiguous (not published)
│   └── {YYYY}/{STATE}.json      # full records, sorted by date desc
├── site/                        # Vite + vanilla JS static frontend
└── .github/workflows/           # ci.yml, daily update action
```

Humans never hand-edit anything under `data/`. The whole tree is regenerated
idempotently on each run, so re-runs are safe.

---

## License

- **Code** — MIT License. See [LICENSE](LICENSE).
- **Data** (everything under `data/`) — Open Database License (ODbL) v1.0. See [LICENSE-DATA](LICENSE-DATA).

---

## Governance and contribution

- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute, and the things that must never
  be done (hand-editing `data/`, storing PII in fixtures, adding frameworks to the static
  site, bypassing `sanitize.py`, loosening `additionalProperties:false`).
- [TAKEDOWN.md](TAKEDOWN.md) — removal-on-request process for acquitted / quashed cases.
- [SECURITY.md](SECURITY.md) — responsible disclosure.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — community expectations.

---

*Sakshi is a witness, not a judge. It records what public sources say, cites them, and
lets the record stand.*
