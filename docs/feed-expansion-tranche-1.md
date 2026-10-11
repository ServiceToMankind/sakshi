# Adding feeds — first batch (draft, 1 August 2026)

**Status when written:** a draft for me to decide on, prepared overnight. **Every feed
was added switched off (`enabled: false`)**, so the decision in the morning would be a
one-line change per source. Nothing was turned on that night; the overnight rules didn't
allow it.

> **Update:** I turned on both of these feeds on 12 August 2026 (`times-of-india-top`
> and `hindustan-times-india` in `sources.yml`). The legal and terms-of-service review is
> still marked as pending there.

I checked the `robots.txt` answers live on **1 August 2026** for the project's
User-Agent (`sakshi-bot/1.0 (+https://github.com/ServiceToMankind/sakshi)`), using the
same `RobotFileParser` check the pipeline's `PoliteClient` uses. A feed only counts as a
candidate if robots.txt **ALLOWS** it **and** the URL returns a valid RSS or Atom
document.

## Feeds to consider turning on (added to `sources.yml`, switched off)

| Outlet | Feed URL | robots.txt | Feed | Terms |
|---|---|---|---|---|
| The Times of India | `https://timesofindia.indiatimes.com/rssfeedstopstories.cms` | **ALLOW** | 200, XML | The RSS feed is publicly syndicated; a full legal review of the terms is still to do before turning it on |
| Hindustan Times | `https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml` | **ALLOW** | 200, XML | The RSS feed is publicly syndicated; a full legal review of the terms is still to do before turning it on |

Both are national feeds (top stories / India news), added to the `national:` block.
They cover everything, so expect few sexual-offence cases among them. The extractor's
`in_scope` check and the ordering by offence relevance already deal with that.

## Outlets checked and left out

| Outlet | Reason (checked 1 August 2026) |
|---|---|
| Scroll.in | robots.txt **DISALLOWS** our User-Agent |
| Deccan Herald | robots.txt **DISALLOWS** |
| The News Minute | robots.txt **DISALLOWS** |
| The Telegraph India | robots.txt **DISALLOWS** |
| Deccan Chronicle | robots.txt **DISALLOWS** |
| The Print | robots.txt **ALLOWS**, but `/feed/` didn't return a valid RSS document. It needs the right feed address before it can be a candidate |

A DISALLOW is final: the pipeline never fetches a URL that robots.txt disallows, so these
can't be added unless the outlet's robots.txt changes.

## Before turning any feed on (my checklist)

1. **A legal review of the terms** of each outlet for automated RSS use (the Terms column
   above is a placeholder, not a legal opinion).
2. **Check robots.txt again** at the time of turning it on (policies change).
3. **Set `enabled: true`** for the approved feeds only (one line each), then watch the
   first run's heartbeat (fetched, extracted, in scope, cost) and the size of the
   possible-duplicates list and the review queue. The overnight rules paused a batch if
   the list of possible duplicates went over 25 or a pair sat there for more than 7 days.
4. **Which state a case belongs to.** These national feeds aren't tied to any one state;
   a record's state comes from extraction, and `coverage.json` counts it honestly per
   state.

## Nothing about the protections changes

Adding a feed only changes *what we fetch*, never a protection. Every fetched record still
goes through fetch, extract, sanitize, dedupe, verify and `pii_guard`, unchanged. Accused
names from the media stay withheld (`name_public_court_record: null`); children's cases
are reduced to the minimal form and never published automatically.
