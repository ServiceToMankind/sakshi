# High Court + Supreme Court judgment-portal survey — 2026-08-03 (§4a)

> Automated survey (curl + robots.txt inspection, honest `sakshi-bot` UA, no CAPTCHA
> circumvention) of all 25 High Courts + the Supreme Court, to decide whether the paid
> Indian Kanoon token is still the critical path for court coverage. **It is not.**

# Sakshi Court-Source Survey (§4a) — 26 courts (25 HC + SC)

## 1. Headline

Of the 26 courts, only **7 are cleanly OPEN** — reachable, no CAPTCHA on an open listing, robots-permitted: **Delhi, J&K & Ladakh, Jharkhand, Madhya Pradesh, Madras, Meghalaya (legacy-orders), and Punjab & Haryana**. Another **7 expose an open no-CAPTCHA path but only a degraded/partial one** (Andhra's 41-PDF circulated list, Gauhati's ≤2017 archive, Gujarat's Gujarati-translated subset, Manipur's ≤2018 index, Orissa's vernacular subset, Sikkim (broken TLS), Uttarakhand full-bench-only). **7 are hard CAPTCHA-gated** (Supreme Court, Calcutta, Chhattisgarh, Kerala, Patna, Rajasthan, Tripura), **3 are unreachable** from this egress (Bombay, Karnataka, Telangana — likely India-geo-fenced), and **2 remain unknown** (Allahabad HTTP 429, Himachal JS-rendered). **Critical takeaway: the Indian Kanoon API token stays the critical path.** Every court that advertises a statute-**section** facet (Andhra, Kerala, Tripura) hides it behind the CAPTCHA; not one open path offers POCSO/BNS/IPC section search, so the ~14 open courts only support fetch-everything-then-filter, and the remaining ~12 (CAPTCHA + unreachable + unknown) cannot be covered directly at all. IK remains the only realistic route to section-targeted, all-India coverage.

## 2. Survey table

| Court | Reachable | CAPTCHA | Robots | Section-search | Format | Best URL | Notes |
|---|---|---|---|---|---|---|---|
| Supreme Court | partial | yes | allow | no | pdf | https://www.sci.gov.in/judgements-judgement-date/ | Needs browser UA (honest UA 403 at Akamai); search siwp_captcha-gated; date-only |
| Allahabad HC | partial | unknown | allow | unknown | html | https://elegalix.allahabadhighcourt.in/elegalix/StartWebSearch.do | elegalix HTTP 429 both tries; needs throttle to survey |
| Andhra Pradesh HC | yes | yes | no_robots | yes | pdf | https://aphc.gov.in/circulated_judgments.php | Section facet only behind eCourts CAPTCHA; circulated_judgments = OPEN 41-PDF list, no section |
| Bombay HC | no | unknown | unknown | unknown | unknown | — | Timed out >15s both UAs incl robots; retry from other egress |
| Calcutta HC | partial | yes | unknown | no | pdf | https://www.calcuttahighcourt.gov.in/Order-Judgments | Needs unsafe-legacy-renegotiation TLS; name="captcha"; case-type only; robots 403 WAF |
| Chhattisgarh HC | partial | yes | no_robots | no | pdf | https://highcourt.cg.gov.in/hcbspjudgement/oj_search.php | Incomplete cert chain (-k); oj_search CAPTCHA-gated, no section |
| Delhi HC | yes | no | no_robots | no | pdf | https://delhihighcourt.nic.in/web/judgement/fetch-data | OPEN: 308 direct PDF links, no CAPTCHA; date/latest only |
| Gauhati HC | partial | yes | allow | no | pdf | https://ghconline.gov.in/index.php/orders-and-judgements/ | Live search CAPTCHA; static "≤2017" open PDF archive; homepage flaky |
| Gujarat HC | partial | yes | unknown | no | pdf | https://gujarathighcourt.nic.in/gujaratijudgments | Full search = CAPTCHA eCourts; only open path is Gujarati-translated PDF subset |
| Himachal Pradesh HC | partial | unknown | no_robots | unknown | unknown | https://highcourt.hp.gov.in/ | Migrated; DataTables/JS-rendered, curl sees no links; needs AJAX endpoint discovery |
| J&K & Ladakh HC | yes | no | no_robots | no | pdf | https://jkhighcourt.nic.in/judgments_hc.php | OPEN plain-HTML PDF lists (judgments_hc.php + orders.php), no CAPTCHA |
| Jharkhand HC | yes | no | no_robots | no | pdf | https://jharkhandhighcourt.nic.in/hc_order_judgement.php | OPEN 495KB flat HTML list of pdfview.php links, no CAPTCHA, no search form |
| Karnataka HC | no | unknown | unknown | unknown | unknown | — | Host unreachable, repeated 12-25s timeouts (HTTP 000) |
| Kerala HC | yes | yes | unknown | yes | pdf | https://ecourt.keralacourts.in/digicourt/cmshck/Casedetailssearch | eCourts CMS; has 'Act' facet but CAPTCHA-gated; not usable |
| Madhya Pradesh HC | yes | no | allow | no | pdf | https://mphc.gov.in/judgements | OPEN search + free-text within-judgment; no CAPTCHA; direct PDFs; no section facet |
| Madras HC | yes | no | no_robots | no | pdf | https://www.mhc.tn.gov.in/judis/ | OPEN simple Bench+Type+date form, no CAPTCHA; date/bench only |
| Manipur HC | partial | no | no_robots | no | pdf | https://hcmimphal.nic.in/hcmjudgementindex.html | OPEN DataTables index ≤2018, no CAPTCHA; post-2018 via CAPTCHA eCourts |
| Meghalaya HC | yes | yes | allow | no | pdf | https://meghalayahighcourt.nic.in/legacy-orders | Live /orders math_captcha; /legacy-orders = OPEN ~8000-PDF page, no CAPTCHA |
| Orissa HC | partial | yes | no_robots | no | pdf | https://www.orissahighcourt.nic.in/vernacular_judgments/ | Main English search = CAPTCHA eCourts; vernacular_judgments = OPEN ~3000-PDF list |
| Patna HC | yes | yes | no_robots | no | pdf | https://patnahighcourt.gov.in/judgmentslist/ALL | All lists/searches CAPTCHA-gated; judge/date/party facets, no section |
| Punjab & Haryana HC | yes | no | no_robots | no | pdf | https://new.phhc.gov.in/judgement/free-text-search | OPEN Next.js free-text search, no CAPTCHA; free-text approximates POCSO/BNS |
| Rajasthan HC | yes | yes | no_robots | no | pdf | https://hcraj.nic.in/cishcraj-jp/JudgementFilters/ | Main search CAPTCHA ('Verification Code'); alt circulated-judgements.php / ecourts |
| Sikkim HC | partial | no | no_robots | no | pdf | https://hcs.gov.in/hcs/hcourt/hg_judgement_search | OPEN search + direct order PDFs, no CAPTCHA; BUT broken TLS chain (relaxed CA) |
| Telangana HC | no | unknown | unknown | unknown | unknown | — | tshc.gov.in TCP-timeout every attempt; likely India-only geo-fence; re-probe |
| Tripura HC | partial | yes | no_robots | yes | pdf | https://judgments.ecourts.gov.in/pdfsearch/index.php | No native listing; delegates to eCourts; Act/Section facet but CAPTCHA-gated |
| Uttarakhand HC | partial | yes | allow | no | pdf | https://highcourtofuttarakhand.gov.in/full-bench-judgement/ | General search = CAPTCHA eCourts; only open path is 26-PDF Full-Bench page |

## 3. WIRE THESE (enabled: false)

**Tier 1 — clean open listings (reachable, no CAPTCHA, robots OK) — wire first:**

- **Delhi HC** — https://delhihighcourt.nic.in/web/judgement/fetch-data (direct PDF links)
- **J&K & Ladakh HC** — https://jkhighcourt.nic.in/judgments_hc.php (+ orders.php)
- **Jharkhand HC** — https://jharkhandhighcourt.nic.in/hc_order_judgement.php
- **Madhya Pradesh HC** — https://mphc.gov.in/judgements (free-text within judgment text)
- **Madras HC** — https://www.mhc.tn.gov.in/judis/
- **Meghalaya HC** — https://meghalayahighcourt.nic.in/legacy-orders (~8000 PDFs)
- **Punjab & Haryana HC** — https://new.phhc.gov.in/judgement/free-text-search (free-text ≈ POCSO/BNS)

**Tier 2 — open path but partial/degraded (wire with a caveat flag):**

- **Andhra Pradesh HC** — https://aphc.gov.in/circulated_judgments.php (only 41 PDFs)
- **Gauhati HC** — https://ghconline.gov.in/index.php/orders-and-judgements/ (static ≤2017 archive; homepage flaky)
- **Gujarat HC** — https://gujarathighcourt.nic.in/gujaratijudgments (Gujarati-translated subset only)
- **Manipur HC** — https://hcmimphal.nic.in/hcmjudgementindex.html (≤2018 only)
- **Orissa HC** — https://www.orissahighcourt.nic.in/vernacular_judgments/ (vernacular subset; ~3000 PDFs)
- **Sikkim HC** — https://hcs.gov.in/hcs/hcourt/hg_judgement_search (needs relaxed CA bundle — broken TLS chain)
- **Uttarakhand HC** — https://highcourtofuttarakhand.gov.in/full-bench-judgement/ (Full-Bench only; 26 PDFs)

> Note: none of these expose a statute-section facet — all are date/case-type/free-text; section targeting must be done post-fetch during extraction.

## 4. BLOCKED

**CAPTCHA-gated (no usable open alternative) — not wireable per hard rule:**

- Supreme Court — siwp_captcha on search (date-only, needs browser UA)
- Calcutta HC — name="captcha" + legacy-TLS requirement
- Chhattisgarh HC — oj_search.php CAPTCHA + incomplete cert chain
- Kerala HC — digicourt CMS CAPTCHA (has Act facet, but gated)
- Patna HC — all lists/searches CAPTCHA-gated
- Rajasthan HC — 'Verification Code' CAPTCHA (alt circulated-judgements.php worth a later probe)
- Tripura HC — delegates to eCourts pdfsearch CAPTCHA (has Section facet, but gated)

**Unreachable from this egress (re-probe from an Indian IP):**

- Bombay HC, Karnataka HC, Telangana HC — TCP/route timeouts on every attempt (likely India-only geo-fence or down)

**Unknown / needs more survey work:**

- Allahabad HC — elegalix HTTP 429; needs backoff/throttle to inspect
- Himachal Pradesh HC — JS/DataTables-rendered; needs AJAX endpoint discovery

**robots-disallow:** none of the judgment paths are explicitly robots-disallowed; Calcutta returns a 403 WAF page for robots.txt (verdict unknown, treat cautiously). Meghalaya disallows only /search/ (legacy-orders permitted).