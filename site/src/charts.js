// Infographics: a count-up, a hand-built SVG state tile-grid, a horizontal status-distribution
// bar, and a 24-month trend area — all hand-built SVG/HTML (no charting library), so the whole
// set is light, theme-aware (colors read from CSS custom properties), and renders synchronously
// with no post-load layout shift.

import { el } from './dom.js';
import { statusLabel, stateName } from './format.js';
import { prefersReducedMotion } from './animations.js';

const SVG_NS = 'http://www.w3.org/2000/svg';

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

// Status → CSS variable. ACQUITTED/QUASHED get their own clear colors — never
// muted relative to CONVICTED.
const STATUS_VAR = {
  FIR_FILED: '--c-fir',
  CHARGESHEETED: '--c-charge',
  UNDER_TRIAL: '--c-trial',
  APPEAL_PENDING: '--c-appeal',
  CONVICTED: '--c-convicted',
  ACQUITTED: '--c-acquitted',
  QUASHED: '--c-quashed',
  CLOSED: '--c-closed',
  UNKNOWN: '--c-unknown',
};

export function statusColor(status) {
  return cssVar(STATUS_VAR[status] || '--c-unknown', '#888');
}

/** Animate `node` from 0 to `target`; jumps straight to target under reduced motion. */
export function countUp(node, target, durationMs = 900) {
  const end = Number(target) || 0;
  const fmt = (n) => new Intl.NumberFormat().format(Math.round(n));
  if (prefersReducedMotion() || end === 0) {
    node.textContent = fmt(end);
    return;
  }
  const start = performance.now();
  const tick = (now) => {
    const p = Math.min((now - start) / durationMs, 1);
    const eased = 1 - (1 - p) ** 3;
    node.textContent = fmt(end * eased);
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/**
 * A horizontal status-distribution bar: one segment per status, width ∝ its share, in the
 * reserved status palette. Identity is never colour-alone — the accompanying `statusLegend`
 * labels every segment, and each segment carries a native `<title>` tooltip. Part-to-whole across
 * many statuses reads more cleanly here than in a donut, and it costs no charting library.
 */
export function statusBar(statusCounts) {
  const entries = Object.entries(statusCounts).filter(([, n]) => n > 0);
  // Each segment's flex-grow ∝ its count, so widths are proportional with no total to compute.
  return el(
    'div',
    { class: 'status-bar', role: 'img', 'aria-label': 'Case status distribution' },
    entries.map(([status, n]) =>
      el('span', {
        class: 'status-bar__seg',
        title: `${statusLabel(status)}: ${n}`,
        style: `flex-grow:${n};background:${statusColor(status)}`,
      }),
    ),
  );
}

/**
 * A 24-month trend as a hand-built SVG area — accent stroke + soft fill, a baseline, a dot on the
 * latest month, and one invisible hit-column per month carrying a `<title>` (month + count) so the
 * whole set is hoverable natively with no JS. viewBox units are virtual; CSS sizes it responsively
 * (non-scaling stroke keeps the line crisp at any width).
 */
export function trendChart(monthly) {
  const data = monthly.map((m) => Number(m.count) || 0);
  const W = 240;
  const H = 60;
  const pad = 4;
  const n = data.length;
  const max = Math.max(1, ...data);
  const xAt = (i) => (n <= 1 ? W / 2 : pad + (i / (n - 1)) * (W - 2 * pad));
  const yAt = (v) => H - pad - (v / max) * (H - 2 * pad);
  const pts = data.map((v, i) => `${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`);

  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('class', 'trend-svg');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Cases entering the record per month, last 24 months');

  if (n > 1) {
    const area = document.createElementNS(SVG_NS, 'path');
    area.setAttribute('d', `M${xAt(0)},${H - pad} L${pts.join(' L')} L${xAt(n - 1)},${H - pad} Z`);
    area.setAttribute('class', 'trend-svg__area');
    const line = document.createElementNS(SVG_NS, 'path');
    line.setAttribute('d', `M${pts.join(' L')}`);
    line.setAttribute('class', 'trend-svg__line');
    svg.append(area, line);
  }
  // Latest-month dot.
  if (n) {
    const dot = document.createElementNS(SVG_NS, 'circle');
    dot.setAttribute('cx', xAt(n - 1));
    dot.setAttribute('cy', yAt(data[n - 1]));
    dot.setAttribute('r', 2.5);
    dot.setAttribute('class', 'trend-svg__dot');
    svg.append(dot);
  }
  // Invisible per-month hit columns with a native tooltip.
  const colW = n ? (W - 2 * pad) / n : W;
  monthly.forEach((m, i) => {
    const hit = document.createElementNS(SVG_NS, 'rect');
    hit.setAttribute('x', (xAt(i) - colW / 2).toFixed(1));
    hit.setAttribute('y', '0');
    hit.setAttribute('width', colW.toFixed(1));
    hit.setAttribute('height', String(H));
    hit.setAttribute('fill', 'transparent');
    const title = document.createElementNS(SVG_NS, 'title');
    title.textContent = `${m.month}: ${Number(m.count) || 0}`;
    hit.append(title);
    svg.append(hit);
  });

  const axis = el('div', { class: 'trend-axis', 'aria-hidden': 'true' }, [
    el('span', {}, monthly.length ? monthly[0].month : ''),
    el('span', {}, monthly.length ? monthly[monthly.length - 1].month : ''),
  ]);
  return el('div', { class: 'trend' }, [svg, axis]);
}

// Approximate geographic tile positions [col, row]. Not to scale — a recognizable
// arrangement, per spec (tile-grid, not a geo map).
const TILE_LAYOUT = {
  JK: [3, 0],
  LA: [4, 0],
  HP: [4, 1],
  PB: [3, 1],
  CH: [3, 2],
  UT: [5, 1],
  HR: [4, 2],
  DL: [4, 3],
  RJ: [2, 3],
  UP: [5, 3],
  SK: [7, 2],
  AR: [9, 1],
  BR: [6, 3],
  AS: [8, 2],
  NL: [9, 2],
  ML: [8, 3],
  MN: [9, 3],
  MP: [4, 4],
  JH: [6, 4],
  WB: [7, 4],
  TR: [8, 4],
  MZ: [8, 5],
  GJ: [1, 4],
  DN: [2, 5],
  MH: [3, 5],
  CT: [5, 5],
  OD: [6, 5],
  TG: [4, 6],
  GA: [2, 6],
  KA: [3, 7],
  AP: [5, 7],
  TN: [4, 8],
  KL: [3, 8],
  PY: [5, 8],
  AN: [8, 7],
  LD: [1, 7],
};

/** Build an accessible SVG tile-grid; each tile links to #/explore?state=XX. */
export function renderStateGrid(container, stateCounts) {
  const codes = Object.keys(TILE_LAYOUT);
  // Any state with data but no layout slot gets appended to an overflow row.
  let overflowCol = 0;
  for (const code of Object.keys(stateCounts)) {
    if (!TILE_LAYOUT[code]) TILE_LAYOUT[code] = [overflowCol++, 10];
  }
  const cols = Math.max(...codes.map((c) => TILE_LAYOUT[c][0])) + 1;
  const rows = Math.max(...Object.values(TILE_LAYOUT).map((p) => p[1])) + 1;
  const max = Math.max(1, ...Object.values(stateCounts));
  const cell = 40;
  const gap = 6;
  const w = cols * (cell + gap);
  const h = rows * (cell + gap);

  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.setAttribute('class', 'state-grid');
  svg.setAttribute('role', 'group');
  svg.setAttribute('aria-label', 'Cases by state');

  for (const code of Object.keys(TILE_LAYOUT)) {
    const [c, r] = TILE_LAYOUT[code];
    const count = stateCounts[code] || 0;
    const x = c * (cell + gap);
    const y = r * (cell + gap);
    const a = document.createElementNS(ns, 'a');
    a.setAttribute('href', `#/explore?state=${code}`);
    a.setAttribute('aria-label', `${stateName(code)}: ${count} cases`);

    const rect = document.createElementNS(ns, 'rect');
    rect.setAttribute('x', x);
    rect.setAttribute('y', y);
    rect.setAttribute('width', cell);
    rect.setAttribute('height', cell);
    rect.setAttribute('rx', 6);
    rect.setAttribute('class', count ? 'state-tile state-tile--data' : 'state-tile');
    rect.style.setProperty('--intensity', count ? (0.25 + 0.75 * (count / max)).toFixed(3) : '0');

    const label = document.createElementNS(ns, 'text');
    label.setAttribute('x', x + cell / 2);
    label.setAttribute('y', y + cell / 2 + 4);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('class', 'state-tile__label');
    label.textContent = code;

    const title = document.createElementNS(ns, 'title');
    title.textContent = `${stateName(code)}: ${count}`;

    a.append(rect, label, title);
    svg.append(a);
  }
  container.append(svg);
  return svg;
}

/** A simple accessible legend (list) for the status donut. */
export function statusLegend(statusCounts) {
  const items = Object.entries(statusCounts)
    .filter(([, n]) => n > 0)
    .map(([status, n]) =>
      el('li', { class: 'legend__item' }, [
        el('span', { class: 'legend__swatch', style: `background:${statusColor(status)}` }),
        el('span', { class: 'legend__label' }, statusLabel(status)),
        el('span', { class: 'legend__count' }, String(n)),
      ]),
    );
  return el('ul', { class: 'legend', 'aria-label': 'Status legend' }, items);
}
