# Security Policy

Sakshi — *Because the record must not forget.*

I'm grateful to anyone who helps protect this project and, above all, the people it
touches. This page explains how to report a security problem and what you can expect
from me in return.

---

## Please report privately, never in a public issue

**Don't open a public GitHub issue, pull request or discussion about a security
problem.** Making it public before it's fixed puts people at risk.

Instead, email **contact@stmorg.in** with the details, and start the subject line with
`SECURITY:`.

If you'd like to encrypt your report, send a first email saying so (with no details in
it), and I'll set up a secure channel with you.

### What to include

* What the problem is and what harm it could do.
* Step-by-step instructions to reproduce it, a proof of concept, or the affected file or
  page.
* The commit hash, URL or deployed version affected, if you know it.

Please **don't** include any real victim-identifying data in your report. If what you
found *is* exposed personal data, tell me **where** it appears and **how** to reach it,
but don't paste the data itself.

---

## What's covered

Covered:

* **The data pipeline**: fetching, extraction (`pipeline/extract/`), the sanitizer
  (`pipeline/sanitize.py`), the final personal-data check (`scripts/pii_guard.py`),
  deduplication, validation, writing the data files, and the GitHub Actions that run
  them. A way around the sanitizer or `pii_guard` matters most of all.
* **The static site**: the built website on GitHub Pages, its service worker, and any
  code that runs in the browser.
* **The supply chain**: problems with dependencies, the build or CI setup that could lead
  to a compromise or to personal data getting out.
* **Secrets**: any way `GEMINI_API_KEY`, `SCRAPE_BOT_TOKEN`, `INDIANKANOON_API_TOKEN` or
  another secret could be exposed.

### Personal data getting out is the most serious problem

Any way that information identifying a victim or survivor could be taken in, stored,
logged, cached, committed or served, whether or not it has actually happened, is treated
as the **most serious kind of security *and* legal incident**. The core legal promise of
this project is that such data is never collected (under Section 72 of the Bharatiya
Nyaya Sanhita 2023 and Section 23 of the POCSO Act 2012). Anything that breaks that
promise comes before every other kind of report and is dealt with immediately.

Not covered:

* What published court records or news sources themselves say (for the public record,
  use [TAKEDOWN.md](./TAKEDOWN.md) instead).
* Anything that needs physical access, tricking maintainers, or flooding the site with
  traffic.
* Reports from automated scanners that don't show any real impact.

---

## What I'll do

* **Acknowledge** your report within **3 business days**.
* **Assess** it within **7 business days**, including how serious it is and when I expect
  to fix it.
* **Suspected exposure of personal data:** dealt with immediately once confirmed, ahead
  of the times above.
* **Fix and disclosure:** I aim to fix real problems within **90 days**, and sooner for
  serious ones. I'll keep you updated and agree with you on when to make it public once a
  fix is out.

I'll credit you for the report if you'd like that, and respect your wish to stay
anonymous if you don't.

---

## Safe harbour

I see good-faith security research as a real contribution, not an attack. If you make a
good-faith effort to follow this policy, I will:

* Not take or support any legal action against you for your research.
* Work with you to understand and fix the problem quickly.
* Recognise your contribution.

Good faith means: you avoid privacy violations and harm to people and the service; you
don't access, change, copy out or keep data beyond the minimum needed to show the
problem; you don't deliberately access any victim-identifying data; you give me a
reasonable time to fix it before saying anything publicly; and you don't use the problem
beyond a proof of concept.

If you're not sure whether something is allowed, ask me first at **contact@stmorg.in**.
I'd much rather answer a question than see someone put at risk.

---

## For anything that isn't a security problem

* To correct or remove a **data record**, see [TAKEDOWN.md](./TAKEDOWN.md).
* For **conduct** concerns, see
  [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).

Thank you for helping keep the record accurate, fair and safe.
