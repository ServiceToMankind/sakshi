# Asking for a correction or a removal

Sakshi — *Because the record must not forget.*

The record has to be accurate, and it has to be fair. This page explains how to ask me
to correct or remove something, what I'll do, and how quickly. I take every one of these
requests seriously.

Sakshi is an open-source, static record of **publicly reported** sexual-offence cases in
India, gathered from public court records and credible media. It is **not** a crime
statistic, **not** legal advice, and **not** a substitute for official NCRB data. Every
published fact carries a public source you can check.

---

## First, about victims' safety

**We never collect anything that identifies a victim.** It isn't collected and then
hidden; it is never collected at all. Victim and survivor names, photos, addresses,
family members' names, school or workplace, exact ages, and any other detail that could
identify them are never written to disk, committed, logged or cached, and never enter
git history. The code enforces this automatically (see `pipeline/sanitize.py` and
`scripts/pii_guard.py`), in line with Section 72 of the Bharatiya Nyaya Sanhita 2023
(formerly IPC 228A) and Section 23 of the POCSO Act 2012.

Because the system is built so this data has nowhere to live, it shouldn't be able to
leak from us. If you think you've found anything that identifies a victim anywhere in
this project, please treat it as a security incident and report it straight away as
described in [SECURITY.md](./SECURITY.md). I'll treat it as the most serious kind of
problem.

---

## What I'll correct

I welcome requests to fix the public record, including:

* **Factual errors**: the wrong district, court, offence sections or FIR/CNR reference,
  a date read wrongly, or a source linked to the wrong case.
* **Status updates**: a case whose court status has changed (for example from
  `UNDER_TRIAL` to `ACQUITTED`, `CONVICTED`, `QUASHED`, `CLOSED` or `APPEAL_PENDING`)
  where our record is out of date.
* **An accused attached to the wrong case**: a name or label on the wrong record, or an
  accused name that doesn't appear in an official court record.
* **Records wrongly merged or split**: two cases joined into one that should be
  separate, or one case split into two that should be joined.

## How a correction is made

Nobody edits the `data/` folder by hand; the pipeline rebuilds it. Once I've confirmed a
correction, I make it in one of two ways:

1. **Reading the source again (preferred).** If the corrected fact is in a public source
   that's still online, the pipeline reads it again and the record updates itself. Every
   field stays linked to a citation.
2. **A reviewed correction file** (`corrections/<record-id>.yml`) for fixes the pipeline
   can't make on its own: two cases it merged and can't separate again, or a summary
   whose source article has dropped off the feed and can't be read again. Each correction
   file is committed to git, named after the record's `id`, and records **who** wrote
   it, **when**, **why**, and the **evidence** it relies on, so every correction can be
   checked. A correction can either:
   * **quarantine** the record (take it off the public site and into review), or
   * **override specific fields** (for example, fix a district or move a status
     forward). Overrides are applied *before* the sanitizer and validator run, so a
     corrected value still has to pass every check. A correction can **never** set a
     field that identifies a victim, an `id`, or the `minor_involved` flag; those are
     refused outright. A corrected record shows a **"Corrected"** label on the site, and
     the reason lives in the committed correction file.

Correction files are checked against
[`schemas/correction.schema.json`](./schemas/correction.schema.json) and explained in
[`corrections/README.md`](./corrections/README.md).

## When I'll remove a record

I'll remove a case record in these situations:

1. **Acquitted or quashed cases.** If the public court record shows a final status of
   `ACQUITTED` or `QUASHED`, the person named or referred to can ask for the record to be
   removed. Acquittals and quashed cases are always shown with the same prominence as
   every other status. Removal on request is offered on top of that, because of the
   presumption of innocence and the harm a lingering record can do.
2. **A court orders it.** If any court with the authority to do so orders a matter
   removed, redacted or de-indexed, I'll comply. Please include a reference to the order.
3. **Anything that might identify a victim.** Removed immediately, no conditions (see
   the note above).

I honour removals even though our sources are public. The point of this project is
accountability, not keeping people the courts have cleared in the public eye forever.

## How to send a request

Use whichever is easier for you:

* **A GitHub issue (best for corrections):** open an issue with the
  **Data correction / removal** form in this repository. It asks for everything I need.
* **Email (best for removals or anything sensitive):**
  **contact@stmorg.in**.

You don't need a GitHub account to email. You don't need to be a lawyer, and you don't
need to explain more than you're comfortable sharing.

## What to include

So I can act quickly and check against the source, please include as much of this as
you have:

* **Which case**: our `id` (format `SKS-YYYY-XX-NNNNNN`), **or** the **CNR**, **or** the
  **FIR number, police station and district**.
* **What's wrong**, or **what you'd like removed**, in a sentence or two.
* **A source or reference**: for a status update, a link to or citation of the court
  record; for a court-ordered removal, a reference to the order. If you don't have one,
  tell me anyway and I'll check the official record myself.

Please **don't** include anything that identifies a victim in your request. I don't need
it and I won't store it.

## How quickly I'll respond

* **Acknowledgement:** within **3 business days** of getting your request.
* **Anything that might identify a victim, or a valid court order:** handled as soon as
  possible, and always within **72 hours** of confirming it. These go to the front of the
  queue.
* **Corrections and status updates:** checked against the source and, if confirmed,
  reflected in the next scheduled data run, usually within **7 business days**.
* **Removal requests for acquitted or quashed cases:** reviewed and, if confirmed, acted
  on within **7 business days**.

I'll tell you what I did. If I turn a request down, I'll explain why and tell you how to
take it further.

## Taking it further

If you're not happy with my response, or I haven't replied within the times above:

1. Reply to your original email or issue and ask for it to be escalated, or write again
   to **contact@stmorg.in** with "ESCALATION" in the subject line.
2. For a security or personal-data concern, go straight to [SECURITY.md](./SECURITY.md).
3. You keep every legal remedy you'd otherwise have. Nothing on this page limits your
   rights.

I'd rather correct the record than defend a mistake. Thank you for helping keep it
accurate and fair.
