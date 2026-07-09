# Security Policy

Sakshi — *Because the record must not forget.*

We are grateful to security researchers who help us protect this project and,
above all, the people it touches. This document explains how to report a
vulnerability and what you can expect from us in return.

---

## Report privately — never in a public issue

**Do not open a public GitHub issue, pull request, or discussion for a security
vulnerability.** Public disclosure before a fix puts people at risk.

Instead, email **contact@stmorg.in** with the details. Please use a
subject line beginning with `SECURITY:`.

If you wish to encrypt your report, say so in a first, contentless email and we
will arrange a secure channel.

### What to include

* A description of the issue and its impact.
* Step-by-step reproduction, proof-of-concept, or the affected file/endpoint.
* The commit hash, URL, or deployed version affected, if known.

Please do **not** include any real victim-identifying data in your report. If
your finding *is* exposed personal data, describe **where** it appears and
**how** to reach it, but do not paste the data itself.

---

## Scope

In scope:

* **The data pipeline** — fetching, extraction (`extract/`), sanitization
  (`sanitize.py`), the PII guard (`pii_guard.py`), deduplication, validation,
  sharding, and the GitHub Actions that run them. Bypasses of the sanitizer or
  PII guard are especially important.
* **The static site** — the built frontend hosted on GitHub Pages, its service
  worker, and any client-side logic.
* **Supply chain** — dependency, build, or CI configuration issues that could
  lead to compromise or to PII disclosure.
* **Secrets handling** — any path by which `GEMINI_API_KEY` or another secret
  could be exposed.

### Accidental PII exposure is top severity

Any pathway by which victim- or survivor-identifying information could be
ingested, stored, logged, cached, committed, or served — whether or not it has
actually happened — is treated as a **top-severity security *and* legal
incident**. This project's core legal guarantee is that such data is never
ingested (per Section 72 of the Bharatiya Nyaya Sanhita 2023 and Section 23 of
the POCSO Act 2012). A break in that guarantee takes priority over every other
class of report and will be actioned immediately.

Out of scope:

* The content of published court records or media sources themselves (for the
  public record, use [TAKEDOWN.md](./TAKEDOWN.md) instead).
* Findings that require physical access, social engineering of maintainers, or
  denial-of-service via volumetric traffic.
* Reports from automated scanners with no demonstrated impact.

---

## Our response

* **Acknowledgement:** within **3 business days**.
* **Triage and initial assessment:** within **7 business days**, including a
  severity rating and expected remediation timeline.
* **Suspected PII exposure:** actioned immediately on confirmation, ahead of the
  timelines above.
* **Fix and disclosure:** we aim to remediate valid vulnerabilities within **90
  days**, and sooner for high-severity issues. We will keep you updated on
  progress and coordinate public disclosure with you once a fix is available.

We will credit you for your report if you would like to be credited, and respect
your preference to remain anonymous otherwise.

---

## Safe harbor

We consider good-faith security research to be a valued contribution, not a
hostile act. If you make a good-faith effort to comply with this policy, we will:

* Not pursue or support any legal action against you for your research.
* Work with you to understand and resolve the issue quickly.
* Recognize your contribution.

Good faith means: you avoid privacy violations and harm to people and the
service; you do not access, modify, exfiltrate, or retain data beyond the
minimum needed to demonstrate the issue; you do not intentionally access any
victim-identifying data; you give us a reasonable time to remediate before any
public disclosure; and you do not exploit the issue beyond proof of concept.

If you are uncertain whether an action is authorized, ask us first at
**contact@stmorg.in**. We would rather answer a question than see a
person put at risk.

---

## For non-security concerns

* To correct or remove a **data record**, see [TAKEDOWN.md](./TAKEDOWN.md).
* For **conduct** concerns, see
  [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).

Thank you for helping us keep the record accurate, fair, and safe.
