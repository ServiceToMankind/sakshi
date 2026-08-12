// The /accountability route (§3) — the project's shame engine on one page: the scale drumbeat,
// a LIVE "longest without justice" counter for the worst court-anchored pending cases, the
// sortable per-(state, district) scorecard (cases, % stalled pre-chargesheet, median pending,
// convictions vs acquittals), and the offender scorecard — all aggregate/public data (no victim
// particulars). The coverage disclaimer travels with the scorecard so a ranking is never read as
// national. Nothing here lowers the identity floor: pendency is court-anchored + non-minor only.

import { el } from '../dom.js';
import { t } from '../i18n/index.js';
import { loadSummary, loadCoverage } from '../data.js';
import { formatNumber, stateName } from '../format.js';
import { scaleDrumbeat, jurisdictionScorecard, offenderScorecard } from './scorecards.js';

// A self-updating "N days, HH:MM:SS" counter ticking from a day-precise report date. Day-precise
// dates exist only for non-minor court-anchored cases, so this never renders minor granularity.
// The interval clears itself once the node leaves the DOM (route change) — no leak.
function liveCounter(isoDate) {
  const days = el('span', { class: 'live-counter__days' }, '—');
  const clock = el('span', { class: 'live-counter__clock' }, '');
  const wrap = el('div', { class: 'live-counter', role: 'timer', 'aria-live': 'off' }, [
    days,
    clock,
  ]);
  const start = Date.parse(`${isoDate}T00:00:00Z`);
  const tick = () => {
    if (!wrap.isConnected) {
      window.clearInterval(id);
      return;
    }
    const ms = Date.now() - start;
    if (!Number.isFinite(start) || ms < 0) {
      days.textContent = '—';
      return;
    }
    const d = Math.floor(ms / 86400000);
    const rem = ms - d * 86400000;
    const h = Math.floor(rem / 3600000);
    const m = Math.floor((rem % 3600000) / 60000);
    const s = Math.floor((rem % 60000) / 1000);
    days.textContent = formatNumber(d);
    const pad = (n) => String(n).padStart(2, '0');
    clock.textContent = `${pad(h)}:${pad(m)}:${pad(s)}`;
  };
  const id = window.setInterval(tick, 1000);
  tick();
  return wrap;
}

// State code from an id (SKS-YYYY-ST-NNNNNN) so a spotlight card can name the state — the entry
// itself carries only the district (§1a: district is the finest locality ever stored).
function stateOfId(id) {
  const parts = String(id).split('-');
  return parts.length >= 3 ? parts[2] : '';
}

function longestSpotlight(entries) {
  const list = Array.isArray(entries) ? entries : [];
  const body = list.length
    ? el(
        'ul',
        { class: 'longest-list' },
        list.map((e) => {
          const place = [stateName(stateOfId(e.id)), e.district].filter(Boolean).join(' · ');
          const counter = e.incident_reported_date
            ? liveCounter(e.incident_reported_date)
            : el('div', { class: 'live-counter' }, [
                el('span', { class: 'live-counter__days' }, formatNumber(e.days_since_reported)),
              ]);
          return el('li', { class: 'longest-card' }, [
            counter,
            el('div', { class: 'longest-card__meta' }, [
              el(
                'span',
                { class: 'longest-card__label', 'data-i18n': 'days_without_justice' },
                t('days_without_justice'),
              ),
              place ? el('span', { class: 'longest-card__place' }, place) : null,
              el(
                'a',
                { class: 'longest-card__link', href: `#/case/${encodeURIComponent(e.id)}` },
                e.id,
              ),
            ]),
          ]);
        }),
      )
    : el('p', { class: 'muted', 'data-i18n': 'acct_longest_empty' }, t('acct_longest_empty'));

  return el('section', { class: 'panel reveal', 'aria-labelledby': 'acct-longest-title' }, [
    el(
      'h2',
      { class: 'panel__title', id: 'acct-longest-title', 'data-i18n': 'acct_longest_title' },
      t('acct_longest_title'),
    ),
    el('p', { class: 'muted', 'data-i18n': 'acct_longest_lead' }, t('acct_longest_lead')),
    body,
  ]);
}

// One headline: the share of TRACKED cases stalled before a chargesheet (FIR filed, no
// chargesheet) — computed from the public status counts.
function stalledHeadline(statusCounts) {
  const counts = statusCounts || {};
  const total = Object.values(counts).reduce((n, c) => n + (Number(c) || 0), 0);
  if (!total) return null;
  const pct = Math.round((100 * (Number(counts.FIR_FILED) || 0)) / total);
  return el('section', { class: 'acct-headline reveal', role: 'note' }, [
    el('span', { class: 'acct-headline__num' }, `${pct}%`),
    el(
      'span',
      { class: 'acct-headline__text', 'data-i18n': 'acct_stalled_text' },
      t('acct_stalled_text'),
    ),
  ]);
}

export async function renderAccountability() {
  const summary = await loadSummary();
  let coverage = null;
  try {
    coverage = await loadCoverage();
  } catch {
    coverage = null;
  }

  return el('div', { class: 'view view--accountability' }, [
    el('section', { class: 'lead reveal' }, [
      el('h1', { class: 'lead__tagline', 'data-i18n': 'acct_title' }, t('acct_title')),
      el('p', { class: 'lead__text', 'data-i18n': 'acct_lead' }, t('acct_lead')),
    ]),
    stalledHeadline(summary.status_counts),
    scaleDrumbeat(summary),
    longestSpotlight(summary.top_longest_pending),
    jurisdictionScorecard(summary.jurisdictions, coverage),
    offenderScorecard(),
  ]);
}
