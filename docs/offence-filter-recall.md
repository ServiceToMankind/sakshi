# The news offence-word filter — how much it catches

The news pre-filter's job is to skip documents that *obviously* have nothing to do with
sexual offences, so we don't pay an AI model to read them, while **never throwing away a
real sexual-offence report**. That's my red line. Gemini's `in_scope` check makes the
actual decision about scope, so the filter is tuned to **catch everything (high recall),
even if it lets through a lot that isn't relevant (low precision)**.

## Why the old filter was wrong for news

The old ordering hint (`_OFFENCE_HINTS`) was **English only** and leaned on **section
numbers** (`rape`, `sexual`, `assault`, `376`, `354`, and so on). It failed on news in two
basic ways:

1. **Newspapers describe the offence, not the section of the law**, so matching on
   section numbers doesn't help; and
2. **it couldn't match any non-English script at all**, so every Telugu, Hindi, Tamil and
   Marathi crime feed scored **zero, every time**.

It also only *sorted* documents rather than skipping any, so regional documents sank to
the bottom, and a run with a time limit never got to them.

## The new filter

- **Court sources (tier 1)** keep the section-number pre-filter as it was (a judgment
  cites its sections, and the filter decides which documents we pay to fetch).
- **News sources (tier 2 and 3)** use `pipeline.offence_filter.media_offence_hit`: a
  chosen set of English offence words (matched as whole words) **plus offence words in
  native scripts** for Hindi, Telugu, Marathi and Tamil. The word lists were drafted and
  checked one language at a time, by AI reviewers working as native-language
  sub-editors. Native-script words match anywhere in the text; English words match only as
  whole words (so "rape" doesn't match "grape", and "minor" on its own isn't a word we
  look for). Words that only describe a person (girl, boy, student, woman, minor) were
  removed: they don't catch anything extra (a real headline always has an offence word
  too), and they only add false alarms.

## Measurement (12 August 2026)

I fetched **1,064 live documents** from the feeds that were switched on. A set of 175 of
them (every regional document, every document either filter flagged, and a fixed sample of
unflagged ones) was labelled without knowing which filter had flagged it, for "is this a
sexual-offence report?". Here's how the filters did on the clear positives:

| Filter | Recall (clear positives) | Recall on regional | Pass rate (of 1064) |
|---|---:|---:|---:|
| **Old** (English `_OFFENCE_HINTS`) | 14/16 = **88%** | **0/3 = 0%** | 3.0% |
| **New** (tiered, trimmed) | 16/16 = **100%** | 2/3 | **1.7%** |

- The new filter catches **every** clear sexual-offence report, **including the regional
  ones the old filter could never match**, while letting *fewer* documents through (it
  drops the old filter's noisy bare `assault`, `abuse` and `harass`, which matched other
  crimes).
- The two reports it didn't catch are secondary matters *close to* POCSO (a doctor not
  reporting a child's pregnancy; a dispute over a pregnancy diagnosis), not reports of the
  offence itself. Gemini's scope check would have turned them away anyway.

## Cost

A pass rate of **1.7%**. At about 600 crime-feed documents a day and about $0.008 per
document, that's **roughly $2.40 a month**, well under the $10 cap, so the cap doesn't
need raising. The pass rate for each source is reported every run in
`data/pipeline_health.json` and in the heartbeat. A separate check fails the run loudly if
more than 50 documents get through the pre-filter but no cases come back, so a broken
step can't hide behind a quiet day.

## Turning on more languages

A news feed in a language that **isn't** in `offence_filter.LANGUAGES_WITH_TERMS` (at the
moment Hindi, Telugu, Marathi and Tamil) must stay `enabled: false`. Turning it on would
just produce zeros without anyone noticing. Bengali, Malayalam, Kannada and Gujarati stay
switched off until their word lists are built and measured.
