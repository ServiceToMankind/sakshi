# Data Correction & Removal Requests

Sakshi — *Because the record must not forget.*

The record must be accurate, and it must be fair. This document explains how to
ask us to correct or remove data, what we will do, and how quickly. We take
these requests seriously and respond with care.

Sakshi is an open-source, static public-accountability record of **publicly
reported** sexual-assault cases in India, aggregated from public judicial
records and credible media. It is **not** a crime-rate statistic, **not** legal
advice, and **not** a substitute for official NCRB data. Every published data
point carries a citable public source.

---

## A note on victim safety, first

**We never ingest victim-identifying data at all** — it is not merely redacted.
Victim and survivor names, photos, addresses, family-member names,
school/workplace, exact ages, and any re-identifying detail are never written to
disk, committed, logged, or cached, and never enter git history. This is a
hard, automated guarantee enforced at the code level (see `sanitize.py` and
`pii_guard.py`), in keeping with Section 72 of the Bharatiya Nyaya Sanhita 2023
(formerly IPC 228A) and Section 23 of the POCSO Act 2012.

Because such data is **structurally incapable of existing in our system**, it
cannot leak from us. If you believe you have found victim-identifying
information anywhere in this project, treat it as a security incident and report
it immediately per [SECURITY.md](./SECURITY.md) — we will treat it as a
top-severity issue.

---

## What we correct

We welcome and act on requests to fix the public record, including:

* **Factual errors** — wrong district, wrong court, wrong offence sections,
  wrong FIR/CNR reference, mis-parsed dates, or an incorrectly linked source.
* **Status updates** — a case whose judicial status has changed (for example,
  moved from `UNDER_TRIAL` to `ACQUITTED`, `CONVICTED`, `QUASHED`, `CLOSED`, or
  `APPEAL_PENDING`) and where our record is stale.
* **Mis-attribution of an accused** — a name or label attached to the wrong
  case, or an accused name that does not appear in an official court record.
* **Duplicate or merged records** that should be split, or split records that
  should be merged.

Corrections are applied by re-running the pipeline against the corrected
source, not by hand-editing `data/`. Humans never hand-edit the data tree; this
keeps every published field traceable to a source.

## Removal-on-request policy

We support removal of a case record in the following circumstances:

1. **Acquitted or quashed cases.** Where the public court record shows a final
   status of `ACQUITTED` or `QUASHED`, the person named or referenced may request
   removal of the record. Acquittals and quashings are always rendered with equal
   prominence to other statuses; removal on request is offered in addition, in
   recognition of the presumption of innocence and the harm of a lingering
   record.
2. **Court-ordered removal.** Where any court of competent jurisdiction orders
   removal, redaction, or de-indexing of a matter, we will comply. Please include
   a reference to the order.
3. **Any suspected victim-identifying content.** Removed immediately and without
   precondition (see the note above).

Removal is honored even though our sources are public: the goal of this project
is civic accountability, not perpetual exposure of individuals cleared by the
courts.

## How to file a request

Choose whichever is easier for you:

* **GitHub issue (preferred for corrections):** open an issue using the
  **data-correction** template in this repository. The template prompts you for
  the fields we need.
* **Email (preferred for removals or anything sensitive):**
  **contact@stmorg.in**.

You do not need a GitHub account to email us. You do not need to be a lawyer,
and you do not need to explain more than you are comfortable sharing.

## What to include

To let us act quickly and verify against the source, please include as much of
the following as you have:

* **The case identifier** — our `id` (format `SKS-YYYY-XX-NNNNNN`), **or** the
  **CNR**, **or** the **FIR number + police station + district**.
* **What is wrong**, or **what you are asking us to remove**, in a sentence or
  two.
* **A source or reference** — for a status update, a link or citation to the
  court record; for a court-ordered removal, a reference to the order. If you
  cannot provide one, tell us anyway and we will verify against the official
  record ourselves.

Please do **not** include any victim-identifying detail in your request. We do
not need it and we will not store it.

## Our service level

* **Acknowledgement:** within **3 business days** of receiving your request.
* **Suspected victim-identifying content or a valid court order:** actioned as
  soon as possible, and always within **72 hours** of confirmation — these
  jump the queue.
* **Corrections and status updates:** verified against the source and, where
  confirmed, reflected in the next scheduled data run, typically within **7
  business days**.
* **Acquitted/quashed removal requests:** reviewed and, where confirmed,
  actioned within **7 business days**.

We will tell you what we did. If we decline a request, we will explain why and
tell you how to escalate.

## Escalation

If you are not satisfied with our response, or we have not replied within the
timelines above:

1. Reply to your original email or issue asking for escalation, or write again
   to **contact@stmorg.in** with "ESCALATION" in the subject line.
2. For a security or PII concern, follow [SECURITY.md](./SECURITY.md) directly.
3. You retain every legal remedy otherwise available to you; nothing in this
   document limits your rights.

We would rather correct the record than defend an error. Thank you for helping
us keep it accurate and fair.
