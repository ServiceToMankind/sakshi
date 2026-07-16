// Accountability-layer landing sections, all built from public/aggregate data only
// (CLAUDE.md §1a): the scale drumbeat + daily heat strip (summary.scale), the sortable
// jurisdiction scorecard (summary.jurisdictions), and the offender scorecard (court-
// sourced named accused, non-minor only). None of these surface any victim particular.

import { el, clear } from '../dom.js';
import { t, applyI18n } from '../i18n/index.js';
import { stateName, formatDate, formatNumber } from '../format.js';
import { statusBadge, severityBadge } from './parts.js';
import { loadAllRecords } from '../data.js';

// --- Scale drumbeat + daily heat strip -----------------------------------

/**
 * A horizontal calendar heat strip of the daily INGESTION histogram (when cases were
 * recorded — an ingestion date, never an incident date, so it is non-identifying and
 * works for minors too). Colour intensity scales with the day's count. The strip is a
 * single labelled image for assistive tech (per-day counts are exposed as native
 * tooltips); it degrades to a note when there is no history yet.
 */
function heatStrip(daily) {
  const days = Array.isArray(daily) ? daily.filter((d) => d && typeof d.date === 'string') : [];
  if (!days.length) {
    return el(
      'p',
      { class: 'muted heat-strip__empty', 'data-i18n': 'scale_no_history' },
      t('scale_no_history'),
    );
  }
  const counts = days.map((d) => Number(d.count) || 0);
  const max = Math.max(1, ...counts);
  const total = counts.reduce((n, c) => n + c, 0);
  const peak = days.reduce((best, d) =>
    (Number(d.count) || 0) > (Number(best.count) || 0) ? d : best,
  );

  const cells = days.map((d) => {
    const count = Number(d.count) || 0;
    const cell = el('span', {
      class: count ? 'heat-cell heat-cell--data' : 'heat-cell',
      title: `${d.date}: ${count}`,
    });
    cell.style.setProperty('--intensity', (count ? 0.2 + 0.8 * (count / max) : 0).toFixed(3));
    return cell;
  });

  const label = total
    ? `${t('scale_heat_label')} — ${t('scale_heat_peak')} ${peak.count} (${peak.date})`
    : `${t('scale_heat_label')} — ${t('scale_no_history')}`;

  return el('div', { class: 'heat-strip' }, [
    el('div', { class: 'heat-strip__cells', role: 'img', 'aria-label': label }, cells),
    el('div', { class: 'heat-strip__axis', 'aria-hidden': 'true' }, [
      el('span', {}, days[0].date),
      el('span', {}, days[days.length - 1].date),
    ]),
  ]);
}

/** The scale drumbeat: cases this week + cumulative total + aggravated count + heat strip. */
export function scaleDrumbeat(summary) {
  const scale = summary && summary.scale ? summary.scale : null;
  if (!scale) return null;
  const thisWeek = Number(scale.this_week) || 0;
  const cumulative = Number(scale.cumulative_total) || 0;
  const aggravated = Number(summary.aggravated_total) || 0;

  const line = (num, labelKey, extraClass) =>
    el('p', { class: `drumbeat__line${extraClass ? ` ${extraClass}` : ''}` }, [
      el('span', { class: 'drumbeat__num' }, formatNumber(num)),
      ' ',
      el('span', { class: 'drumbeat__label', 'data-i18n': labelKey }, t(labelKey)),
    ]);

  return el('section', { class: 'drumbeat reveal', 'aria-labelledby': 'scale-title' }, [
    el(
      'h2',
      { class: 'drumbeat__title', id: 'scale-title', 'data-i18n': 'section_scale' },
      t('section_scale'),
    ),
    el('div', { class: 'drumbeat__stats' }, [
      line(thisWeek, 'scale_this_week', 'drumbeat__line--week'),
      line(cumulative, 'scale_cumulative', 'drumbeat__line--total'),
      aggravated ? line(aggravated, 'scale_aggravated', 'drumbeat__line--aggravated') : null,
    ]),
    heatStrip(scale.daily),
  ]);
}

// --- Jurisdiction scorecard (sortable) -----------------------------------

