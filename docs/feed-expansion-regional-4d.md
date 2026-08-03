# Feed expansion — regional-language press (§4d, DRAFT)

**The single biggest coverage gap.** Most sexual-offence cases in India are reported in the
vernacular press and never appear in English. An English-only source list structurally cannot
see most of the country.

**Every feed ships `enabled: false`, and there is a HARD gate before any is enabled.**

## ⛔ Enablement gate (§4e) — do NOT skip

No non-English source may be flipped to `enabled: true` until, **for that language**:

1. The **multilingual PII guard** (`pipeline/pii_multilingual.py`, §4e) is **wired** into the
   protected gates — `dedupe.has_identity_detail` + `scripts/pii_guard` + `sanitize` — via a
   **human-approved issue** (CLAUDE.md §2). See `docs/multilingual-pii-guard-proposal.md`.
2. Extraction is **asserted** to output English for that script (assert, don't assume).
3. That language's native-script age patterns + romanized kinship/office/geo terms are tuned,
   and **fixture records prove the guard FIRES at 100% branch coverage**.

Until all three hold, the language's feeds stay disabled. Every active identity gate is an
English regex today; enabling a regional source before the guard fires runs the pipeline with
the **identity floor disabled** for its input — a Phase-0 breach.

## Hindi — wired (disabled), robots verified 2026-08-03

| Outlet | Feed URL | robots | feed |
|---|---|---|---|
| Dainik Bhaskar | `https://www.bhaskar.com/rss-v1--category-4587.xml` | ALLOW | 200 XML |
| Amar Ujala | `https://www.amarujala.com/rss/breaking-news.xml` | ALLOW | 200 XML |

Excluded (this pass): Navbharat Times (robots allow, feed URL 404 — needs the correct path).

## Other languages — candidate outlets (feed URLs to confirm; one PR per language)

Wire each **only** alongside that language's §4e guard extension + fixtures.

- **Telugu:** Eenadu, Andhra Jyothi, Namasthe Telangana. (Eenadu robots ALLOW but the tried
  feed URL was non-XML — find the correct RSS.)
- **Tamil:** Daily Thanthi, Dinamalar, Dinamani. (Dinamani robots **DISALLOW**.)
- **Marathi:** Lokmat, Sakal, Loksatta. (Lokmat robots ALLOW; feed URL to confirm.)
- **Bengali:** Anandabazar Patrika (robots **DISALLOW**), Bartaman.
- **Malayalam:** Malayala Manorama, Mathrubhumi. (Mathrubhumi robots ALLOW; feed URL to confirm.)
- **Kannada:** Prajavani (robots **DISALLOW**), Vijaya Karnataka.
- **Gujarati:** Divya Bhaskar (robots ALLOW; feed URL to confirm), Gujarat Samachar.
- **Odia:** Sambad, Dharitri. **Punjabi:** Ajit, Jagbani. **Assamese:** Asomiya Pratidin.

A `robots DISALLOW` is final — the pipeline never fetches a disallowed URL. Feed-URL discovery
for several outlets needs their homepage's `<link rel="alternate" type="application/rss+xml">`
or a published feed index; the values above are candidates, not confirmed, except where noted.

## Coverage honesty (§7)
Once a language is enabled, extend the Coverage page with **per-language** coverage so a reader
can see that (e.g.) Odisha is thin because we read one Odia outlet — not because Odisha is safe.
