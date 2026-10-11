# Adding feeds — regional-language press (draft, August 2026)

**This is the biggest gap in our coverage.** Most sexual-offence cases in India are
reported in the regional-language press and never appear in English. A list of English
sources alone simply can't see most of the country.

**Every feed was added switched off (`enabled: false`), with a firm condition to meet
before any of them could be turned on.**

> **Update:** the multilingual personal-data guard described below was wired in later
> (issue #136; see `docs/multilingual-pii-guard-proposal.md`). On 12 August 2026 I turned
> on the Hindi, Telugu, Marathi and Tamil feeds in `sources.yml`. The Bengali, Gujarati,
> Kannada and Malayalam feeds are set up but still switched off, because the offence
> filter doesn't have word lists for those languages yet (see
> `docs/offence-filter-recall.md`).

## ⛔ The condition for turning a language on (don't skip it)

No non-English source may be set to `enabled: true` until, **for that language**:

1. The **multilingual personal-data guard** (`pipeline/pii_multilingual.py`) is **wired**
   into the protected checks (`dedupe.has_identity_detail`, `scripts/pii_guard` and
   `sanitize`) through a **human-approved issue** (CLAUDE.md, section 2). See
   `docs/multilingual-pii-guard-proposal.md`.
2. It's **tested** that extraction returns English for that script (tested, not assumed).
3. That language's native-script age patterns and romanised family, office and place
   words are tuned, and **test records prove the guard catches them, with 100% branch
   coverage**.

Until all three are true, that language's feeds stay off. At the time of writing, every
active identity check was an English regular expression. Turning on a regional source
before the guard catches anything would run the pipeline with the **identity protections
switched off** for that input. That would break the core privacy rules.

## Hindi — set up (switched off), robots.txt checked 3 August 2026

| Outlet | Feed URL | robots | feed |
|---|---|---|---|
| Dainik Bhaskar | `https://www.bhaskar.com/rss-v1--category-4587.xml` | ALLOW | 200 XML |
| Amar Ujala | `https://www.amarujala.com/rss/breaking-news.xml` | ALLOW | 200 XML |

Left out this time: Navbharat Times (robots.txt allows it, but the feed URL returns 404;
it needs the right address).

## Other languages — possible outlets (feed URLs still to confirm; one PR per language)

Add each one **only** together with that language's extension to the guard and its tests.

- **Telugu:** Eenadu, Andhra Jyothi, Namasthe Telangana. (Eenadu's robots.txt allows it,
  but the feed URL I tried wasn't XML; I need the right RSS address.)
- **Tamil:** Daily Thanthi, Dinamalar, Dinamani. (Dinamani's robots.txt **DISALLOWS**.)
- **Marathi:** Lokmat, Sakal, Loksatta. (Lokmat's robots.txt allows it; feed URL to confirm.)
- **Bengali:** Anandabazar Patrika (robots.txt **DISALLOWS**), Bartaman.
- **Malayalam:** Malayala Manorama, Mathrubhumi. (Mathrubhumi's robots.txt allows it;
  feed URL to confirm.)
- **Kannada:** Prajavani (robots.txt **DISALLOWS**), Vijaya Karnataka.
- **Gujarati:** Divya Bhaskar (robots.txt allows it; feed URL to confirm), Gujarat Samachar.
- **Odia:** Sambad, Dharitri. **Punjabi:** Ajit, Jagbani. **Assamese:** Asomiya Pratidin.

A robots.txt DISALLOW is final: the pipeline never fetches a disallowed URL. Finding the
feed address for several outlets needs their homepage's
`<link rel="alternate" type="application/rss+xml">` or a published list of feeds. The
outlets above are candidates, not confirmed, except where I've said otherwise.

> **Update:** the regional outlets that ended up in `sources.yml` are Dainik Bhaskar and
> Amar Ujala (Hindi), Namasthe Telangana and the Telugu daily Sakshi, Lokmat and Sakal
> (Marathi), Daily Thanthi and Hindu Tamil Thisai (Tamil), all switched on; and Ei Samay
> and Sangbad Pratidin (Bengali), Divya Bhaskar (Gujarati), Kannada Prabha (Kannada) and
> Mathrubhumi (Malayalam), all switched off.

## Being honest about coverage
Once a language is on, the Coverage page should show coverage **per language**, so a
reader can see that (for example) Odisha looks thin because we read only one Odia outlet,
not because Odisha is safe.
