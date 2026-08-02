// Coverage page (§3): where the record looks, and whether its claims can be re-checked.
// Two honest numbers — the trackability rate (court-anchored fraction) and per-state
// coverage with DECLARED gaps — plus the calibration that this is a record of publicly
// reported cases, not a crime-rate statistic.

import { el } from '../dom.js';
import { t } from '../i18n/index.js';
import { stateName } from '../format.js';
import { loadCoverage } from '../data.js';

function noticeView(key) {
  return el('div', { class: 'view view--notice' }, [
    el('a', { href: '#/', class: 'crumb' }, `← ${t('nav_home')}`),
    el('p', { class: 'notice', role: 'status' }, t(key)),
  ]);
}

function pct(rate) {
  return `${Math.round((rate || 0) * 100)}%`;
}

function statTile(value, label) {
  return el('div', { class: 'cov-tile' }, [
    el('div', { class: 'cov-tile__value' }, value),
    el('div', { class: 'cov-tile__label' }, label),
  ]);
}

function stateRow(code, info) {
  const covered = info.active_sources > 0 || info.records > 0;
  return el('tr', { class: covered ? 'cov-row' : 'cov-row cov-row--gap' }, [
    el('td', { class: 'cov-row__state' }, `${stateName(code)} (${code})`),
    el('td', {}, covered ? t('cov_status_covered') : t('cov_status_gap')),
    el('td', { class: 'cov-num' }, String(info.active_sources)),
    el('td', { class: 'cov-num' }, String(info.records)),
  ]);
}

export async function renderCoverage() {
  let cov;
  try {
    cov = await loadCoverage();
  } catch {
    return noticeView(navigator.onLine === false ? 'offline_notice' : 'missing_shard');
  }

  const track = cov.trackability || { total: 0, court_anchored: 0, rate: 0 };
  const states = cov.states || {};
  const codes = Object.keys(states).sort();

  const tiles = el('div', { class: 'cov-tiles' }, [
    statTile(pct(track.rate), t('cov_trackable_label')),
    statTile(
      `${cov.states_covered || 0} / ${cov.states_total || codes.length}`,
      t('cov_states_label'),
    ),
    statTile(String(cov.national_sources || 0), t('cov_national_label')),
  ]);

  const table = el('table', { class: 'cov-table' }, [
    el('thead', {}, [
      el('tr', {}, [
        el('th', {}, t('cov_col_state')),
        el('th', {}, t('cov_col_status')),
        el('th', {}, t('cov_col_sources')),
        el('th', {}, t('cov_col_records')),
      ]),
    ]),
    el(
      'tbody',
      {},
      codes.map((code) => stateRow(code, states[code])),
    ),
  ]);

  return el('div', { class: 'view view--coverage' }, [
    el('a', { href: '#/', class: 'crumb' }, `← ${t('nav_home')}`),
    el('h1', { class: 'view__title' }, t('cov_title')),
    el('p', { class: 'view__lead' }, t('cov_lead')),
    el('aside', { class: 'cov-framing', role: 'note' }, [
      el('h2', { class: 'cov-framing__title' }, t('cov_framing_title')),
      el('p', { class: 'cov-framing__text' }, t('cov_framing')),
    ]),
    tiles,
    el('p', { class: 'cov-trackable-note' }, t('cov_trackable_note')),
    el('h2', { class: 'cov-subtitle' }, t('cov_by_state')),
    el('div', { class: 'cov-table-wrap' }, [table]),
    el('p', { class: 'disclaimer disclaimer--coverage' }, t('disclaimer')),
  ]);
}
