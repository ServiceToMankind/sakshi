// Hash-based router so the site is a pure static deployment (no server rewrites).
// The filter state lives in the query portion of the hash, so every view — down
// to a specific filter combination — is a shareable, bookmarkable, back/forward-
// safe link.
//
//   #/                                landing (overview)
//   #/explore?state=TG&status=UNDER_TRIAL&sort=pending
//   #/case/SKS-2026-TG-000123         case detail

import { mount, el } from './dom.js';
import { applyI18n, t } from './i18n/index.js';
import { revealOnScroll, prefersReducedMotion } from './animations.js';
import { renderLanding } from './views/landing.js';
import { renderExplore } from './views/explore.js';
import { renderCase } from './views/caseDetail.js';

const OUTLET_ID = 'app';
const VIEWS = { landing: renderLanding, explore: renderExplore, case: renderCase };

export function parseRoute() {
  const raw = window.location.hash.replace(/^#/, '') || '/';
  const [path, query = ''] = raw.split('?');
  const params = new URLSearchParams(query);
  if (path.startsWith('/explore')) return { name: 'explore', path, params };
  if (path.startsWith('/case/')) {
    return { name: 'case', path, params, id: decodeURIComponent(path.slice('/case/'.length)) };
  }
  return { name: 'landing', path: '/', params };
}

/** Programmatic navigation; a no-op if we're already there. */
export function navigate(hash) {
  if (window.location.hash === `#${hash}`) return;
  window.location.hash = hash;
}

function loadingNode() {
  return el('div', { class: 'view view--loading', 'aria-busy': 'true' }, [
    el('span', { class: 'skeleton skeleton--stat' }),
    el('span', { class: 'skeleton skeleton--chart' }),
    el('span', { class: 'visually-hidden', 'data-i18n': 'loading' }, t('loading')),
  ]);
}

function errorNode() {
  return el('div', { class: 'view view--error', role: 'alert' }, [
    el('p', { 'data-i18n': 'error_generic' }, t('error_generic')),
    el('button', { class: 'btn', onclick: () => render() }, t('retry')),
  ]);
}

function markActiveNav(routeName) {
  document.querySelectorAll('[data-nav]').forEach((link) => {
    if (link.dataset.nav === routeName) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}

async function render() {
  const outlet = document.getElementById(OUTLET_ID);
  if (!outlet) return;
  const route = parseRoute();
  markActiveNav(route.name);

  mount(outlet, loadingNode());

  let node;
  try {
    node = await (VIEWS[route.name] || renderLanding)(route);
  } catch (err) {
    console.error('[sakshi] view error:', err);
    node = errorNode();
  }

  const swap = () => {
    mount(outlet, node);
    applyI18n(outlet);
    revealOnScroll(outlet);
    window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  };

  if (document.startViewTransition && !prefersReducedMotion()) {
    document.startViewTransition(swap);
  } else {
    swap();
  }
}

export function initRouter() {
  window.addEventListener('hashchange', render);
  // Re-render the current view when language or theme changes so freshly built
  // nodes (and theme-colored charts) pick up the new locale/palette.
  window.addEventListener('sakshi:locale', render);
  window.addEventListener('sakshi:theme', render);
  render();
}
