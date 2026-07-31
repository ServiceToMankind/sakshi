// Read-aloud via the Web Speech API (§7) — a pure client feature, no data leaves the page.
// Speaks a case's title + summary in the current locale. Degrades gracefully: if the browser
// has no speechSynthesis, the button is simply never created. Toggles play/stop.

import { el } from './dom.js';
import { t, currentLocale } from './i18n/index.js';

const LOCALE_TO_BCP47 = { en: 'en-IN', hi: 'hi-IN', te: 'te-IN' };

function synth() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
    ? window.speechSynthesis
    : null;
}

/** A read-aloud toggle button for `text`, or null when speech synthesis is unavailable. */
export function readAloudButton(text) {
  const engine = synth();
  const speech = String(text || '').trim();
  if (!engine || !speech) return null;

  const label = el('span', { 'data-i18n': 'read_aloud' }, t('read_aloud'));
  const btn = el('button', { class: 'btn btn--ghost read-aloud', type: 'button' }, [
    el('span', { class: 'read-aloud__icon', 'aria-hidden': 'true' }, '🔊'),
    label,
  ]);

  const reset = () => {
    label.textContent = t('read_aloud');
    label.setAttribute('data-i18n', 'read_aloud');
    btn.removeAttribute('aria-pressed');
  };

  btn.addEventListener('click', () => {
    if (engine.speaking) {
      engine.cancel();
      reset();
      return;
    }
    const utter = new window.SpeechSynthesisUtterance(speech);
    utter.lang = LOCALE_TO_BCP47[currentLocale()] || 'en-IN';
    utter.onend = reset;
    utter.onerror = reset;
    label.textContent = t('read_stop');
    label.setAttribute('data-i18n', 'read_stop');
    btn.setAttribute('aria-pressed', 'true');
    engine.cancel(); // clear any queued utterance first
    engine.speak(utter);
  });

  return btn;
}

/** Stop any in-progress narration — call on route change so speech never bleeds across views. */
export function stopReadAloud() {
  const engine = synth();
  if (engine && (engine.speaking || engine.pending)) engine.cancel();
}
