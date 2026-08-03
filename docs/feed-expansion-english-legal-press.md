# Feed expansion — English legal press + press (§4b/4c, DRAFT)

**Status:** Draft for operator decision. **Every feed ships `enabled: false`** — nothing is
enabled here (hard stop). `robots.txt` verified live **2026-08-03** for the `sakshi-bot` UA;
a candidate qualifies only if robots **ALLOW**s it **and** the URL returns valid RSS/Atom.

## Added (disabled)

| Outlet | Tier | Feed URL | robots | feed |
|---|---|---|---|---|
| **LiveLaw** | 2 (legal_press) | `https://www.livelaw.in/google_feeds.xml` | ALLOW | 200 XML |

LiveLaw's publisher name classifies as **`legal_press`** (`pipeline/provenance`), so a record
sourced from it is **tier 2** — court proceedings with a case citation, not the primary court
record. (The Times of India + Hindustan Times national wires from tranche 1 remain the tier-3
national candidates in `docs/feed-expansion-tranche-1.md`.)

## Candidates checked and EXCLUDED (auditable — §4c "document each exclusion")

| Outlet | Reason (verified 2026-08-03) |
|---|---|
| Bar & Bench (legal_press) | robots.txt **DISALLOW** for our UA |
| The New Indian Express | robots.txt **DISALLOW** |
| The Telegraph India | robots.txt **DISALLOW** (re-confirmed from tranche 1) |
| The News Minute | robots.txt **DISALLOW** (re-confirmed from tranche 1) |
| Deccan Herald / Scroll.in / Deccan Chronicle | robots.txt **DISALLOW** (tranche 1) |
| The Tribune | robots **ALLOW**, but no valid RSS feed URL found (homepage advertises none; `/rss`, `/feeds/rss/india` 404 / non-XML) — needs the correct feed path before it can be a candidate |
| The Print | robots **ALLOW**, `/feed/` not valid RSS (tranche 1) — needs correct path |

A DISALLOW is final: the pipeline never fetches a robots-disallowed URL. Bar & Bench (a
prime legal-press source) disallows automated access, so it is **not eligible** until its
robots policy changes.

## Before enabling (operator checklist)
1. Legal/ToS review of each outlet's terms for automated RSS consumption.
2. Re-verify robots.txt at enable time.
3. Flip `enabled: true` for the approved source(s) only, and watch the first run's heartbeat
   + the candidate-match / review-queue depth.

Adding a feed changes only *what is fetched*; every gate (extract → verify → sanitize →
pii_guard) is unchanged. A legal-press record still withholds accused names unless a court
source is unioned in.
