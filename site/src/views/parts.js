// Small shared building blocks used by more than one view.

import { el } from '../dom.js';
import { t } from '../i18n/index.js';
import {
  statusLabel,
  categoryLabel,
  stateName,
  formatDate,
  formatNumber,
  isActiveStatus,
} from '../format.js';
import { severityLabel, severityCode, isAggravated, isRepeatOffender } from '../severity.js';

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
 * A charge-derived severity badge, or null when the offence sections match no rule.
 * Aggravated categories get a distinct dark-red weight (`badge--aggravated`). Derived
 * ONLY from public charge codes (`offence_sections`) — safe for EVERY case including a
 * minor's, because it describes the OFFENCE, never the victim (CLAUDE.md §1a/§5).
 */
export function severityBadge(offenceSections) {
  const label = severityLabel(offenceSections);
  if (!label) return null;
  const aggravated = isAggravated(offenceSections);
  // The visible text is the human `severity_display`; `data-severity-code` carries the
  // stable machine token (severity_code) so styling/analytics never depend on wording.
  return el(
    'span',
    {
      class: `badge badge--severity${aggravated ? ' badge--aggravated' : ''}`,
      'data-severity-code': severityCode(offenceSections) || '',
      title: t('severity_hint'),
    },
    label,
  );
}

/** A separate repeat/habitual-offender chip (a second aggravating axis), or null. */
export function repeatOffenderBadge(offenceSections) {
  if (!isRepeatOffender(offenceSections)) return null;
  return el(
    'span',
    { class: 'badge badge--repeat', 'data-i18n': 'severity_repeat' },
    t('severity_repeat'),
  );
}

/**
 * The "days since first reported" ticker — NEUTRAL elapsed time, never a "days without
 * justice" claim (that would need a re-checkable court anchor; pendency honesty). Day-precise
 * elapsed time exists ONLY for non-minor cases (a minor's date is year-only by projection, and
 * `days_since_reported` is nulled), so this NEVER renders on a minor card — a hard guardrail
 * (CLAUDE.md §1a). Shown while the case is unresolved; resolved cases show no ticker.
 */
export function daysTicker(record) {
  if (record.minor_involved) return null;
  if (!isActiveStatus(record.status)) return null;
  if (record.days_since_reported == null) return null;
  return el('div', { class: 'days-ticker', role: 'note' }, [
    el('span', { class: 'days-ticker__num' }, formatNumber(record.days_since_reported)),
    el(
      'span',
      { class: 'days-ticker__label', 'data-i18n': 'days_since_reported' },
      t('days_since_reported'),
    ),
  ]);
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
      ? el(
          'time',
          { class: 'feed-card__date', datetime: String(date) },
          `${t('case_reported')} ${formatDate(date)}`,
        )
      : null,
    record.publisher ? el('span', { class: 'feed-card__source' }, record.publisher) : null,
    // A record shows "Status changed <date>" ONLY when a material field actually changed
    // (last_status_change is present). An unchanged re-sighting shows nothing — the site no
    // longer claims every case "updated today" (§1).
    record.last_status_change
      ? el(
          'time',
          {
            class: 'feed-card__updated',
            datetime: String(record.last_status_change),
            title: t('status_changed_hint'),
          },
          `${t('status_changed_label')} ${formatDate(record.last_status_change)}`,
        )
      : null,
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
          severityBadge(record.offence_sections),
          repeatOffenderBadge(record.offence_sections),
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
          severityBadge(record.offence_sections),
          repeatOffenderBadge(record.offence_sections),
          record.minor_involved ? minorBadge() : null,
        ]),
        el('p', { class: 'case-card__summary' }, record.summary || ''),
        daysTicker(record),
        el('div', { class: 'case-card__meta' }, meta),
        el('span', { class: 'case-card__id' }, record.id),
      ],
    ),
  ]);
}
