// Presentation-layer constants and formatters. No DOM, no data fetching.

export const STATUS_LABELS = {
  FIR_FILED: 'FIR filed',
  CHARGESHEETED: 'Chargesheeted',
  UNDER_TRIAL: 'Under trial',
  APPEAL_PENDING: 'Appeal pending',
  CONVICTED: 'Convicted',
  ACQUITTED: 'Acquitted',
  QUASHED: 'Quashed',
  CLOSED: 'Closed',
  UNKNOWN: 'Unknown',
};

// "Active" = the matter is live in the system; "Closed" = resolved. ACQUITTED and
// QUASHED sit in Closed with equal standing to CONVICTED — never hidden.
export const ACTIVE_STATUSES = new Set([
  'FIR_FILED',
  'CHARGESHEETED',
  'UNDER_TRIAL',
  'APPEAL_PENDING',
]);
export const CLOSED_STATUSES = new Set(['CONVICTED', 'ACQUITTED', 'QUASHED', 'CLOSED']);

export const CATEGORY_LABELS = {
  sexual_assault: 'Sexual assault',
  rape: 'Rape',
  pocso: 'POCSO',
  acid_attack: 'Acid attack',
  harassment: 'Harassment',
  other: 'Other',
};

// Ordered status list for legends/stepper.
export const STATUS_ORDER = [
  'FIR_FILED',
  'CHARGESHEETED',
  'UNDER_TRIAL',
  'APPEAL_PENDING',
  'CONVICTED',
  'ACQUITTED',
  'QUASHED',
  'CLOSED',
  'UNKNOWN',
];

const STATE_NAMES = {
  AP: 'Andhra Pradesh',
  AR: 'Arunachal Pradesh',
  AS: 'Assam',
  BR: 'Bihar',
  CT: 'Chhattisgarh',
  GA: 'Goa',
  GJ: 'Gujarat',
  HR: 'Haryana',
  HP: 'Himachal Pradesh',
  JH: 'Jharkhand',
  KA: 'Karnataka',
  KL: 'Kerala',
  MP: 'Madhya Pradesh',
  MH: 'Maharashtra',
  MN: 'Manipur',
  ML: 'Meghalaya',
  MZ: 'Mizoram',
  NL: 'Nagaland',
  OD: 'Odisha',
  PB: 'Punjab',
  RJ: 'Rajasthan',
  SK: 'Sikkim',
  TN: 'Tamil Nadu',
  TG: 'Telangana',
  TR: 'Tripura',
  UP: 'Uttar Pradesh',
  UT: 'Uttarakhand',
  WB: 'West Bengal',
  DL: 'Delhi',
  JK: 'Jammu & Kashmir',
  LA: 'Ladakh',
  PY: 'Puducherry',
  CH: 'Chandigarh',
  AN: 'Andaman & Nicobar',
  DN: 'Dadra & Nagar Haveli and Daman & Diu',
  LD: 'Lakshadweep',
};

export function statusLabel(status) {
  return STATUS_LABELS[status] || status || '—';
}

export function categoryLabel(category) {
  return CATEGORY_LABELS[category] || category || '—';
}

export function stateName(code) {
  return STATE_NAMES[code] || code;
}

export function isActiveStatus(status) {
  return ACTIVE_STATUSES.has(status);
}

export function formatDate(iso) {
  if (!iso) return '—';
  const s = String(iso);
  // Minor cases store reduced-precision dates (POCSO s.23): render them at their
  // true precision rather than fabricating a day/month via Date parsing.
  if (/^\d{4}$/.test(s)) return s; // year only
  if (/^\d{4}-\d{2}$/.test(s)) {
    const ym = new Date(`${s}-01T00:00:00Z`);
    if (Number.isNaN(ym.getTime())) return s;
    return ym.toLocaleDateString(undefined, { year: 'numeric', month: 'short', timeZone: 'UTC' });
  }
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function formatNumber(n) {
  return new Intl.NumberFormat().format(n || 0);
}

/** Whole hours since an ISO timestamp; used for the stale-data notice. */
export function hoursSince(iso) {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return Infinity;
  return (Date.now() - t) / 3_600_000;
}
