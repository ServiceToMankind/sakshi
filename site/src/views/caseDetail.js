// Case detail route — a real article, not a field dump. Structure (§2c):
//   presumption banner (always)
//   → What happened      (the plain-English account / minor projection + read-aloud of the page)
//   → Where justice stands (pendency counter, animated status timeline, court + case anchors)
//   → Severity           (plain-language label from PUBLIC charge codes, then the codes)
//   → Accused            (names only from court records; never for a minor)
//   → Sources            (cited; identifying-slug URLs behind an expander)
// ACQUITTED/QUASHED are shown with the same prominence as CONVICTED. Nothing here lowers the
// identity floor — the summary text is the sanitised record, severity is charge-derived, and a
// minor never surfaces an accused.

import { el } from '../dom.js';
import { t } from '../i18n/index.js';
import { loadCase } from '../data.js';
import {
  formatDate,
  stateName,
  statusLabel,
  safeHttpUrl,
  relativeRecency,
  POCSO_WITHHELD_SENTENCE,
} from '../format.js';
import {
  statusBadge,
  minorBadge,
  correctedBadge,
  severityBadge,
  repeatOffenderBadge,
  daysTicker,
  tracingMarker,
} from './parts.js';
import { severityLabel } from '../severity.js';
import { readAloudButton } from '../read-aloud.js';

const REPO = 'https://github.com/ServiceToMankind/sakshi';

// The statutory withholding sentence (POCSO_WITHHELD_SENTENCE, shared from format.js) is shown
// here as a de-emphasised FOOTNOTE rather than a sentence inside the summary prose (§6
// readability) — display only; the stored record text is unchanged.
function summaryBodyAndFootnote(summary) {
  const text = String(summary || '').trim();
  if (text.endsWith(POCSO_WITHHELD_SENTENCE)) {
    return {
      body: text.slice(0, -POCSO_WITHHELD_SENTENCE.length).trim(),
      footnote: POCSO_WITHHELD_SENTENCE,
    };
  }
  return { body: text, footnote: null };
}

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

// "What happened" — the account. For a non-minor this is the plain-English article summary;
// for a minor it is the deterministic, non-identifying projection. Same section, same heading.
function whatHappenedSection(record) {
  const { body, footnote } = summaryBodyAndFootnote(record.summary);
  const children = [
    sectionTitle('case_what_happened'),
    body ? el('p', { class: 'case__summary' }, body) : null,
  ];
  if (footnote) {
    children.push(el('p', { class: 'case__footnote', role: 'note' }, footnote));
  }
  return el('section', { class: 'panel reveal' }, children.filter(Boolean));
}

function sectionTitle(key) {
  return el('h2', { class: 'panel__title', 'data-i18n': key }, t(key));
}

// "Where justice stands" — the pendency counter first (the drumbeat), then the timeline, then
// the court + case-number anchors that make the pendency re-checkable.
function whereJusticeStandsSection(record) {
  const fir = record.fir_ref
    ? `${record.fir_ref.station || ''} ${record.fir_ref.number || ''}`.trim()
    : '';
  const details = [
    detailRow('case_court', record.court?.name),
    detailRow(
      'case_next_hearing',
      record.court?.next_hearing ? formatDate(record.court.next_hearing) : null,
    ),
    detailRow(
      'case_reported',
      record.incident_reported_date
        ? `${formatDate(record.incident_reported_date)}${
            relativeRecency(record.incident_reported_date)
              ? ` · ${relativeRecency(record.incident_reported_date)}`
              : ''
          }`
        : null,
    ),
    detailRow('case_cnr', record.cnr),
    detailRow('case_fir', fir),
  ].filter(Boolean);

  return el(
    'section',
    { class: 'panel reveal' },
    [
      sectionTitle('case_where_justice_stands'),
      daysTicker(record, { block: true }),
      timeline(record),
      details.length ? el('dl', { class: 'details' }, details) : null,
    ].filter(Boolean),
  );
}

