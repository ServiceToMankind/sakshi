// Sakshi — filter state <-> URL synchronisation (Phase-4 scaffold STUB).
//
// The explore view's filter state is the single source of truth for what the
// user sees, and it round-trips through the URL query so every filtered view is
// shareable. Defaults: sort by largest pending duration; active + closed shown.

/**
 * @typedef {Object} FilterState
 * @property {string=} state          2-letter state code
 * @property {string=} district
 * @property {string=} status         status enum token or 'ALL'
 * @property {number=} year
 * @property {boolean=} minorInvolved
 * @property {'pending' | 'date'} sort
 * @property {string=} q              free-text over summary
 */

/** @returns {FilterState} */
export function defaultFilters() {
  return { status: 'ALL', sort: 'pending' };
}

/**
 * Decode a URLSearchParams into a FilterState.
 * @param {URLSearchParams} params
 * @returns {FilterState}
 */
export function filtersFromParams(params) {
  const f = defaultFilters();
  if (params.has('state')) f.state = params.get('state') ?? undefined;
  if (params.has('district')) f.district = params.get('district') ?? undefined;
  if (params.has('status')) f.status = params.get('status') ?? 'ALL';
  if (params.has('year')) f.year = Number(params.get('year'));
  if (params.has('minor')) f.minorInvolved = params.get('minor') === '1';
  if (params.has('sort')) f.sort = params.get('sort') === 'date' ? 'date' : 'pending';
  if (params.has('q')) f.q = params.get('q') ?? undefined;
  return f;
}

/**
 * Encode a FilterState into a URLSearchParams (omitting defaults/empties).
 * @param {FilterState} f
 * @returns {URLSearchParams}
 */
export function filtersToParams(f) {
  const p = new URLSearchParams();
  if (f.state) p.set('state', f.state);
  if (f.district) p.set('district', f.district);
  if (f.status && f.status !== 'ALL') p.set('status', f.status);
  if (f.year) p.set('year', String(f.year));
  if (f.minorInvolved) p.set('minor', '1');
  if (f.sort && f.sort !== 'pending') p.set('sort', f.sort);
  if (f.q) p.set('q', f.q);
  return p;
}

/**
 * Wire up filter controls. STUB: no DOM bindings yet.
 */
export function initFilters() {
  // TODO: bind form controls -> FilterState -> update location.hash query.
  console.info('[sakshi] filters ready (stub)');
}
