# Multilingual PII guard — WIRED (§4e)

**Status: WIRED (issue #136).** `pipeline/pii_multilingual.py` is now the enforced guard, not a
proposal. It is wired into the two protected gates:
- **`pipeline/sanitize.py`** — `sanitize_string` scrubs any native-script span from every field
  (the English-output enforcement), and `sanitize_record` scrubs romanized kinship/office/
  sub-district markers from the model **prose** fields (title/summary). Romanized markers are
  prose-only so a citation URL slug's place name (e.g. `.../rampur-gaon-case/`) is never mangled.
- **`scripts/pii_guard.py`** — the ship-time scan asserts NO published field carries a
  native-script character (any field) and NO prose field carries a romanized identity marker,
  gated to published shards (the `_review` quarantine is exempt, as for age/occupation).

Both stay at **100% branch coverage**; per-script fixtures in `test_pii_multilingual.py` prove
each vector fires. **A source still lands `enabled: false`** — the guard clears the §4e
*blocker*, but enabling remains the operator's call, one PR per language (D5).

## Why this blocks §4d

Every active identity gate is an **English regex**: the age patterns
(`pii_constants.AGE_EXPRESSION_PATTERNS`), the PII value patterns, the occupation scrubber, the
`dedupe.has_identity_detail` backstop, `scripts/pii_guard`. **None fires on Devanagari / Telugu
/ Tamil / Bengali script, and none fires on the *romanized* Indian-language terms that survive
an English-output extraction.** Enabling a Hindi or Telugu source today would run the pipeline
with the identity floor **silently disabled** for most of its input. That is a Phase-0 breach,
so §4d is hard-blocked on this.

## What the proposal detects (`find_multilingual_pii`)

1. **Romanized kinship** (`romanized_kinship_relation`) — `chacha`, `jija`, `mama garu`, … —
   which state the victim–accused **relationship**, a forbidden field (§1a), regardless of
   direction. English-ambiguous terms (`mama`, `anna`, `para`) are **excluded** here and re-added
   per language behind a language guard.
2. **Local office titles** (`local_office_title`) — `sarpanch`, `patwari`, `mukhiya` — a village
   office holder is as identifying as a name.
3. **Sub-district geography** (`subdistrict_geography`) — `gaon`, `thanda`, `basti`, `tola` — a
   locality finer than the district (the finest we ever store).
4. **Native-script age** (`native_age:<lang>`) — defence-in-depth if raw source text leaks into a
   field. Only **Hindi** (Devanagari `साल`/`वर्ष`) is filled in as the worked first example.

A hit is a **review/quarantine** signal (fail toward review — a hit never leaks, a false positive
just sends a record to a human), not a scrub.

## Wiring (PROTECTED — needs a human-approved issue, CLAUDE.md §2)

These changes touch protected files and must not be made unattended:

1. **`pipeline/dedupe.py`** — add `find_multilingual_pii(...)` to the `has_identity_detail`
   backstop so a record whose text carries a kinship relationship / office title / sub-district
   locality routes to `_review` (like the existing age/relationship checks).
2. **`scripts/pii_guard.py`** — assert no *published* shard's free-text fields contain a
   multilingual vector (the final ship-time gate), extending `matched_*` scanning.
3. **`pipeline/sanitize.py`** — extend `AGE_EXPRESSION_PATTERNS` scanning to the native-script
   age patterns for each enabled language.
4. Keep the forbidden-field list and `additionalProperties:false` unchanged (this adds VALUE
   detection, never a new field).

## Per-language enablement — one PR per language (§4d)

A language is ready to enable **only** when, in one PR:
1. `LANGUAGES` covers it **and** its `NATIVE_SCRIPT_AGE_PATTERNS` entry exists (native speaker
   reviewed), and its kinship/office/geo terms are tuned for false positives.
2. **Extraction is asserted to output English** for that script (assert, don't assume).
3. **Fixture records in that script prove the guard FIRES**, at 100% branch coverage on the
   wired gates.
4. Only then may that language's sources flip from `enabled: false` to `enabled: true`.

Until all four hold for a language, its sources stay disabled — the parking pattern.
