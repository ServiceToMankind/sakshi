// Data layer: base-path-aware fetch of summary.json, the shard manifest, and
// per-state shards, with an in-memory cache and typed errors so views can render
// precise empty/degraded states. Nothing here mutates data; it only reads.

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

export function loadIndex() {
  return getJSON(`${DATA}/index.json`);
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
