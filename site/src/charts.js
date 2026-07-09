// Charts: count-up, a status donut and 24-month trend line (Chart.js, tree-shaken
// to only the pieces we use), and a hand-built SVG state tile-grid (no heavy geo
// library). Colors are read from CSS custom properties so charts are theme-aware.

import { el } from './dom.js';
import { statusLabel, stateName } from './format.js';
import { prefersReducedMotion } from './animations.js';

// Chart.js is loaded lazily (its own chunk) so the initial paint — stat tiles and
// the state tile-grid — is not blocked by charting code.
let chartPromise = null;
function getChart() {
  if (!chartPromise) {
    chartPromise = import('chart.js').then((m) => {
      m.Chart.register(
        m.ArcElement,
        m.DoughnutController,
        m.LineController,
        m.LineElement,
        m.PointElement,
        m.LinearScale,
        m.CategoryScale,
        m.Filler,
        m.Tooltip,
      );
      return m.Chart;
    });
  }
  return chartPromise;
}

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

export async function renderDonut(canvas, statusCounts) {
  const entries = Object.entries(statusCounts).filter(([, n]) => n > 0);
  const Chart = await getChart();
  return new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: entries.map(([s]) => statusLabel(s)),
      datasets: [
        {
          data: entries.map(([, n]) => n),
          backgroundColor: entries.map(([s]) => statusColor(s)),
          borderColor: cssVar('--surface', '#fff'),
          borderWidth: 2,
        },
      ],
    },
    options: {
      cutout: '62%',
      responsive: true,
      maintainAspectRatio: false,
      animation: prefersReducedMotion() ? false : { duration: 700 },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => `${c.label}: ${c.formattedValue}` } },
      },
    },
  });
}

export async function renderTrend(canvas, monthly) {
  const accent = cssVar('--accent', '#5b6cff');
  const Chart = await getChart();
  return new Chart(canvas, {
    type: 'line',
    data: {
      labels: monthly.map((m) => m.month.slice(2)),
      datasets: [
        {
          data: monthly.map((m) => m.count),
          borderColor: accent,
          backgroundColor: cssVar('--accent-soft', 'rgba(91,108,255,0.15)'),
          fill: true,
          tension: 0.35,
          pointRadius: 0,
          pointHoverRadius: 4,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: prefersReducedMotion() ? false : { duration: 700 },
      plugins: { legend: { display: false }, tooltip: { intersect: false, mode: 'index' } },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: cssVar('--text-muted', '#888'), maxTicksLimit: 8 },
        },
        y: {
          beginAtZero: true,
          grid: { color: cssVar('--border', '#eee') },
          ticks: { color: cssVar('--text-muted', '#888'), precision: 0 },
        },
      },
    },
  });
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
