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
  relativeRecency,
  summaryBody,
} from '../format.js';
import { severityLabel, severityCode, isAggravated, isRepeatOffender } from '../severity.js';
import { recordTier, hasCourtSource } from '../tier.js';

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

/** A "Corrected" marker for a record a reviewed human-authored correction has touched. */
export function correctedBadge() {
  return el(
    'span',
    { class: 'badge badge--corrected', 'data-i18n': 'corrected_flag' },
    t('corrected_flag'),
  );
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

/**
 * The source-tier tracing marker (§3), or null when the record is court-sourced and was
 * always so. Tells a reader/journalist/RTI activist exactly which cases have NOT reached the
 * visible judicial record — the accountability signal the project exists for.
 */
export function tracingMarker(record) {
  if (record.traced_to_court) {
    return el(
      'span',
      { class: 'badge badge--traced', title: t('traced_to_court_hint') },
      `${t('traced_to_court')} ${formatDate(record.traced_to_court)}`,
    );
  }
  if (hasCourtSource(record)) return null; // a court record, always tracked
  const tier = recordTier(record);
  if (tier <= 2) {
    return el(
      'span',
      { class: 'badge badge--legalpress', 'data-i18n': 'tier_legal' },
      t('tier_legal'),
    );
  }
  return el('span', { class: 'badge badge--media', 'data-i18n': 'tier_media' }, t('tier_media'));
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

// Pre-verdict statuses — the ones where "no verdict yet" is literally true. APPEAL_PENDING is
// excluded (a verdict exists; it is under appeal), so we never mis-state it.
const PRE_VERDICT_STATUSES = new Set(['FIR_FILED', 'CHARGESHEETED', 'UNDER_TRIAL']);

/**
 * The pendency ticker. Day-precise elapsed time exists ONLY for non-minor cases (a minor's
 * date is year-only by projection and `days_since_reported` is nulled), so this NEVER renders
 * on a minor card — a hard guardrail (CLAUDE.md §1a). Shown while the case is unresolved.
 *
 * Wording follows the source anchor, which is where the honesty lives:
 *   - COURT-ANCHORED (a re-checkable tier-1 record): "days without justice" — the framing the
 *     project exists for (§3, "aim the shame at power"). For a pre-verdict status it adds a
 *     factual "no verdict yet" line; the status badge + presumption banner still stand, so this
 *     is a statement about the SYSTEM's pendency, never about the accused's guilt.
 *   - MEDIA-ONLY (no court anchor yet): the neutral "days since first reported" — we do not
 *     assert "without justice" for a case that has not reached the judicial record.
 * Pass `{ block: true }` for the larger case-page treatment.
 */
export function daysTicker(record, { block = false } = {}) {
  if (record.minor_involved) return null;
  if (!isActiveStatus(record.status)) return null;
  if (record.days_since_reported == null) return null;
  const courtAnchored =
    hasCourtSource(record) || Boolean(record.court?.name) || Boolean(record.cnr);
  const cls =
    'days-ticker' +
    (courtAnchored ? ' days-ticker--accountability' : '') +
    (block ? ' days-ticker--block' : '');
  const children = [
    el('span', { class: 'days-ticker__num' }, formatNumber(record.days_since_reported)),
    el(
      'span',
      {
        class: 'days-ticker__label',
        'data-i18n': courtAnchored ? 'days_without_justice' : 'days_since_reported',
      },
      courtAnchored ? t('days_without_justice') : t('days_since_reported'),
    ),
  ];
  if (courtAnchored && PRE_VERDICT_STATUSES.has(String(record.status))) {
    children.push(
      el(
        'span',
        { class: 'days-ticker__note', 'data-i18n': 'days_no_verdict' },
        t('days_no_verdict'),
      ),
    );
  }
  return el('div', { class: cls, role: 'note' }, children);
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
          `${t('case_reported')} ${formatDate(date)}${
            relativeRecency(date) ? ` · ${relativeRecency(date)}` : ''
          }`,
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
          tracingMarker(record),
        ]),
        el('h3', { class: 'feed-card__title' }, record.title || record.id),
        summaryBody(record.summary)
          ? el('p', { class: 'feed-card__summary' }, summaryBody(record.summary))
          : null,
        // Pendency ticker — consistent with the explore card (§3 "days without justice on
        // every court-anchored card"). Null for minors / resolved / media-with-no-days.
        daysTicker(record),
        el('div', { class: 'feed-card__meta' }, meta),
      ],
    ),
  ]);
}

/** A tappable case card linking to the case detail route. */
export function caseCard(record) {
  // Compact, scannable meta: district + reported date only. The offence is already stated by the
  // severity badge (top) and the plain-English summary; the raw charge codes + the statutory
  // withholding line live on the case page, so a list card never repeats them.
  const reported = record.incident_reported_date;
  const meta = [
    record.district ? el('span', {}, record.district) : null,
    reported ? el('time', { datetime: String(reported) }, formatDate(reported)) : null,
  ].filter(Boolean);
  const body = summaryBody(record.summary);

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
        body ? el('p', { class: 'case-card__summary' }, body) : null,
        daysTicker(record),
        meta.length ? el('div', { class: 'case-card__meta' }, meta) : null,
        el('span', { class: 'case-card__id' }, record.id),
      ].filter(Boolean),
    ),
  ]);
}

/**
 * A windowed pagination control: ‹ 1 … 4 5 6 … 20 ›. Returns null for a single page.
 * `onSelect(page)` is called with the 1-based target page (the caller navigates or re-renders).
 */
export function pagination(current, totalPages, onSelect) {
  if (totalPages <= 1) return null;
  const cur = Math.min(Math.max(1, current), totalPages);
  const pageBtn = (label, page, { disabled = false, isCurrent = false, aria } = {}) =>
    el(
      'button',
      {
        type: 'button',
        class: `pager__btn${isCurrent ? ' is-current' : ''}`,
        disabled: disabled || isCurrent,
        'aria-current': isCurrent ? 'page' : null,
        'aria-label': aria || null,
        onclick: disabled || isCurrent ? null : () => onSelect(page),
      },
      label,
    );
  // Window: first, last, and cur±1, with … gaps.
  const nums = [];
  for (let p = 1; p <= totalPages; p += 1) {
    if (p === 1 || p === totalPages || (p >= cur - 1 && p <= cur + 1)) nums.push(p);
    else if (nums[nums.length - 1] !== '…') nums.push('…');
  }
  return el('nav', { class: 'pager', 'aria-label': t('pager_label') }, [
    pageBtn('‹', cur - 1, { disabled: cur <= 1, aria: t('pager_prev') }),
    ...nums.map((p) =>
      p === '…'
        ? el('span', { class: 'pager__gap', 'aria-hidden': 'true' }, '…')
        : pageBtn(String(p), p, { isCurrent: p === cur, aria: `${t('pager_page')} ${p}` }),
    ),
    pageBtn('›', cur + 1, { disabled: cur >= totalPages, aria: t('pager_next') }),
  ]);
}