// Column spec. `value` feeds the client-side sort; `cell` renders the display node.
// Numeric columns sort descending first (worst-first for accountability); the place
// column sorts ascending. A null median (all-minor jurisdiction) always sorts last.
const COLUMNS = [
  {
    key: 'place',
    i18n: 'jur_col_place',
    type: 'text',
    sortable: true,
    value: (j) => `${stateName(j.state)} ${j.district || ''}`,
    cell: (j) =>
      el('span', { class: 'scorecard__place' }, [
        el('span', { class: 'scorecard__state' }, stateName(j.state)),
        el('span', { class: 'scorecard__district' }, j.district || '—'),
      ]),
  },
  {
    key: 'total',
    i18n: 'jur_col_cases',
    type: 'num',
    sortable: true,
    value: (j) => j.total,
    cell: (j) => formatNumber(j.total),
  },
  {
    key: 'under_trial_pct',
    i18n: 'jur_col_under_trial',
    type: 'num',
    sortable: true,
    value: (j) => j.under_trial_pct,
    cell: (j) => `${Number(j.under_trial_pct) || 0}%`,
  },
  {
    key: 'median_pending_days',
    i18n: 'jur_col_median_pending',
    type: 'num',
    sortable: true,
    value: (j) => j.median_pending_days,
    cell: (j) => (j.median_pending_days == null ? '—' : formatNumber(j.median_pending_days)),
  },
  {
    key: 'convictions',
    i18n: 'jur_col_convictions',
    type: 'num',
    sortable: true,
    value: (j) => j.convictions,
    cell: (j) => formatNumber(j.convictions),
  },
  {
    key: 'acquittals',
    i18n: 'jur_col_acquittals',
    type: 'num',
    sortable: false,
    value: (j) => j.acquittals,
    cell: (j) => formatNumber(j.acquittals),
  },
  {
    key: 'longest',
    i18n: 'jur_col_longest',
    type: 'text',
    sortable: false,
    value: (j) => (j.longest_pending ? j.longest_pending.days : null),
    cell: (j) =>
      j.longest_pending
        ? el(
            'a',
            {
              class: 'scorecard__longest',
              href: `#/case/${encodeURIComponent(j.longest_pending.id)}`,
            },
            `${j.longest_pending.id}: ${formatNumber(j.longest_pending.days)} ${t('case_pending_days')}`,
          )
        : '—',
  },
];

function compareBy(col, dir) {
  return (a, b) => {
    const av = col.value(a);
    const bv = col.value(b);
    // Nulls (e.g. an all-minor jurisdiction's median) sort last, both directions.
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = col.type === 'num' ? av - bv : String(av).localeCompare(String(bv));
    return dir === 'asc' ? cmp : -cmp;
  };
}

/**
 * The institutional-shame engine: a sortable per-(state, district) scorecard from
 * summary.jurisdictions. Aggregate/public counts only — no case-level or victim data.
 * Returns null when there are no jurisdictions (landing simply omits the section).
 */
export function jurisdictionScorecard(jurisdictions) {
  const rows = Array.isArray(jurisdictions) ? jurisdictions : [];
  if (!rows.length) return null;

  const sort = { key: 'total', dir: 'desc' };
  const tbody = el('tbody');

  const heads = COLUMNS.map((col) => {
    if (!col.sortable) {
      return {
        col,
        th: el('th', { scope: 'col' }, el('span', { 'data-i18n': col.i18n }, t(col.i18n))),
      };
    }
    const caret = el('span', { class: 'scorecard__caret', 'aria-hidden': 'true' }, '');
    const btn = el('button', { type: 'button', class: 'scorecard__sort' }, [
      el('span', { 'data-i18n': col.i18n }, t(col.i18n)),
      caret,
    ]);
    const th = el('th', { scope: 'col', 'aria-sort': 'none' }, btn);
    return { col, th, btn, caret };
  });

  const draw = () => {
    const col = COLUMNS.find((c) => c.key === sort.key);
    const sorted = [...rows].sort(compareBy(col, sort.dir));
    clear(tbody);
    sorted.forEach((j) => {
      const cells = COLUMNS.map((c) => {
        const content = c.cell(j);
        return c.key === 'place'
          ? el('th', { scope: 'row', class: 'scorecard__cell scorecard__cell--place' }, content)
          : el('td', { class: `scorecard__cell scorecard__cell--${c.key}` }, content);
      });
      tbody.append(el('tr', {}, cells));
    });
    heads.forEach(({ col: c, th, caret }) => {
      if (!c.sortable) return;
      const active = c.key === sort.key;
      th.setAttribute(
        'aria-sort',
        active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none',
      );
      caret.textContent = active ? (sort.dir === 'asc' ? '▲' : '▼') : '';
    });
    applyI18n(tbody);
  };

  heads.forEach(({ col, btn }) => {
    if (!col.sortable) return;
    btn.addEventListener('click', () => {
      if (sort.key === col.key) sort.dir = sort.dir === 'asc' ? 'desc' : 'asc';
      else {
        sort.key = col.key;
        sort.dir = col.key === 'place' ? 'asc' : 'desc';
      }
      draw();
    });
  });

  const table = el('table', { class: 'scorecard' }, [
    el(
      'thead',
      {},
      el(
        'tr',
        {},
        heads.map((h) => h.th),
      ),
    ),
    tbody,
  ]);
  draw();

  return el('section', { class: 'scorecard-section reveal', 'aria-labelledby': 'jur-title' }, [
    el('div', { class: 'scorecard-section__head' }, [
      el(
        'h2',
        { class: 'panel__title', id: 'jur-title', 'data-i18n': 'section_jurisdictions' },
        t('section_jurisdictions'),
      ),
      el('p', { class: 'muted scorecard-section__lead', 'data-i18n': 'jur_lead' }, t('jur_lead')),
    ]),
    el('div', { class: 'scorecard-wrap' }, table),
  ]);
}

