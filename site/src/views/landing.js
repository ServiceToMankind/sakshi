// Landing / overview route. Loads only summary.json. Renders animated totals, a
// status donut with an accessible legend, an SVG state tile-grid, and a 24-month
// trend line. Handles offline, stale (>48h), and empty (genesis) states.

import { el } from '../dom.js';
import { t } from '../i18n/index.js';
import { loadSummary } from '../data.js';
import { countUp, renderDonut, renderTrend, renderStateGrid, statusLegend } from '../charts.js';
import { ACTIVE_STATUSES, hoursSince } from '../format.js';

function statTile(valueNode, labelKey) {
  return el('div', { class: 'stat' }, [
    valueNode,
    el('span', { class: 'stat__label', 'data-i18n': labelKey }, t(labelKey)),
  ]);
}

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
      el('p', { class: 'empty__title' }, t('app_title')),
      el('p', { class: 'empty__text' }, t('landing_lead')),
      el('p', { class: 'muted', 'data-i18n': 'no_results' }, t('no_results')),
    ]),
  ]);
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

  const statusCounts = summary.status_counts || {};
  const stateCounts = summary.state_counts || {};
  const monthly = summary.monthly_trend || [];
  const activeTotal = Object.entries(statusCounts).reduce(
    (n, [s, c]) => n + (ACTIVE_STATUSES.has(s) ? c : 0),
    0,
  );
  const closedTotal = total - activeTotal;
  const stale = hoursSince(summary.generated_at) > 48;

  const totalNode = el('span', { class: 'stat__value' }, '0');
  const activeNode = el('span', { class: 'stat__value' }, '0');
  const closedNode = el('span', { class: 'stat__value' }, '0');
  const donutCanvas = el('canvas', { 'aria-hidden': 'true' });
  const trendCanvas = el('canvas', { role: 'img', 'aria-label': t('section_trend') });
  const gridWrap = el('div', { class: 'state-grid-wrap' });
  renderStateGrid(gridWrap, stateCounts); // built synchronously — avoids post-load layout shift

  const node = el('div', { class: 'view view--landing' }, [
    stale ? notice('stale', 'stale_notice') : null,
    el('section', { class: 'lead reveal' }, [
      el('p', { class: 'lead__tagline', 'data-i18n': 'tagline' }, t('tagline')),
      el('p', { class: 'lead__text', 'data-i18n': 'landing_lead' }, t('landing_lead')),
    ]),
    el('section', { class: 'stats reveal', 'aria-label': t('stat_total') }, [
      statTile(totalNode, 'stat_total'),
      statTile(activeNode, 'stat_active'),
      statTile(closedNode, 'stat_closed'),
    ]),
    el('section', { class: 'panel reveal' }, [
      el('h2', { class: 'panel__title', 'data-i18n': 'section_status' }, t('section_status')),
      el('div', { class: 'donut-wrap' }, [
        el('div', { class: 'donut' }, donutCanvas),
        statusLegend(statusCounts),
      ]),
    ]),
    el('section', { class: 'panel reveal' }, [
      el('h2', { class: 'panel__title', 'data-i18n': 'section_states' }, t('section_states')),
      gridWrap,
    ]),
    el('section', { class: 'panel reveal' }, [
      el('h2', { class: 'panel__title', 'data-i18n': 'section_trend' }, t('section_trend')),
      el('div', { class: 'trend' }, trendCanvas),
    ]),
  ]);

  // Charts and count-ups run after the node is mounted (next frame).
  requestAnimationFrame(() => {
    if (!node.isConnected) return;
    countUp(totalNode, total);
    countUp(activeNode, activeTotal);
    countUp(closedNode, closedTotal);
    renderDonut(donutCanvas, statusCounts);
    renderTrend(trendCanvas, monthly);
  });

  return node;
}
