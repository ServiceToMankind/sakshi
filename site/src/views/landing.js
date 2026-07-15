// Landing / overview route. The record itself is the landing page: a compact
// stat strip, then the "Recent cases" feed (primary content, from recent.json),
// then charts below — collapsed by default on mobile. A persistent search +
// filter bar sits atop the feed. Handles offline, stale (>48h), empty (genesis),
// and a missing/empty recent.json (feed empty-state) distinctly.

import { el, clear } from '../dom.js';
import { t, applyI18n } from '../i18n/index.js';
import { loadSummary, loadRecent } from '../data.js';
import { renderDonut, renderTrend, renderStateGrid, statusLegend } from '../charts.js';
import { ACTIVE_STATUSES, hoursSince, stateName, statusLabel, formatNumber } from '../format.js';
import { recentCard } from './parts.js';

function notice(kind, key) {
  return el('p', { class: `notice notice--${kind}`, role: 'status', 'data-i18n': key }, t(key));
}

function noticeView(key) {
  return el('div', { class: 'view view--notice' }, [
    el('p', { class: 'notice', role: 'status', 'data-i18n': key }, t(key)),
  ]);
}

function emptyGenesis() {
  return el('div', { class: 'view view--empty' }, [
    el('div', { class: 'empty empty--genesis reveal' }, [
      el('p', { class: 'lead__tagline', 'data-i18n': 'tagline' }, t('tagline')),
      el('p', { class: 'empty__title', 'data-i18n': 'genesis_title' }, t('genesis_title')),
      el('p', { class: 'empty__text', 'data-i18n': 'genesis_text' }, t('genesis_text')),
    ]),
  ]);
}

// --- Stat strip ----------------------------------------------------------
function statStripItem(value, labelKey) {
  return el('span', { class: 'stat-strip__item' }, [
    el('span', { class: 'stat-strip__value' }, formatNumber(value)),
    el('span', { class: 'stat-strip__label', 'data-i18n': labelKey }, t(labelKey)),
  ]);
}

function statStrip(total, active, closed) {
  const sep = () => el('span', { class: 'stat-strip__sep', 'aria-hidden': 'true' }, '·');
  return el('section', { class: 'stat-strip reveal', 'aria-label': t('stat_total') }, [
    statStripItem(total, 'stat_total'),
    sep(),
    statStripItem(active, 'stat_active'),
    sep(),
    statStripItem(closed, 'stat_closed'),
  ]);
}

// --- Recent feed ---------------------------------------------------------
function uniqueSorted(values, keyer) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => keyer(a).localeCompare(keyer(b)));
}

