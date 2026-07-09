// Sakshi — internationalisation loader (Phase-4 scaffold STUB).
//
// Ships English and Hindi. The active locale is chosen from the URL (?lang=),
// then localStorage, then the browser language, defaulting to English.
// Strings are applied to any element carrying a [data-i18n] key.

/** @type {Record<string, Record<string, string>>} */
const cache = {};

const SUPPORTED = ['en', 'hi'];
const DEFAULT_LOCALE = 'en';

function detectLocale() {
  const fromUrl = new URLSearchParams(window.location.search).get('lang');
  const fromStore = window.localStorage?.getItem('sakshi.lang');
  const fromNav = navigator.language?.slice(0, 2);
  const candidate = fromUrl || fromStore || fromNav || DEFAULT_LOCALE;
  return SUPPORTED.includes(candidate) ? candidate : DEFAULT_LOCALE;
}

/**
 * @param {string} locale
 * @returns {Promise<Record<string, string>>}
 */
async function loadMessages(locale) {
  if (cache[locale]) return cache[locale];
  const mod = await import(`./${locale}.json`);
  cache[locale] = mod.default ?? mod;
  return cache[locale];
}

/**
 * Apply loaded messages to [data-i18n] elements.
 * @param {Record<string, string>} messages
 */
function apply(messages) {
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    if (key && messages[key]) el.textContent = messages[key];
  });
}

/**
 * Initialise i18n for the current document.
 * @returns {Promise<string>} the active locale
 */
export async function initI18n() {
  const locale = detectLocale();
  document.documentElement.lang = locale;
  try {
    apply(await loadMessages(locale));
  } catch (err) {
    console.warn('[sakshi] i18n load failed, keeping HTML defaults:', err);
  }
  return locale;
}
