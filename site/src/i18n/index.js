// i18n: English is the complete base. Other locales are PARTIAL overrides that
// fall back to English key-by-key. In dev, any element rendered from a fallback
// (i.e. an untranslated key) is flagged via [data-i18n-missing] so gaps are
// visible while developing — never in production.

import en from './en.json';
import hi from './hi.json';

const LOCALES = { en, hi };
const SUPPORTED = ['en', 'hi'];
const DEV = import.meta.env.DEV;

let base = {}; // full English
let overrides = {}; // partial active-locale strings
let locale = 'en';

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
    /* storage may be unavailable; non-fatal */
  }
}

function detectLocale() {
  const fromUrl = new URLSearchParams(window.location.search).get('lang');
  const candidate = fromUrl || safeGet('sakshi.lang') || navigator.language?.slice(0, 2) || 'en';
  return SUPPORTED.includes(candidate) ? candidate : 'en';
}

function messagesFor(loc) {
  return LOCALES[loc] || {};
}

export function t(key) {
  if (locale !== 'en' && key in overrides) return overrides[key];
  return base[key] ?? key;
}

export function isUntranslated(key) {
  return locale !== 'en' && !(key in overrides);
}

export function currentLocale() {
  return locale;
}

export function supportedLocales() {
  return [...SUPPORTED];
}

/** Apply all [data-i18n] keys under `root`, flagging untranslated ones in dev. */
export function applyI18n(root = document) {
  root.querySelectorAll('[data-i18n]').forEach((node) => {
    const key = node.getAttribute('data-i18n');
    if (!key) return;
    node.textContent = t(key);
    if (DEV && isUntranslated(key)) node.setAttribute('data-i18n-missing', '');
    else node.removeAttribute('data-i18n-missing');
  });
}

export function initI18n() {
  locale = detectLocale();
  base = LOCALES.en;
  overrides = locale === 'en' ? {} : messagesFor(locale);
  document.documentElement.lang = locale;
  applyI18n();
  return locale;
}

export function setLocale(next) {
  if (!SUPPORTED.includes(next) || next === locale) return;
  safeSet('sakshi.lang', next);
  locale = next;
  overrides = next === 'en' ? {} : messagesFor(next);
  document.documentElement.lang = next;
  applyI18n();
  window.dispatchEvent(new CustomEvent('sakshi:locale', { detail: next }));
}