// --- Offender scorecard (court-sourced named accused, non-minor only) ------

/**
 * Collect named offenders from published records. GUARDRAIL (CLAUDE.md §1a/§5): a name
 * is surfaced ONLY when it comes from an official court record
 * (`name_public_court_record`) AND ONLY for a NON-MINOR case — a minor's record never
 * surfaces an accused. Both filters are enforced here.
 */
function collectOffenders(records) {
  const offenders = [];
  for (const r of records) {
    if (r.minor_involved) continue; // never surface an accused for a minor
    for (const a of r.accused || []) {
      if (!a || !a.name_public_court_record) continue; // court-sourced names only
      offenders.push({
        name: a.name_public_court_record,
        status: a.status,
        sections: r.offence_sections || [],
        court: r.court && r.court.name ? r.court.name : '',
        date: r.incident_reported_date || '',
        caseId: r.id,
      });
    }
  }
  offenders.sort((x, y) => String(y.date).localeCompare(String(x.date)));
  return offenders;
}

function offenderCard(o) {
  const sev = severityBadge(o.sections);
  const offence =
    sev ||
    (o.sections.length ? el('span', { class: 'offender__offence' }, o.sections.join(', ')) : null);
  const meta = [
    o.court ? el('span', { class: 'offender__court' }, o.court) : null,
    o.date
      ? el('time', { class: 'offender__date', datetime: String(o.date) }, formatDate(o.date))
      : null,
  ].filter(Boolean);

  return el('li', { class: 'offender' }, [
    el('div', { class: 'offender__head' }, [
      el('span', { class: 'offender__name' }, o.name),
      statusBadge(o.status),
    ]),
    offence ? el('div', { class: 'offender__offence-row' }, [offence]) : null,
    meta.length ? el('div', { class: 'offender__meta' }, meta) : null,
    el('a', { class: 'offender__link', href: `#/case/${encodeURIComponent(o.caseId)}` }, o.caseId),
  ]);
}

function offenderEmpty() {
  return el('div', { class: 'offenders__empty', role: 'status' }, [
    el('p', { 'data-i18n': 'offenders_empty' }, t('offenders_empty')),
  ]);
}

/**
 * The offender scorecard. Records are loaded lazily (accused data lives in the shards,
 * not the summary) and populated in place, so the landing paints without waiting; the
 * empty-state stands until — and unless — court-recorded offenders arrive.
 */
export function offenderScorecard() {
  const body = el('div', { class: 'offenders__body' }, offenderEmpty());
  const section = el(
    'section',
    { class: 'scorecard-section reveal', 'aria-labelledby': 'off-title' },
    [
      el('div', { class: 'scorecard-section__head' }, [
        el(
          'h2',
          { class: 'panel__title', id: 'off-title', 'data-i18n': 'section_offenders' },
          t('section_offenders'),
        ),
        el(
          'p',
          { class: 'muted scorecard-section__lead', 'data-i18n': 'offenders_lead' },
          t('offenders_lead'),
        ),
      ]),
      body,
    ],
  );

  loadAllRecords()
    .then((records) => {
      const offenders = collectOffenders(records);
      if (!offenders.length) return; // keep the empty-state already rendered
      clear(body);
      body.append(el('ul', { class: 'offenders' }, offenders.map(offenderCard)));
      applyI18n(body);
    })
    .catch(() => {
      /* leave the empty-state in place */
    });

  return section;
}