// "Severity" — plain-language label derived ONLY from public charge sections (never the victim),
// then the raw charge codes for anyone who wants to check them. Rendered only when we have codes.
function severitySection(record) {
  const codes = record.offence_sections || [];
  if (!codes.length) return null;
  const badges = [severityBadge(codes), repeatOffenderBadge(codes)].filter(Boolean);
  return el(
    'section',
    { class: 'panel reveal' },
    [
      sectionTitle('case_severity'),
      badges.length ? el('div', { class: 'case__badges' }, badges) : null,
      el('p', { class: 'case__severity-note', 'data-i18n': 'severity_hint' }, t('severity_hint')),
      el('div', { class: 'charge-codes' }, [
        el(
          'span',
          { class: 'charge-codes__label', 'data-i18n': 'case_offences' },
          t('case_offences'),
        ),
        el(
          'ul',
          { class: 'charge-codes__list' },
          codes.map((c) => el('li', { class: 'charge-codes__item' }, String(c))),
        ),
      ]),
    ].filter(Boolean),
  );
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
  return el('section', { class: 'panel reveal' }, [sectionTitle('case_accused'), list]);
}

function sourceDomain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return t('case_view_source');
  }
}

function sourceItem(s) {
  // Anchor text is the publisher or the bare DOMAIN — NEVER the raw URL, whose slug can
  // state a detail the record withholds (§5). The href keeps the full URL (a citation must
  // be verifiable); the visible text does not expose the slug.
  return el('li', { class: 'source' }, [
    el(
      'a',
      {
        href: safeHttpUrl(s.url),
        target: '_blank',
        rel: 'noopener noreferrer',
        class: 'source__link',
      },
      s.publisher || sourceDomain(s.url),
    ),
    el('span', { class: 'source__meta' }, formatDate(s.retrieved)),
  ]);
}

function sourcesSection(record) {
  const all = record.sources || [];
  // Clean sources first (§5 "prefer clean source for display"); sources whose URL slug may
  // reveal a withheld detail go behind an expander, de-emphasised.
  const clean = all.filter((s) => !s.url_carries_identifying_slug);
  const flagged = all.filter((s) => s.url_carries_identifying_slug);
  const children = [sectionTitle('case_sources')];
  if (clean.length) {
    children.push(el('ul', { class: 'sources' }, clean.map(sourceItem)));
  }
  if (flagged.length) {
    children.push(
      el('details', { class: 'sources__flagged' }, [
        el('summary', { class: 'sources__flagged-summary' }, t('sources_identifying_summary')),
        el('p', { class: 'sources__flagged-note' }, t('sources_identifying_note')),
        el('ul', { class: 'sources' }, flagged.map(sourceItem)),
      ]),
    );
  }
  return el('section', { class: 'panel reveal' }, children);
}

// The read-aloud narration for the WHOLE page (§2c): what happened, where justice stands, and
// the charge-derived severity — the record spoken as an article, in reading order.
function pageNarration(record) {
  const { body } = summaryBodyAndFootnote(record.summary);
  const parts = [
    record.title || null,
    body || null,
    `${t('filter_status')}: ${statusLabel(record.status)}`,
    record.court?.name ? `${t('case_court')}: ${record.court.name}` : null,
    record.days_since_reported != null && !record.minor_involved
      ? `${record.days_since_reported} ${t('days_since_reported')}`
      : null,
    severityLabel(record.offence_sections)
      ? `${t('case_severity')}: ${severityLabel(record.offence_sections)}`
      : null,
  ];
  return parts.filter(Boolean).join('. ');
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
        record.corrected ? correctedBadge() : null,
        tracingMarker(record),
      ]),
      el('h1', { class: 'case__id' }, record.id),
      readAloudButton(pageNarration(record)),
    ]),
    whatHappenedSection(record),
    whereJusticeStandsSection(record),
    severitySection(record),
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
