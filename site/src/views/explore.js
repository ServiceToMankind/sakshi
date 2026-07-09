// Explore route: pick a state, then drill into its cases with filters. Every
// filter combination round-trips through the URL. Handles the "no shard for this
// state" degraded case distinctly from "no results".

import { el } from '../dom.js';
import { t } from '../i18n/index.js';
import { loadSummary, loadStateRecords, stateHasData } from '../data.js';
import { filtersFromParams, paramsFromFilters, applyFilters, DEFAULT_FILTERS } from '../state.js';
import { buildFilters } from '../filters.js';
import { stateName } from '../format.js';
import { navigate } from '../router.js';
import { caseCard } from './parts.js';

function uniqueSorted(values, direction = 'asc') {
  const out = [...new Set(values.filter(Boolean))].sort();
  return direction === 'desc' ? out.reverse() : out;
}

async function statePicker() {
  let counts = {};
  try {
    counts = (await loadSummary()).state_counts || {};
  } catch {
    counts = {};
  }
  const codes = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
  const tiles = codes.length
    ? codes.map((code) =>
        el('a', { class: 'state-pick', href: `#/explore?state=${code}` }, [
          el('span', { class: 'state-pick__name' }, stateName(code)),
          el('span', { class: 'state-pick__count' }, String(counts[code])),
        ]),
      )
    : [el('p', { class: 'muted', 'data-i18n': 'no_results' }, t('no_results'))];

  return el('div', { class: 'view view--explore' }, [
    el('div', { class: 'explore__head reveal' }, [
      el('h1', { class: 'explore__title', 'data-i18n': 'explore_title' }, t('explore_title')),
      el('p', { class: 'muted', 'data-i18n': 'explore_lead' }, t('explore_lead')),
    ]),
    el('p', { class: 'muted', 'data-i18n': 'select_state' }, t('select_state')),
    el('div', { class: 'state-picks reveal' }, tiles),
  ]);
}

function missingState(state) {
  return el('div', { class: 'view view--notice' }, [
    el('a', { href: '#/explore', class: 'crumb' }, `← ${t('nav_explore')}`),
    el('h1', { class: 'explore__title' }, stateName(state)),
    el('p', { class: 'notice', role: 'status', 'data-i18n': 'missing_shard' }, t('missing_shard')),
  ]);
}

export async function renderExplore(route) {
  const state = route.params.get('state') || '';
  if (!state) return statePicker();
  if (!(await stateHasData(state))) return missingState(state);

  const filters = filtersFromParams(route.params);
  const { records } = await loadStateRecords(state);
  const years = uniqueSorted(
    records.map((r) => String(r.incident_reported_date || '').slice(0, 4)),
    'desc',
  );
  const districts = uniqueSorted(records.map((r) => r.district));
  const statuses = uniqueSorted(records.map((r) => r.status));
  const filtered = applyFilters(records, filters);

  const onChange = (key, value) => {
    const next = key === '__clear__' ? { ...DEFAULT_FILTERS } : { ...filters, [key]: value };
    const params = paramsFromFilters(next);
    params.set('state', state);
    navigate(`/explore?${params.toString()}`);
  };

  const results = filtered.length
    ? el('ul', { class: 'case-list' }, filtered.map(caseCard))
    : el('div', { class: 'empty', role: 'status' }, [
        el('p', { 'data-i18n': 'no_results' }, t('no_results')),
        el('p', { class: 'empty__hint', 'data-i18n': 'no_results_hint' }, t('no_results_hint')),
      ]);

  return el('div', { class: 'view view--explore' }, [
    el('div', { class: 'explore__head reveal' }, [
      el('a', { href: '#/explore', class: 'crumb' }, `← ${t('nav_explore')}`),
      el('h1', { class: 'explore__title' }, stateName(state)),
      el('p', { class: 'muted' }, `${filtered.length} ${t('results_count')}`),
    ]),
    buildFilters(filters, { years, districts, statuses }, onChange),
    results,
  ]);
}
