// Filter state <-> URL. Every filter combination round-trips through the URL query
// (in the hash), so any Explore view is deep-linkable and back/forward safe.

import { ACTIVE_STATUSES, CLOSED_STATUSES } from './format.js';

export const SORTS = ['pending', 'recent', 'oldest'];

export const DEFAULT_FILTERS = {
  state: '',
  district: '',
  status: '',
  activity: '',
  year: '',
  minor: '',
  q: '',
  sort: 'pending',
};

/** Read a URLSearchParams into a normalized filters object. */
export function filtersFromParams(params) {
  const filters = { ...DEFAULT_FILTERS };
  for (const key of Object.keys(DEFAULT_FILTERS)) {
    const value = params.get(key);
    if (value != null) filters[key] = value;
  }
  if (!SORTS.includes(filters.sort)) filters.sort = 'pending';
  return filters;
}

/** Serialize filters to URLSearchParams, omitting defaults so links stay clean. */
export function paramsFromFilters(filters) {
  const params = new URLSearchParams();
  for (const key of Object.keys(DEFAULT_FILTERS)) {
    const value = filters[key];
    if (value && value !== DEFAULT_FILTERS[key]) params.set(key, value);
  }
  return params;
}

const SORTERS = {
  pending: (a, b) => (b.pending_days || 0) - (a.pending_days || 0),
  recent: (a, b) =>
    String(b.incident_reported_date || '').localeCompare(String(a.incident_reported_date || '')),
  oldest: (a, b) =>
    String(a.incident_reported_date || '').localeCompare(String(b.incident_reported_date || '')),
};

/** Pure: filter + sort a record list by the filters object. */
export function applyFilters(records, filters) {
  const q = filters.q.trim().toLowerCase();
  const filtered = records.filter((r) => {
    if (filters.district && r.district !== filters.district) return false;
    if (filters.status && r.status !== filters.status) return false;
    if (filters.activity === 'active' && !ACTIVE_STATUSES.has(r.status)) return false;
    if (filters.activity === 'closed' && !CLOSED_STATUSES.has(r.status)) return false;
    if (filters.year && String(r.incident_reported_date || '').slice(0, 4) !== filters.year) {
      return false;
    }
    if (filters.minor === 'yes' && !r.minor_involved) return false;
    if (filters.minor === 'no' && r.minor_involved) return false;
    if (q) {
      const hay = [
        r.summary,
        r.district,
        r.cnr,
        (r.offence_sections || []).join(' '),
        r.court?.name,
      ]
        .join(' ')
        .toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  return filtered.sort(SORTERS[filters.sort] || SORTERS.pending);
}
