// Small shared building blocks used by more than one view.

import { el } from '../dom.js';
import { t } from '../i18n/index.js';
import { statusLabel, categoryLabel } from '../format.js';

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
