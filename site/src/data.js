// Loads the site's data files (the summary, the list of shards, the district scorecard
// and each state's cases), keeps them in memory, and reports clear errors so a page can
// say exactly what's missing. It only reads; it never changes anything.

const BASE = import.meta.env.BASE_URL || '/';
const DATA = `${BASE}data`;

const cache = new Map();

export class DataError extends Error {
  constructor(message, { status = 0, url = '' } = {}) {
    super(message);
    this.name = 'DataError';
    this.status = status;
    this.url = url;
  }
}

async function getJSON(url) {
  if (cache.has(url)) return cache.get(url);
  let res;
  try {
    res = await fetch(url, { headers: { Accept: 'application/json' } });
  } catch {
    throw new DataError('network unavailable', { url });
  }
  if (!res.ok) throw new DataError(`HTTP ${res.status}`, { status: res.status, url });
  const json = await res.json();
  cache.set(url, json);
  return json;
}

export function loadSummary() {
  return getJSON(`${DATA}/summary.json`);
}

/**
 * The landing feed's data source: a flat array of the latest published records
 * (newest first), written by the pipeline as `data/recent.json`. Deliberately a
 * single small file so the landing never walks per-state shards. Callers should
 * treat a rejection (missing/empty file) as "no recent cases" and degrade.
 */
export function loadRecent() {
  return getJSON(`${DATA}/recent.json`);
}

export function loadIndex() {
  return getJSON(`${DATA}/index.json`);
}

/**
 * The scorecard for every district (data/jurisdictions.json), busiest first, with no cap,
 * so every published case is counted once. It lives in its own file so the home page
 * stays fast however many districts we cover.
 */
export async function loadJurisdictions() {
  const doc = await getJSON(`${DATA}/jurisdictions.json`);
  return Array.isArray(doc.jurisdictions) ? doc.jurisdictions : [];
}

/** Per-state coverage + the trackability rate (data/coverage.json, §3). */
export function loadCoverage() {
  return getJSON(`${DATA}/coverage.json`);
}

function shardsWhere(index, predicate) {
  return (index.shards || []).filter(predicate);
}

/** True if the manifest lists any shard for the state (so views can say "no data" vs "404"). */
export async function stateHasData(state) {
  const index = await loadIndex();
  return shardsWhere(index, (s) => s.state === state).length > 0;
}

/** Load every record for a state (all years, all -pN parts). Returns {present, records}. */
export async function loadStateRecords(state) {
  const index = await loadIndex();
  const parts = shardsWhere(index, (s) => s.state === state);
  if (!parts.length) return { present: false, records: [] };
  const arrays = await Promise.all(parts.map((p) => getJSON(`${DATA}/${p.path}`)));
  return { present: true, records: arrays.flat() };
}

/**
 * Load every published record across all shards (all states/years/parts). Used by
 * the offender scorecard, which needs case-level `accused` data that the summary
 * does not carry. Fetches are cached and run in parallel; a shard that fails to load
 * is skipped so one bad file never blanks the whole scorecard.
 */
export async function loadAllRecords() {
  const index = await loadIndex();
  const paths = (index.shards || []).map((s) => s.path);
  const arrays = await Promise.all(paths.map((path) => getJSON(`${DATA}/${path}`).catch(() => [])));
  return arrays.flat();
}

const CASE_ID = /^SKS-(\d{4})-([A-Z]{2})-\d{6}$/;

/** Load a single case by id, or null if the id is malformed or not found. */
export async function loadCase(id) {
  const match = CASE_ID.exec(id || '');
  if (!match) return null;
  const { records } = await loadStateRecords(match[2]);
  return records.find((r) => r.id === id) || null;
}

export function clearCache() {
  cache.clear();
}
