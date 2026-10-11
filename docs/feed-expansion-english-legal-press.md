# Adding feeds — English legal press and other press (draft, 3 August 2026)

**Status when written:** a draft for me to decide on. **Every feed was added switched
off (`enabled: false`)**; nothing was turned on in this pass. I checked `robots.txt` live
on **3 August 2026** for the `sakshi-bot` User-Agent. An outlet only counts as a candidate
if robots.txt **ALLOWS** it **and** the URL returns a valid RSS or Atom feed.

> **Update:** I turned LiveLaw on on 12 August 2026 (`livelaw` in `sources.yml`). The
> legal and terms-of-service review noted below is still marked as pending there.

## Added (switched off)

| Outlet | Tier | Feed URL | robots | feed |
|---|---|---|---|---|
| **LiveLaw** | 2 (legal_press) | `https://www.livelaw.in/google_feeds.xml` | ALLOW | 200 XML |

LiveLaw's publisher name is classed as **`legal_press`** (`pipeline/provenance`), so a
record from it is **tier 2**: reporting on court proceedings with a case citation, but
not the court record itself. (The Times of India and Hindustan Times national feeds from
the first batch are still the tier-3 national candidates in
`docs/feed-expansion-tranche-1.md`.)

## Outlets checked and left out (each one written down so it can be checked)

| Outlet | Reason (checked 3 August 2026) |
|---|---|
| Bar & Bench (legal_press) | robots.txt **DISALLOWS** our User-Agent |
| The New Indian Express | robots.txt **DISALLOWS** |
| The Telegraph India | robots.txt **DISALLOWS** (confirmed again from the first batch) |
| The News Minute | robots.txt **DISALLOWS** (confirmed again from the first batch) |
| Deccan Herald / Scroll.in / Deccan Chronicle | robots.txt **DISALLOWS** (first batch) |
| The Tribune | robots.txt **ALLOWS**, but I couldn't find a valid RSS feed (the homepage lists none; `/rss` and `/feeds/rss/india` return 404 or aren't XML). It needs the right feed address before it can be a candidate |
| The Print | robots.txt **ALLOWS**, but `/feed/` isn't valid RSS (first batch). It needs the right address |

A DISALLOW is final: the pipeline never fetches a URL that robots.txt disallows. Bar &
Bench (a major legal-press source) disallows automated access, so it **can't be added**
unless its robots.txt changes.

## Before turning a feed on (my checklist)
1. A legal and terms-of-service review of each outlet's rules on automated RSS use.
2. Check robots.txt again at the time of turning it on.
3. Set `enabled: true` for the approved feeds only, then watch the first run's heartbeat
   and the size of the possible-duplicates list and the review queue.

Adding a feed only changes *what we fetch*. Every step (extract, verify, sanitize,
pii_guard) stays the same. A record from the legal press still withholds accused names
unless a court source is added to it.
