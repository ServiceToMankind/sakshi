// Sakshi — frontend entry point (Phase-4 scaffold STUB).
//
// Responsibilities once fully implemented:
//   1. Load data/summary.json (the only payload the landing page needs).
//   2. Wire the router (state -> district drill-down, shareable filter URLs).
//   3. Render charts (count-up totals, status donut, SVG state tile-grid, trend).
//   4. Initialise animations (IntersectionObserver reveals, View Transitions),
//      always respecting prefers-reduced-motion.
//   5. Initialise i18n (en/hi) and the theme toggle.
//
// This stub only loads summary data and logs a plan. No real UI yet.

import { initRouter } from './router.js';
import { initFilters } from './filters.js';
import { initReveals } from './animations.js';
import { initI18n } from './i18n/index.js';
// Chart helpers are imported lazily where rendered; referenced here for the plan.
// import { countUp, renderStatusDonut, renderTrend, renderStateGrid } from './charts.js';

// Base is injected by Vite (see vite.config.js `base`). Data lives at repo-root
// /data, which is served as a sibling of the built site on GitHub Pages.
const SUMMARY_URL = `${import.meta.env.BASE_URL}data/summary.json`;

async function loadSummary() {
  try {
    const res = await fetch(SUMMARY_URL, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`summary.json -> HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    // TODO: fall back to service-worker-cached summary for offline glance.
    console.warn('[sakshi] could not load summary.json:', err);
    return null;
  }
}

function initThemeToggle() {
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const root = document.documentElement;
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    // TODO: persist preference to localStorage.
  });
}

function updateLastUpdated(summary) {
  const el = document.getElementById('last-updated');
  if (!el || !summary?.generated_at) return;
  el.dateTime = summary.generated_at;
  el.textContent = new Date(summary.generated_at).toLocaleDateString();
}

async function main() {
  console.info('[sakshi] booting frontend scaffold');

  initThemeToggle();
  await initI18n();
  initReveals();
  initFilters();
  initRouter();

  const summary = await loadSummary();
  if (summary) {
    updateLastUpdated(summary);
    console.info('[sakshi] summary loaded:', {
      total: summary.total_cases,
      states: summary.state_counts && Object.keys(summary.state_counts).length,
    });
    // TODO: render totals count-up, status donut, state tile-grid, trend line.
  }
}

main();
