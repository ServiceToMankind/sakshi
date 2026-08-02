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
  // No status has been recorded from a court/media source yet — not "unknown" as a claim
  // about the case, but "not yet recorded" (§6 plain-language honesty).
  UNKNOWN: 'No court status recorded yet',
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

// Whitelist http(s) for any URL rendered as an outbound href. Source URLs are
// pipeline-controlled, but this is defence in depth so a stray javascript:/data:
// scheme can never become a clickable link. Returns '#' for anything else.
export function safeHttpUrl(url) {
  return typeof url === 'string' && /^https?:\/\//i.test(url.trim()) ? url : '#';
}

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

/**
 * A relative-recency phrase ("3 weeks ago") for a DAY-PRECISE date only. Returns '' for a
 * year- or month-only date — a minor's incident date is month-precise by projection (§2), so
 * a minor card shows the month itself ("Jul 2026"), never a day-grained "N ago". Localised via
 * Intl.RelativeTimeFormat. Future dates return ''.
 */
export function relativeRecency(iso) {
  const s = String(iso || '');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return '';
  const then = new Date(`${s}T00:00:00Z`).getTime();
  if (Number.isNaN(then)) return '';
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days < 0) return '';
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  if (days < 7) return rtf.format(-days, 'day');
  if (days < 45) return rtf.format(-Math.round(days / 7), 'week');
  if (days < 365) return rtf.format(-Math.round(days / 30), 'month');
  return rtf.format(-Math.round(days / 365), 'year');
}

/** Whole hours since an ISO timestamp; used for the stale-data notice. */
export function hoursSince(iso) {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return Infinity;
  return (Date.now() - t) / 3_600_000;
}
