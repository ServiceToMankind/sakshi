// Small shared building blocks used by more than one view.

import { el } from '../dom.js';
import { t } from '../i18n/index.js';
import { statusLabel, categoryLabel, stateName, formatDate } from '../format.js';

/** A status badge. ACQUITTED/QUASHED are styled with equal prominence to CONVICTED. */
export function statusBadge(status) {
  return el(
    'span',
    { class: `badge badge--${String(status).toLowerCase()}`, 'data-status': status },
    statusLabel(status),
  );
}

export function minorBadge() {
  return el('span', { class: 'badge badge--minor', 'data-i18n': 'minor_flag' }, t('minor_flag'));
}

/**
 * Shown ONLY when a record is corroborated (verified === true). A record that is
 * not verified shows nothing here — we never label anything "unverified".
 */
export function verifiedBadge() {
  return el('span', { class: 'badge badge--verified', title: t('verified_hint') }, [
    el('span', { class: 'badge__check', 'aria-hidden': 'true' }, '✓'),
    el('span', { 'data-i18n': 'verified_badge' }, t('verified_badge')),
  ]);
}

/**
 * A card for the landing "Recent cases" feed. Reads the flat `recent.json` shape
 * (title/summary/state/district/category/status/date/publisher/verified), which
 * differs from the richer shard record used by `caseCard`.
 */
export function recentCard(record) {
  const place = [stateName(record.state), record.district].filter(Boolean).join(' · ');
  const date = record.incident_reported_date;
  const meta = [
    place ? el('span', { class: 'feed-card__place' }, place) : null,
    el('span', { class: 'feed-card__cat' }, categoryLabel(record.category)),
    date
      ? el('time', { class: 'feed-card__date', datetime: String(date) }, formatDate(date))
      : null,
    record.publisher ? el('span', { class: 'feed-card__source' }, record.publisher) : null,
  ].filter(Boolean);

  return el('li', { class: 'feed-card' }, [
    el(
      'a',
      {
        class: 'feed-card__link',
        href: `#/case/${encodeURIComponent(record.id)}`,
        'aria-label': `${record.title || record.id} — ${statusLabel(record.status)}`,
      },
      [
        el('div', { class: 'feed-card__badges' }, [
          statusBadge(record.status),
          record.minor_involved ? minorBadge() : null,
          record.verified ? verifiedBadge() : null,
        ]),
        el('h3', { class: 'feed-card__title' }, record.title || record.id),
        record.summary ? el('p', { class: 'feed-card__summary' }, record.summary) : null,
        el('div', { class: 'feed-card__meta' }, meta),
      ],
    ),
  ]);
}

/** A tappable case card linking to the case detail route. */
export function caseCard(record) {
  const meta = [
    el('span', {}, record.district || ''),
    el('span', {}, categoryLabel(record.category)),
    (record.offence_sections || []).length
      ? el('span', {}, (record.offence_sections || []).join(', '))
      : null,
    record.pending_days != null
      ? el(
          'span',
          { class: 'case-card__pending' },
          `${record.pending_days} ${t('case_pending_days')}`,
        )
      : null,
  ].filter(Boolean);

  return el('li', { class: 'case-card' }, [
    el(
      'a',
      {
        class: 'case-card__link',
        href: `#/case/${encodeURIComponent(record.id)}`,
        'aria-label': `${record.id} — ${statusLabel(record.status)}`,
      },
      [
        el('div', { class: 'case-card__top' }, [
          statusBadge(record.status),
          record.minor_involved ? minorBadge() : null,
        ]),
        el('p', { class: 'case-card__summary' }, record.summary || ''),
        el('div', { class: 'case-card__meta' }, meta),
        el('span', { class: 'case-card__id' }, record.id),
      ],
    ),
  ]);
}
