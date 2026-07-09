// Frontend entry point: styles, i18n, theme + language toggles, the router, the
// footer's last-updated stamp, and the service worker. The router owns rendering.

import '../styles/main.css';

import { initI18n, setLocale, currentLocale, supportedLocales } from './i18n/index.js';
import { initRouter } from './router.js';
import { loadSummary } from './data.js';
import { formatDate } from './format.js';

function safeGet(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function safeSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* non-fatal */
  }
}

function initTheme() {
  const stored = safeGet('sakshi.theme');
  if (stored === 'dark' || stored === 'light') document.documentElement.dataset.theme = stored;
  const btn = document.getElementById('theme-toggle');
  btn?.addEventListener('click', () => {
    const root = document.documentElement;
    const isDark =
      root.dataset.theme === 'dark' ||
      (!root.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
    const next = isDark ? 'light' : 'dark';
    root.dataset.theme = next;
    safeSet('sakshi.theme', next);
    window.dispatchEvent(new CustomEvent('sakshi:theme', { detail: next }));
  });
}

function updateLangLabel() {
  const btn = document.getElementById('lang-toggle');
  if (btn) btn.textContent = currentLocale() === 'en' ? 'हिंदी' : 'EN';
}

function initLangToggle() {
  const btn = document.getElementById('lang-toggle');
  btn?.addEventListener('click', async () => {
    const locales = supportedLocales();
    const next = locales[(locales.indexOf(currentLocale()) + 1) % locales.length];
    await setLocale(next);
    updateLangLabel();
  });
  updateLangLabel();
}

async function initFooter() {
  const node = document.getElementById('last-updated');
  if (!node) return;
  try {
    const summary = await loadSummary();
    if (summary?.generated_at) {
      node.dateTime = summary.generated_at;
      node.textContent = formatDate(summary.generated_at);
    }
  } catch {
    /* leave the placeholder dash */
  }
}

function registerServiceWorker() {
  if (!('serviceWorker' in navigator) || !import.meta.env.PROD) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(() => {});
  });
}

async function main() {
  initTheme();
  await initI18n();
  initLangToggle();
  initRouter();
  initFooter();
  registerServiceWorker();
}

main();
