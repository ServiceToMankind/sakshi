// Case detail route. Renders the presumption-of-innocence banner (always), an
// animated status timeline, case details, accused (names only from court records),
// a cited sources list, and a "report a correction" link that opens a prefilled
// GitHub issue. ACQUITTED/QUASHED are shown with the same prominence as CONVICTED.

import { el } from '../dom.js';
import { t } from '../i18n/index.js';
import { loadCase } from '../data.js';
import { formatDate, stateName, safeHttpUrl } from '../format.js';
import {
  statusBadge,
  minorBadge,
  severityBadge,
  repeatOffenderBadge,
  daysTicker,
} from './parts.js';

const REPO = 'https://github.com/ServiceToMankind/sakshi';

function timeline(record) {
  const history = (record.status_history || [])
    .slice()
    .sort((a, b) => String(a.date).localeCompare(String(b.date)));
  const steps = history.length ? history : [{ status: record.status, date: null }];
  return el(
    'ol',
    { class: 'timeline' },
    steps.map((step, i) =>
      el('li', { class: `timeline__step${i === steps.length - 1 ? ' is-current' : ''}` }, [
        el('span', { class: 'timeline__dot', 'aria-hidden': 'true' }),
        el('div', { class: 'timeline__body' }, [
          statusBadge(step.status),
          step.date
            ? el('time', { datetime: step.date, class: 'timeline__date' }, formatDate(step.date))
            : null,
        ]),
      ]),
    ),
  );
}

function detailRow(labelKey, value) {
  if (value == null || value === '') return null;
  return el('div', { class: 'detail' }, [
    el('dt', { class: 'detail__label', 'data-i18n': labelKey }, t(labelKey)),
    el('dd', { class: 'detail__value' }, value),
  ]);
}

function accusedSection(record) {
  // Guardrail (CLAUDE.md §1a): a minor's record never surfaces an accused — naming an
  // offender in a child case is a re-identification vector (accused↔victim proximity).
  // The pipeline already withholds a minor's accused name; this is defence-in-depth so
  // the UI can never render one regardless of what a record happens to carry.
  if (record.minor_involved) return null;
  const accused = record.accused || [];
  if (!accused.length) return null;
  const list = el(
    'ul',
    { class: 'accused' },
    accused.map((a) =>
      el('li', { class: 'accused__item' }, [
        el('span', { class: 'accused__label' }, a.label),
        el(
          'span',
          {
            class: a.name_public_court_record
              ? 'accused__name'
              : 'accused__name accused__name--withheld',
          },
          a.name_public_court_record || t('accused_withheld'),
        ),
        statusBadge(a.status),
      ]),
    ),
  );
  return el('section', { class: 'panel reveal' }, [
    el('h2', { class: 'panel__title', 'data-i18n': 'case_accused' }, t('case_accused')),
    list,
  ]);
}

function sourcesSection(record) {
  const list = el(
    'ul',
    { class: 'sources' },
    (record.sources || []).map((s) =>
      el('li', { class: 'source' }, [
        el(
          'a',
          {
            href: safeHttpUrl(s.url),
            target: '_blank',
            rel: 'noopener noreferrer',
            class: 'source__link',
          },
          s.publisher || s.url,
        ),
        el('span', { class: 'source__meta' }, formatDate(s.retrieved)),
      ]),
    ),
  );
  return el('section', { class: 'panel reveal' }, [
    el('h2', { class: 'panel__title', 'data-i18n': 'case_sources' }, t('case_sources')),
    list,
  ]);
}

function notFound(id) {
  return el('div', { class: 'view view--notice' }, [
    el('a', { href: '#/explore', class: 'crumb' }, `← ${t('nav_explore')}`),
    el('p', { class: 'notice', role: 'status' }, `${t('error_generic')} (${id || ''})`),
  ]);
}

export async function renderCase(route) {
  let record;
  try {
    record = await loadCase(route.id);
  } catch {
    record = null;
  }
  if (!record) return notFound(route.id);

  const correctionUrl = `${REPO}/issues/new?template=data-correction.yml&title=${encodeURIComponent(
    `Data correction: ${record.id}`,
  )}`;
  const fir = record.fir_ref
    ? `${record.fir_ref.station || ''} ${record.fir_ref.number || ''}`.trim()
    : '';

  return el('article', { class: 'view view--case', tabindex: '-1' }, [
    el(
      'p',
      { class: 'presumption-banner', role: 'note', 'data-i18n': 'presumption_banner' },
      t('presumption_banner'),
    ),
    el('div', { class: 'case__head reveal' }, [
      el(
        'a',
        { href: record.state ? `#/explore?state=${record.state}` : '#/explore', class: 'crumb' },
        `← ${stateName(record.state)}`,
      ),
      el('div', { class: 'case__badges' }, [
        statusBadge(record.status),
        severityBadge(record.offence_sections),
        repeatOffenderBadge(record.offence_sections),
        record.minor_involved ? minorBadge() : null,
      ]),
      el('h1', { class: 'case__id' }, record.id),
      el('p', { class: 'case__summary' }, record.summary || ''),
      daysTicker(record),
    ]),
    el('section', { class: 'panel reveal' }, [
      el(
        'h2',
        { class: 'panel__title', 'data-i18n': 'case_status_timeline' },
        t('case_status_timeline'),
      ),
      timeline(record),
    ]),
    el('section', { class: 'panel reveal' }, [
      el(
        'dl',
        { class: 'details' },
        [
          detailRow('case_court', record.court?.name),
          detailRow(
            'case_next_hearing',
            record.court?.next_hearing ? formatDate(record.court.next_hearing) : null,
          ),
          detailRow('case_offences', (record.offence_sections || []).join(', ')),
          detailRow('case_reported', formatDate(record.incident_reported_date)),
          record.pending_days != null
            ? detailRow('case_pending', `${record.pending_days} ${t('case_pending_days')}`)
            : null,
          detailRow('case_cnr', record.cnr),
          detailRow('case_fir', fir),
        ].filter(Boolean),
      ),
    ]),
    accusedSection(record),
    sourcesSection(record),
    el('div', { class: 'case__actions reveal' }, [
      el(
        'a',
        {
          class: 'btn',
          href: correctionUrl,
          target: '_blank',
          rel: 'noopener noreferrer',
          'data-i18n': 'case_report_correction',
        },
        t('case_report_correction'),
      ),
    ]),
  ]);
}
