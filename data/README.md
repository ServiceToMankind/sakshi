# data/ — the record itself, written by the pipeline

**Everything in this folder is written by the Sakshi pipeline. Please don't edit any file
here by hand.**

The whole `data/` tree is rebuilt the same way on every run. Files are written safely
(to a temporary file first, checked, then renamed into place), so a run that fails
halfway leaves the last good version untouched, and running it again is always safe. A
hand edit would be overwritten on the next run, and worse, it would skip the sanitizer
and the personal-data checks that every published record has to pass. If a record is
wrong, fix the source or the pipeline, or add a file in [`../corrections/`](../corrections/),
never the data file.

## License

Everything in `data/` is published under the **Open Database License (ODbL) v1.0**. (The
project's *code* is MIT; the *data* is ODbL. See the repository root for the full terms.)

## What's published

These files are copied to the website on every deploy.

### `summary.json`
What the front page loads first. Totals only, never full records:
- `generated_at`: when the run happened (ISO-8601)
- `total`: the number of published cases
- `status_counts`: cases per court status (`FIR_FILED`, `UNDER_TRIAL`, and so on)
- `state_counts`: cases per 2-letter state/UT code
- `monthly_trend`: case counts for each of the last 24 months
- `top_longest_pending`: the 10 cases waiting longest for justice, each with **only**
  `id`, `district`, `days_since_reported` and `incident_reported_date`. Only an adult's
  case that is still open, has a day-precise date, and carries a court reference (a CNR or
  an FIR number) can appear here, because a claim that a case is still waiting is only
  honest if its status can be checked again. A child's case never appears.
- `severity_counts` and `aggravated_total`: cases per plain-language severity label,
  worked out only from the public charge sections
- `scale`: the running total, how many cases entered the record this week, and a count
  per day for the last 120 days. These dates are when *we recorded* a case, not when it
  happened.

**`summary.json` must stay under 50 KB.** The pipeline refuses to write a bigger one, and
CI checks it too. It's the first thing the site loads, and the site keeps a copy so the
front page still works offline.

The district scorecard used to live in this file, capped at 120 rows. India has about
780 districts, so it outgrew that, and real cases went missing from the scorecard. It now
has its own file, `jurisdictions.json`.

### `jurisdictions.json`
The scorecard for every district we have a case in, with **no cap**, busiest first. Each
row has the `state`, `district`, `total`, `under_trial` (and `under_trial_pct`),
`convictions`, `acquittals` (acquitted and quashed together), and, when it isn't zero,
`pre_chargesheet` (cases where an FIR was filed but no chargesheet followed). The
`median_pending_days` and `longest_pending` figures use the same honest rule as
`top_longest_pending` above, so a district with no such case shows `null`. That's a
safeguard, not missing data. `scripts/counts_guard.py` checks that the rows add up to
the total.

### `recent.json`
The 50 most recently *listed* cases (newest `first_published` first), so the front page
doesn't have to open every data file. Each entry carries only what the feed shows: the
`id`, title, summary, state, district, category, status, charge sections, dates, whether
a child was involved, the first publisher, whether it was verified, and whether it has
been traced to a court record.

### `coverage.json`
Where we look, and where we don't yet. For every state and union territory it gives the
number of active sources, the number of published cases, and whether it is a
`declared_gap` (a place we know we don't cover yet). It also gives the *trackability*
rate: the share of cases with a court reference whose status can be checked again. The
Coverage page on the site is built from this file.

### `pipeline_health.json`
Counts from the last run, per source: documents fetched, skipped by the offence filter,
extracted, published, held and quarantined, with the reason for each drop. It also shows
how each court source narrowed its listing down to the judgments worth reading. Counts
and publisher names only, never case text.

### `index.json`
The list of every data file, so the site never has to guess a file name and get a 404.
Each entry gives the file's path, state, year, number of records and size in bytes:

```
{"generated_at": "...", "shards": [
  {"path": "2026/TG.json", "state": "TG", "year": 2026, "records": 0, "bytes": 0}
]}
```

### `{YYYY}/{STATE}.json`
The full records, one file per year and state, newest first. `{STATE}` is the 2-letter
Indian state/UT code (TG, AP, MH, DL, KA, ...). The shape of a record is set by
`schemas/case.schema.json`, which is the one source of truth for it.

**Splitting large files:** if a file would go over 500 KB, it is split into
`{STATE}-p2.json` (then `-p3.json`, and so on), and every part is listed in `index.json`.

### `_merge_review/candidates.json`
Groups of published cases that *might* be the same case, for a person to decide on. The
pipeline never merges these on its own. The file holds only record IDs, the state,
district and category, and why they look alike. An empty list means there's nothing to
check.

## What isn't published

### `_needs_review/`
Records that passed every check but aren't allowed to publish without a person looking
first (`pipeline/gates.py`). For example: a case that names an accused, even from a court
record; a case whose only source is a live blog; one whose confidence is between 0.80 and
0.85; one where POCSO charges don't match the minor flag; or a child's case that the
verification step hasn't approved.
- `queue.json` is the current held list. Each record in it has been through the sanitizer
  and `pii_guard` like any other. It is committed to git so the data PR shows it, but the
  deploy **never copies it to the website**.
- `approved.json` lists the source URLs of held records I've reviewed and approved. An
  approved record still goes through the full last gate, and a child's case stays in its
  minimal form.

### `_meta/`
Bookkeeping, never shown on the website.
- `serials.json` remembers the highest case number used for each year and state, so an
  old ID is never given to a new case. It is committed with each data update.
- `last_checked.json` records the date each case was last looked at. It stays out of the
  public record, so cases don't look as if they change every day.
- `processed.json` (the document ledger) and `spend.json` (the month's Gemini spend, in
  dollars only) live on the separate `ledger-state` branch, not on `main`. See
  CONTRIBUTING.md.

### `_review/`: quarantine (never committed, never published)
Anything the pipeline is less than 80% sure about (`confidence < 0.8`), anything it
couldn't match cleanly against an existing case, and anything a correction file has taken
off the site goes to `data/_review/`. This folder is in `.gitignore`, so it is never
committed, and the deploy leaves it out, so it never reaches the website. It is saved
with that run's logs for 14 days so I can look at it. Nothing leaves quarantine without a
person deciding. If more than 20 records land here in one run, the daily job opens an
issue.

## What this folder never contains

The victim's identity is **never collected**: not hidden after the fact, never written at
all. Matching is done on the case (FIR / CNR / police station / district / date /
court), never on anything about a person. Accused names appear only when they are in an
official court record. See the rules in the repository root and
`pipeline/sanitize.py` / `scripts/pii_guard.py` for how this is enforced.