function filterRecent(records, f) {
  const q = f.q.trim().toLowerCase();
  return records.filter((r) => {
    if (f.state && r.state !== f.state) return false;
    if (f.status && r.status !== f.status) return false;
    if (f.category && r.category !== f.category) return false;
    if (q) {
      const hay = [r.title, r.summary, r.district, r.publisher, stateName(r.state)]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function feedSelect(name, labelKey, options, onChange) {
  const select = el(
    'select',
    { id: `feed-${name}`, name, onchange: (e) => onChange(name, e.target.value) },
    options.map((o) => el('option', { value: o.value }, o.label)),
  );
  return el('label', { class: 'filter' }, [
    el('span', { class: 'filter__label', 'data-i18n': labelKey }, t(labelKey)),
    select,
  ]);
}

/** A self-contained, client-side filtered feed. Order (newest-first) is preserved. */
function recentFeed(records) {
  const filters = { q: '', state: '', status: '', category: '' };
  const list = el('ul', { class: 'feed', 'aria-live': 'polite' });
  const count = el('p', { class: 'muted feed__count' });

  const allOpt = { value: '', label: t('filter_all') };
  const stateOpts = [
    allOpt,
    ...uniqueSorted(
      records.map((r) => r.state),
      stateName,
    ).map((s) => ({ value: s, label: stateName(s) })),
  ];
  const statusOpts = [
    allOpt,
    ...uniqueSorted(
      records.map((r) => r.status),
      statusLabel,
    ).map((s) => ({ value: s, label: statusLabel(s) })),
  ];
  const categoryOpts = [
    allOpt,
    ...uniqueSorted(
      records.map((r) => r.category),
      (c) => c,
    ).map((c) => ({ value: c, label: c })),
  ];

  const draw = () => {
    const filtered = records.length ? filterRecent(records, filters) : [];
    clear(list);
    if (!records.length) {
      count.textContent = '';
      list.append(
        el('li', { class: 'feed__empty', role: 'status' }, [
          el('p', { 'data-i18n': 'recent_empty' }, t('recent_empty')),
        ]),
      );
    } else if (!filtered.length) {
      count.textContent = '';
      list.append(
        el('li', { class: 'feed__empty', role: 'status' }, [
          el('p', { 'data-i18n': 'no_results' }, t('no_results')),
          el('p', { class: 'empty__hint', 'data-i18n': 'no_results_hint' }, t('no_results_hint')),
        ]),
      );
    } else {
      count.textContent = `${filtered.length} ${t('results_count')}`;
      filtered.forEach((r) => list.append(recentCard(r)));
    }
    applyI18n(list);
  };

  const onChange = (key, value) => {
    filters[key] = value;
    draw();
  };

  const search = el('input', {
    type: 'search',
    id: 'feed-q',
    name: 'q',
    placeholder: t('recent_search'),
    'aria-label': t('recent_search'),
    oninput: debounce((e) => onChange('q', e.target.value), 200),
  });

  const bar = el(
    'form',
    { class: 'filters filters--feed', role: 'search', onsubmit: (e) => e.preventDefault() },
    [
      el('label', { class: 'filter filter--search' }, [
        el('span', { class: 'filter__label', 'data-i18n': 'recent_search' }, t('recent_search')),
        search,
      ]),
      feedSelect('state', 'filter_state', stateOpts, onChange),
      feedSelect('status', 'filter_status', statusOpts, onChange),
      feedSelect('category', 'filter_category', categoryOpts, onChange),
      records.length
        ? el(
            'button',
            {
              type: 'button',
              class: 'btn btn--ghost filter__clear',
              onclick: () => {
                filters.q = '';
                filters.state = '';
                filters.status = '';
                filters.category = '';
                search.value = '';
                bar.querySelectorAll('select').forEach((s) => (s.value = ''));
                draw();
              },
            },
            t('filter_clear'),
          )
        : null,
    ],
  );

  draw();

  return el('section', { class: 'recent', 'aria-labelledby': 'recent-title' }, [
    el('div', { class: 'recent__head' }, [
      el(
        'h2',
        { class: 'panel__title recent__title', id: 'recent-title', 'data-i18n': 'section_recent' },
        t('section_recent'),
      ),
      el(
        'a',
        { class: 'recent__explore', href: '#/explore', 'data-i18n': 'recent_explore_all' },
        t('recent_explore_all'),
      ),
    ]),
    el('p', { class: 'muted recent__lead', 'data-i18n': 'recent_lead' }, t('recent_lead')),
    bar,
    count,
    list,
  ]);
}

// --- Charts (below the feed; collapsed by default on mobile) --------------
function chartsSection(statusCounts, stateCounts, monthly) {
  const donutCanvas = el('canvas', { 'aria-hidden': 'true' });
  const trendCanvas = el('canvas', { role: 'img', 'aria-label': t('section_trend') });
  const gridWrap = el('div', { class: 'state-grid-wrap' });
  renderStateGrid(gridWrap, stateCounts); // synchronous SVG — no post-load layout shift

  const wide = window.matchMedia?.('(min-width: 48rem)').matches ?? true;
  const details = el('details', { class: 'charts', open: wide }, [
    el('summary', { class: 'charts__summary' }, [
      el('span', { 'data-i18n': 'section_charts' }, t('section_charts')),
    ]),
    el('div', { class: 'charts__body' }, [
      el('section', { class: 'panel' }, [
        el('h3', { class: 'panel__title', 'data-i18n': 'section_status' }, t('section_status')),
        el('div', { class: 'donut-wrap' }, [
          el('div', { class: 'donut' }, donutCanvas),
          statusLegend(statusCounts),
        ]),
      ]),
      el('section', { class: 'panel' }, [
        el('h3', { class: 'panel__title', 'data-i18n': 'section_states' }, t('section_states')),
        gridWrap,
      ]),
      el('section', { class: 'panel' }, [
        el('h3', { class: 'panel__title', 'data-i18n': 'section_trend' }, t('section_trend')),
        el('div', { class: 'trend' }, trendCanvas),
      ]),
    ]),
  ]);

  // Canvas charts need a laid-out (non-display:none) canvas to size correctly, so
  // render them only once the <details> is actually open — immediately when open
  // at mount (desktop), or on first expand (mobile).
  let drawn = false;
  const drawCharts = () => {
    if (drawn || !details.isConnected) return;
    drawn = true;
    renderDonut(donutCanvas, statusCounts);
    renderTrend(trendCanvas, monthly);
  };
  details.addEventListener('toggle', () => {
    if (details.open) drawCharts();
  });

  return { details, drawCharts, isOpen: () => details.open };
}

export async function renderLanding() {
  let summary;
  try {
    summary = await loadSummary();
  } catch {
    return noticeView(navigator.onLine === false ? 'offline_notice' : 'error_generic');
  }

  const total = summary.total || 0;
  if (total === 0) return emptyGenesis();

  // The feed degrades gracefully: a missing/empty recent.json yields an empty
  // feed (with its own message) while the stat strip and charts still render.
  let recent = [];
  try {
    const data = await loadRecent();
    if (Array.isArray(data)) recent = data;
  } catch {
    recent = [];
  }

  const statusCounts = summary.status_counts || {};
  const stateCounts = summary.state_counts || {};
  const monthly = summary.monthly_trend || [];
  const activeTotal = Object.entries(statusCounts).reduce(
    (n, [s, c]) => n + (ACTIVE_STATUSES.has(s) ? c : 0),
    0,
  );
  const closedTotal = total - activeTotal;
  const stale = hoursSince(summary.generated_at) > 48;

  const charts = chartsSection(statusCounts, stateCounts, monthly);

  const node = el('div', { class: 'view view--landing' }, [
    stale ? notice('stale', 'stale_notice') : null,
    el('section', { class: 'lead reveal' }, [
      el('p', { class: 'lead__tagline', 'data-i18n': 'tagline' }, t('tagline')),
      el('p', { class: 'lead__text', 'data-i18n': 'landing_lead' }, t('landing_lead')),
    ]),
    statStrip(total, activeTotal, closedTotal),
    recentFeed(recent),
    el('section', { class: 'charts-wrap reveal' }, [charts.details]),
  ]);

  // If the charts panel is open at mount (desktop), draw once the node is laid out.
  requestAnimationFrame(() => {
    if (node.isConnected && charts.isOpen()) charts.drawCharts();
  });

  return node;
}
