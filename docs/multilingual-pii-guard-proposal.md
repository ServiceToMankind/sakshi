# Multilingual personal-data guard — now wired in

**Status: wired in (issue #136).** `pipeline/pii_multilingual.py` is no longer a proposal;
it's an enforced check. It runs inside the two protected checks:
- **`pipeline/sanitize.py`**: `sanitize_string` removes any non-English-script text from
  every field (this is how we make sure the output is English), and `sanitize_record`
  removes romanised family, office and below-district place words from the
  model-written **text** fields (title and summary). The romanised words are only removed
  from that text, so a place name in a citation URL (for example
  `.../rampur-gaon-case/`) is never mangled.
- **`scripts/pii_guard.py`**: the check before anything ships confirms that NO published
  field contains a non-English-script character (any field), and NO text field contains a
  romanised identity word. It applies to published files (the `_review` quarantine is left
  out, as it is for the age and occupation checks).

Both stay at **100% branch coverage**, and the test records for each script in
`test_pii_multilingual.py` prove each kind of leak is caught. **A new source still starts
switched off (`enabled: false`).** The guard removes the blocker for regional-language
sources, but turning a language on is still my decision, one PR per language.

> **Update:** I turned on the Hindi, Telugu, Marathi and Tamil feeds on 12 August 2026
> (`sources.yml`). Native-script age patterns now exist for Hindi, Telugu, Tamil,
> Bengali, Malayalam, Kannada, Gujarati, Punjabi and Odia (`NATIVE_SCRIPT_AGE_PATTERNS`
> in `pipeline/pii_multilingual.py`).

## Why regional-language sources had to wait for this

Every identity check we had was an **English regular expression**: the age patterns
(`pii_constants.AGE_EXPRESSION_PATTERNS`), the personal-data patterns, the occupation
scrubber, the `dedupe.has_identity_detail` backstop, and `scripts/pii_guard`. **None of
them catch anything in Devanagari, Telugu, Tamil or Bengali script, and none catch the
*romanised* Indian-language words that survive an extraction into English.** Turning on
a Hindi or Telugu source back then would have run the pipeline with the identity
protections **silently switched off** for most of its input. That would break the core
privacy rules, so regional-language sources were firmly blocked until this was done.

## What it detects (`find_multilingual_pii`)

1. **Romanised family words** (`romanized_kinship_relation`): `chacha`, `jija`,
   `mama garu`, and so on. These state the victim–accused **relationship**, which is a
   forbidden field (CLAUDE.md, section 1a), whichever way round it's written. Words that
   are also ordinary English (`mama`, `anna`, `para`) are **left out** here and added back
   per language, only when that language is switched on.
2. **Local office titles** (`local_office_title`): `sarpanch`, `patwari`, `mukhiya`. A
   village office holder is as identifying as a name.
3. **Places smaller than a district** (`subdistrict_geography`): `gaon`, `thanda`,
   `basti`, `tola`. These name a locality finer than the district, and the district is the
   finest place we ever store.
4. **Ages written in a native script** (`native_age:<lang>`): a further layer, in case raw
   source text leaks into a field. When I first wrote this, only **Hindi** (Devanagari
   `साल`/`वर्ष`) was filled in, as the first worked example.

A match is a signal to **send the record for review or quarantine** (we lean towards
review: a match never leaks anything, and a false alarm just sends a record to a person),
not something to scrub.

## How I proposed to wire it in (PROTECTED: needs a human-approved issue, CLAUDE.md section 2)

These changes touch protected files, so they couldn't be made unattended:

1. **`pipeline/dedupe.py`**: add `find_multilingual_pii(...)` to the
   `has_identity_detail` backstop, so a record whose text contains a family relationship,
   an office title or a sub-district place goes to `_review` (like the existing age and
   relationship checks).
2. **`scripts/pii_guard.py`**: check that no *published* file's text fields contain any of
   these markers (the final check before shipping), extending the `matched_*` scanning.
3. **`pipeline/sanitize.py`**: extend the `AGE_EXPRESSION_PATTERNS` scanning to the
   native-script age patterns for each language that's switched on.
4. Leave the forbidden-field list and `additionalProperties: false` unchanged (this adds
   checks on VALUES, never a new field).

What was actually wired in under issue #136 is described at the top: the sanitizer and
`pii_guard`.

## Turning on a language: one PR per language

A language is ready to switch on **only** when, in one PR:
1. `LANGUAGES` includes it **and** it has an entry in `NATIVE_SCRIPT_AGE_PATTERNS` (checked
   by a native speaker), and its family, office and place words are tuned so they don't
   raise false alarms.
2. **It's tested that extraction returns English** for that script (tested, not assumed).
3. **Test records in that script prove the guard catches them**, with 100% branch coverage
   on the wired checks.
4. Only then may that language's sources go from `enabled: false` to `enabled: true`.

Until all four are true for a language, its sources stay switched off and wait.
