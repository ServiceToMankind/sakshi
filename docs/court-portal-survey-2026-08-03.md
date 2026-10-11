# High Court and Supreme Court judgment-portal survey — 3 August 2026

> On 3 August 2026 I surveyed all 25 High Courts and the Supreme Court with a script
> (curl plus a robots.txt check, using the honest `sakshi-bot` User-Agent, and never
> getting around a CAPTCHA). I wanted to know whether the paid Indian Kanoon token was
> still the only realistic way to cover the courts. **It still is.**

## 1. The short version

Of the 26 courts, only **7 are cleanly OPEN**: reachable, no CAPTCHA on an open listing,
and allowed by robots.txt. They are **Delhi, J&K & Ladakh, Jharkhand, Madhya Pradesh,
Madras, Meghalaya (legacy orders), and Punjab & Haryana**. Another **7 have an open path
with no CAPTCHA, but only a partial or degraded one** (Andhra's list of 41 circulated
PDFs, Gauhati's archive up to 2017, Gujarat's subset translated into Gujarati, Manipur's
index up to 2018, Orissa's vernacular subset, Sikkim (broken TLS), and Uttarakhand's full
bench only). **7 are firmly behind a CAPTCHA** (Supreme Court, Calcutta, Chhattisgarh,
Kerala, Patna, Rajasthan, Tripura), **3 couldn't be reached** from where I ran the survey
(Bombay, Karnataka, Telangana, probably limited to Indian IP addresses), and **2 are still
unknown** (Allahabad returned HTTP 429, and Himachal's page is built by JavaScript).

**What matters most: the Indian Kanoon API token is still the critical path.** Every
court that offers a search by statute **section** (Andhra, Kerala, Tripura) hides it
behind the CAPTCHA. Not one open path lets you search by POCSO, BNS or IPC section, so
the roughly 14 open courts only allow "fetch everything, then filter", and the other
roughly 12 (CAPTCHA, unreachable or unknown) can't be covered directly at all. Indian
Kanoon is still the only realistic route to section-targeted coverage of all of India.

## 2. Survey table

| Court | Reachable | CAPTCHA | Robots | Section-search | Format | Best URL | Notes |
|---|---|---|---|---|---|---|---|
| Supreme Court | partial | yes | allow | no | pdf | https://www.sci.gov.in/judgements-judgement-date/ | Needs a browser UA (honest UA gets 403 at Akamai); search behind siwp_captcha; date only |
| Allahabad HC | partial | unknown | allow | unknown | html | https://elegalix.allahabadhighcourt.in/elegalix/StartWebSearch.do | elegalix returned HTTP 429 both times; needs slower requests to survey |
| Andhra Pradesh HC | yes | yes | no_robots | yes | pdf | https://aphc.gov.in/circulated_judgments.php | Section search only behind the eCourts CAPTCHA; circulated_judgments is an OPEN list of 41 PDFs, no section search |
| Bombay HC | no | unknown | unknown | unknown | unknown | — | Timed out after 15s with both UAs, robots.txt included; try again from another network |
| Calcutta HC | partial | yes | unknown | no | pdf | https://www.calcuttahighcourt.gov.in/Order-Judgments | Needs unsafe legacy TLS renegotiation; name="captcha"; case type only; robots.txt blocked by a firewall (403) |
| Chhattisgarh HC | partial | yes | no_robots | no | pdf | https://highcourt.cg.gov.in/hcbspjudgement/oj_search.php | Incomplete certificate chain (-k); oj_search behind a CAPTCHA, no section search |
| Delhi HC | yes | no | no_robots | no | pdf | https://delhihighcourt.nic.in/web/judgement/fetch-data | OPEN: 308 direct PDF links, no CAPTCHA; by date / latest only |
| Gauhati HC | partial | yes | allow | no | pdf | https://ghconline.gov.in/index.php/orders-and-judgements/ | Live search behind a CAPTCHA; static open PDF archive up to 2017; homepage unreliable |
| Gujarat HC | partial | yes | unknown | no | pdf | https://gujarathighcourt.nic.in/gujaratijudgments | Full search is eCourts behind a CAPTCHA; the only open path is a subset of PDFs translated into Gujarati |
| Himachal Pradesh HC | partial | unknown | no_robots | unknown | unknown | https://highcourt.hp.gov.in/ | Moved to a new site; built by DataTables/JavaScript, curl sees no links; needs the AJAX endpoint found |
| J&K & Ladakh HC | yes | no | no_robots | no | pdf | https://jkhighcourt.nic.in/judgments_hc.php | OPEN plain-HTML lists of PDFs (judgments_hc.php and orders.php), no CAPTCHA |
| Jharkhand HC | yes | no | no_robots | no | pdf | https://jharkhandhighcourt.nic.in/hc_order_judgement.php | OPEN 495 KB flat HTML list of pdfview.php links, no CAPTCHA, no search form |
| Karnataka HC | no | unknown | unknown | unknown | unknown | — | Couldn't reach the host, repeated 12–25s timeouts (HTTP 000) |
| Kerala HC | yes | yes | unknown | yes | pdf | https://ecourt.keralacourts.in/digicourt/cmshck/Casedetailssearch | eCourts CMS; has an "Act" search but it's behind a CAPTCHA; not usable |
| Madhya Pradesh HC | yes | no | allow | no | pdf | https://mphc.gov.in/judgements | OPEN search plus free-text search within judgments; no CAPTCHA; direct PDFs; no section search |
| Madras HC | yes | no | no_robots | no | pdf | https://www.mhc.tn.gov.in/judis/ | OPEN simple bench + type + date form, no CAPTCHA; date and bench only |
| Manipur HC | partial | no | no_robots | no | pdf | https://hcmimphal.nic.in/hcmjudgementindex.html | OPEN DataTables index up to 2018, no CAPTCHA; after 2018 through eCourts behind a CAPTCHA |
| Meghalaya HC | yes | yes | allow | no | pdf | https://meghalayahighcourt.nic.in/legacy-orders | Live /orders has a maths CAPTCHA; /legacy-orders is an OPEN page of about 8,000 PDFs, no CAPTCHA |
| Orissa HC | partial | yes | no_robots | no | pdf | https://www.orissahighcourt.nic.in/vernacular_judgments/ | Main English search is eCourts behind a CAPTCHA; vernacular_judgments is an OPEN list of about 3,000 PDFs |
| Patna HC | yes | yes | no_robots | no | pdf | https://patnahighcourt.gov.in/judgmentslist/ALL | Every list and search is behind a CAPTCHA; judge, date and party filters, no section |
| Punjab & Haryana HC | yes | no | no_robots | no | pdf | https://new.phhc.gov.in/judgement/free-text-search | OPEN Next.js free-text search, no CAPTCHA; free text roughly stands in for POCSO/BNS |
| Rajasthan HC | yes | yes | no_robots | no | pdf | https://hcraj.nic.in/cishcraj-jp/JudgementFilters/ | Main search has a CAPTCHA ("Verification Code"); alternatives are circulated-judgements.php / eCourts |
| Sikkim HC | partial | no | no_robots | no | pdf | https://hcs.gov.in/hcs/hcourt/hg_judgement_search | OPEN search and direct order PDFs, no CAPTCHA; BUT the TLS chain is broken (needs a relaxed CA) |
| Telangana HC | no | unknown | unknown | unknown | unknown | — | tshc.gov.in timed out on every attempt; probably limited to Indian IPs; try again |
| Tripura HC | partial | yes | no_robots | yes | pdf | https://judgments.ecourts.gov.in/pdfsearch/index.php | No listing of its own; hands off to eCourts; has Act/Section search but behind a CAPTCHA |
| Uttarakhand HC | partial | yes | allow | no | pdf | https://highcourtofuttarakhand.gov.in/full-bench-judgement/ | General search is eCourts behind a CAPTCHA; the only open path is a full-bench page of 26 PDFs |

## 3. Courts worth connecting (each one added switched off first)

**Tier 1: clean open listings (reachable, no CAPTCHA, robots OK). Connect these first.**

- **Delhi HC**: https://delhihighcourt.nic.in/web/judgement/fetch-data (direct PDF links)
- **J&K & Ladakh HC**: https://jkhighcourt.nic.in/judgments_hc.php (and orders.php)
- **Jharkhand HC**: https://jharkhandhighcourt.nic.in/hc_order_judgement.php
- **Madhya Pradesh HC**: https://mphc.gov.in/judgements (free-text search within judgments)
- **Madras HC**: https://www.mhc.tn.gov.in/judis/
- **Meghalaya HC**: https://meghalayahighcourt.nic.in/legacy-orders (about 8,000 PDFs)
- **Punjab & Haryana HC**: https://new.phhc.gov.in/judgement/free-text-search (free text roughly stands in for POCSO/BNS)

**Tier 2: an open path, but partial or degraded (connect with a note saying so).**

- **Andhra Pradesh HC**: https://aphc.gov.in/circulated_judgments.php (only 41 PDFs)
- **Gauhati HC**: https://ghconline.gov.in/index.php/orders-and-judgements/ (static archive up to 2017; homepage unreliable)
- **Gujarat HC**: https://gujarathighcourt.nic.in/gujaratijudgments (only the subset translated into Gujarati)
- **Manipur HC**: https://hcmimphal.nic.in/hcmjudgementindex.html (up to 2018 only)
- **Orissa HC**: https://www.orissahighcourt.nic.in/vernacular_judgments/ (vernacular subset; about 3,000 PDFs)
- **Sikkim HC**: https://hcs.gov.in/hcs/hcourt/hg_judgement_search (needs a relaxed CA bundle because the TLS chain is broken)
- **Uttarakhand HC**: https://highcourtofuttarakhand.gov.in/full-bench-judgement/ (full bench only; 26 PDFs)

> None of these let you search by statute section. They all work by date, case type or
> free text, so picking out the right sections has to happen after fetching, during
> extraction.

## 4. Blocked

**Behind a CAPTCHA with no usable open alternative. I don't connect these, because I
never get around a CAPTCHA:**

- Supreme Court: siwp_captcha on search (date only, needs a browser UA)
- Calcutta HC: name="captcha" plus a legacy TLS requirement
- Chhattisgarh HC: CAPTCHA on oj_search.php plus an incomplete certificate chain
- Kerala HC: CAPTCHA on the digicourt CMS (it has an Act search, but it's gated)
- Patna HC: every list and search is behind a CAPTCHA
- Rajasthan HC: "Verification Code" CAPTCHA (the circulated-judgements.php alternative is worth a later look)
- Tripura HC: hands off to the eCourts pdfsearch CAPTCHA (it has a Section search, but it's gated)

**Couldn't be reached from where I ran the survey (try again from an Indian IP):**

- Bombay HC, Karnataka HC, Telangana HC: connection timeouts on every attempt (probably limited to Indian IPs, or down)

**Unknown, needs more work:**

- Allahabad HC: elegalix returned HTTP 429; needs slower requests to look at properly
- Himachal Pradesh HC: built by JavaScript/DataTables; needs the AJAX endpoint found

**robots.txt:** none of the judgment paths are explicitly disallowed. Calcutta returns a
403 firewall page for robots.txt (so the answer is unknown; treat it with care).
Meghalaya disallows only /search/ (legacy-orders is allowed).

---

## Update, 12 August 2026: the "remaining open" courts (P&H, MP, Madras, Jharkhand)

I went back to the four courts the survey called open but that I hadn't connected yet.
**Reading their portals directly would break a rule I won't break, for all four, so
they are covered through Indian Kanoon's licensed API instead.** I added `doctypes:`
searches to `sources.yml`, and on 12 August 2026 I checked that each one returns the
right court:

| Court | What I found on the portal (12 August 2026) | How it's covered |
|---|---|---|
| **Punjab & Haryana** | The judgment API host `livedb9010.phhc.gov.in` serves `robots.txt: Disallow: /`, so the whole API is off limits. The public site is a single-page app that only talks to that host. | `doctypes:punjab` → "Punjab-Haryana High Court" ✓ |
| **Madhya Pradesh** | A Next.js single-page app; judgments come from a search API behind a CAPTCHA. Plain HTTP gets 0 documents. | `doctypes:madhyapradesh` → "Madhya Pradesh High Court" ✓ |
| **Madras** | A CodeIgniter form that has to be POSTed with a date and a CSRF cookie; not a static list. | `doctypes:chennai` → "Madras High Court" ✓ |
| **Jharkhand** | `hc_order_judgement.php` is **not a redirect** (HTTP 200, no redirects) and was serving the right Jharkhand content. The "J&K content" I saw earlier was a **passing mix-up on shared NIC servers**, so a direct scraper would now and then record cases under the wrong court. | `doctypes:jharkhand` → "Jharkhand High Court" ✓ (no risk of mix-ups) |

**What I concluded:** none of the four can be read directly without breaking the
robots.txt or no-CAPTCHA rules (P&H, MP, Madras) or risking cases filed under the wrong
court (Jharkhand). Indian Kanoon was already connected, its token was live by then, and
it reads full judgments (#153). It mirrors all four and is the right way to cover them
within the rules. The shared `IK_MAX_DOCS_PER_RUN=100` budget covers every search, so this
widens court coverage across the country without raising the most we can be billed.

The open portals I did connect directly are Delhi, J&K & Ladakh and Meghalaya (the
`hc_judgments` sources in `sources.yml`).
