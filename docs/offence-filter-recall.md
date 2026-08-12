# §2 media offence-language pre-filter — recall measurement

The media pre-filter's job is to skip *obviously irrelevant* documents so we don't pay an LLM
to read them, while **never discarding a true sexual-offence report** (the operator's red
line). Gemini's `in_scope` gate makes the actual scope decision. So the filter is tuned for
**high recall / low precision**.

## Why the old filter was wrong for media

The old ordering hint (`_OFFENCE_HINTS`) was **English-only** and **section-anchored-ish**
(`rape`, `sexual`, `assault`, `376`, `354`, …). Two structural failures on media:

1. **Newspapers report the offence, not the statute**, so the section anchoring is moot; and
2. **it cannot match any non-English script at all** — every Telugu / Hindi / Tamil / Marathi
   crime feed scored **zero by construction**.

It was also only a *sort*, not a skip, so regional docs sank to the bottom and a
wall-clock-bounded run never reached them.

## The new filter

- **Court sources (tier 1)** keep the statute pre-filter unchanged (a judgment cites its
  sections; it gates per-document billing).
- **Media sources (tier 2/3)** run `pipeline.offence_filter.media_offence_hit`: a curated
  English offence-term set (word-boundaried) **plus native-script offence terms** for Hindi,
  Telugu, Marathi and Tamil, built and adversarially reviewed by native-language sub-editors
  (one agent per language). Native terms match as substrings; roman terms are word-boundaried
  (so "rape" ≠ "grape", and bare "minor" is not a term). Pure person-nouns (girl/boy/student/
  woman/minor) were removed — they add no recall (a real headline carries an offence word too)
  and only add false positives.

## Measurement (2026-08-12)

**1064 live documents** fetched from the enabled media feeds. A stratified set of 175 (every
regional doc + every doc either filter flagged + a deterministic unflagged sample) was
blind-labelled for "is this a sexual-offence report?". Result over the labelled clear
positives:

| Filter | Recall (clear positives) | Recall on regional | Pass rate (of 1064) |
|---|---:|---:|---:|
| **Old** (English `_OFFENCE_HINTS`) | 14/16 = **88%** | **0/3 = 0%** | 3.0% |
| **New** (tiered, trimmed) | 16/16 = **100%** | 2/3 | **1.7%** |

- The new filter recalls **every** clear sexual-offence report, **including the regional ones
  the old filter structurally cannot match**, at a *lower* pass rate (it drops the old filter's
  noisy bare `assault`/`abuse`/`harass`, which matched non-sexual crime).
- The two non-recalled items are POCSO-**adjacent** secondary matters (a doctor's failure to
  report a minor's pregnancy; a pregnancy-diagnosis dispute) — not primary offence reports;
  Gemini's scope gate would reject them regardless.

## Cost

Pass rate **1.7%**. At ~600 crime-feed documents/day and ~$0.008/document, that is
**≈ $2.4/month** against the $10 cap — no cap raise needed. The per-source pass rate is
reported every run in `data/pipeline_health.json` and the heartbeat, and the §6 silent-nothing
guard fails the run loudly if >50 documents clear the pre-filter but 0 candidates come back.

## Enabling more languages

A media feed in a language **not** in `offence_filter.LANGUAGES_WITH_TERMS` (currently Hindi,
Telugu, Marathi, Tamil) must stay `enabled: false` — enabling it would produce silent zeros.
Bengali, Malayalam, Kannada and Gujarati stay disabled until their term sets are built + measured.
