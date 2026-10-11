# Defect sweep — 1 August 2026

An offline sweep, run overnight, for the problems an earlier audit had pointed out:
two-letter state codes in text people read, records whose state or district couldn't be
worked out, and published summaries that fail the plain-English check. Here's what I
found. Nothing in this sweep was changed automatically.

## 1. State codes in children's case summaries: everywhere (needs a human-approved issue)

All **15** published summaries for children's cases showed the two-letter **state code**
instead of the full state name, for example `"…in Gurugram, HR (2026)…"`, `"…, TG…"`,
`"…, DL…"`, `"…, UP…"`. People see this, because the site shows `summary` exactly as it is.

- **Where:** the plain-template branch of `pipeline/sanitize.py::minor_summary`
  (`location = ", ".join((district, state))`). The **composer** branch
  (`minor_summary_compose`) already used only the district, so a child's case with two
  or more structured facts wasn't affected. Only the plain-template fallback showed the
  code.
- **Why I didn't fix it that night:** `sanitize.py` is a protected file (CLAUDE.md,
  section 2; it needs 100% branch coverage). The fix is a one-line **wording** change
  (turn the code into the full name using `pipeline/states`, or drop the state, since the
  district already says where). The overnight rules arguably allowed that as "wording",
  but changing a protected file and then rebuilding 15 records is a decision for me to
  make awake, not something to run unattended. I opened an issue to track it.
- **This isn't a broken privacy rule:** a state code or name is public and identifies no
  one. The POCSO Section 23 protections weren't affected. It's a readability problem.

> **Update:** fixed later in PR #123 (issue #115). The minor summary now turns the code
> into the full state name (`state_name` in `pipeline/sanitize.py`).

## 2. Two-letter codes on the website: clean

Every state shown in `site/src` goes through `format.js::stateName()` (the full name). No
raw `record.state` reaches text people read. (Only URL query parameters and filter
values use the code, which is correct.)

## 3. Records with an unknown state: none

Every published record's `state` is a recognised code
(`pipeline/states.CANONICAL_STATES`). The pipeline quarantines any record with an unknown
state, so none can be live.

## 4. The plain-English check: clean

`scripts/readability_guard.py` passes on every published adult's case summary (it runs as
part of `make check`). A newer step in the pipeline (#107) now also quarantines a *new*
hard-to-read summary before it can publish.

## 5. Already dealt with that night

- **South District / South Delhi** matching mix-up: the district clean-up no longer turns
  "South District" into "South Delhi" (#110). Whether to merge the two spellings (they
  belong to two separate children's cases with no case reference) was still an open
  question for me to decide.
- **Forgetful discovery** (records extracted from a headline or blurb that the pipeline
  never fetches again): the article-body fetcher is built, and switched OFF behind a
  setting in PR #112. Turning it on needs me to check a live before-and-after first.
