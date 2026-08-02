# Feed expansion — tranche 1 (DRAFT)

**Status:** Draft for operator decision (overnight, queue X1). **Every feed ships
`enabled: false`** — the morning decision is a one-line flip per source. Nothing is
enabled tonight (NIGHT_RUN hard stop 1).

`robots.txt` verdicts were verified live on **2026-08-01** for the project's
User-Agent (`sakshi-bot/1.0 (+https://github.com/ServiceToMankind/sakshi)`) using
the same `RobotFileParser` check the pipeline's `PoliteClient` applies. A feed is a
candidate only if robots **ALLOW**s it **and** the URL returns a valid RSS/Atom
document.

## Candidates to enable (added to `sources.yml`, disabled)

| Outlet | Feed URL | robots.txt | Feed | ToS |
|---|---|---|---|---|
| The Times of India | `https://timesofindia.indiatimes.com/rssfeedstopstories.cms` | **ALLOW** | 200, XML | RSS is publicly syndicated; full ToS/legal review pending before enabling |
| Hindustan Times | `https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml` | **ALLOW** | 200, XML | RSS is publicly syndicated; full ToS/legal review pending before enabling |

Both are national/pan-India wires (top-stories / India-news), added to the
`national:` block. They are broad feeds — expect a low sexual-offence hit rate; the
extractor's `in_scope` gate + the offence-relevance ordering already handle that.

## Candidates checked and EXCLUDED

| Outlet | Reason (verified 2026-08-01) |
|---|---|
| Scroll.in | robots.txt **DISALLOW** for our UA |
| Deccan Herald | robots.txt **DISALLOW** |
| The News Minute | robots.txt **DISALLOW** |
| The Telegraph India | robots.txt **DISALLOW** |
| Deccan Chronicle | robots.txt **DISALLOW** |
| The Print | robots **ALLOW**, but `/feed/` did not return a valid RSS document — needs the correct feed path before it can be a candidate |

A DISALLOW is final: the pipeline never fetches a robots-disallowed URL, so these
are not eligible until the outlet's robots policy changes.

## Before enabling any feed (operator checklist)

1. **Legal/ToS review** of each outlet's terms for automated RSS consumption
   (the table's ToS column is a placeholder, not a legal opinion).
2. **Re-verify robots.txt** at enable time (policies change).
3. **Flip `enabled: true`** for the approved source(s) only — one line each — and
   watch the first run's heartbeat (fetched/extracted/in-scope, cost) and the
   candidate-match / review-queue depth. NIGHT_RUN pauses a tranche if the
   candidate queue exceeds 25 or a pair sits > 7 days.
4. **State tagging.** These national wires are not state-specific; a record's state
   comes from extraction, and `coverage.json` counts it honestly per state.

## Guardrail note

Adding a feed changes only *what is fetched*, never a protection: every fetched
record still passes fetch → extract → sanitize → dedupe → verify → `pii_guard`
unchanged. Media-sourced accused names remain withheld (`name_public_court_record:
null`); minors are projected and never auto-published.
