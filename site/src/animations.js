// Sakshi — motion helpers (Phase-4 scaffold STUB).
//
// Restrained, memorial-grade motion: staggered reveals as sections enter the
// viewport, and View Transitions between routes. Everything is gated behind
// prefers-reduced-motion — when the user asks for reduced motion, content
// appears immediately with no tween.

const prefersReducedMotion = () =>
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

/**
 * Reveal elements marked with [data-reveal] as they scroll into view.
 */
export function initReveals() {
  const targets = document.querySelectorAll('[data-reveal]');
  if (prefersReducedMotion() || !('IntersectionObserver' in window)) {
    targets.forEach((el) => el.classList.add('is-revealed'));
    return;
  }
  const io = new IntersectionObserver(
    (entries, obs) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-revealed');
        obs.unobserve(entry.target);
      });
    },
    { rootMargin: '0px 0px -10% 0px', threshold: 0.1 },
  );
  targets.forEach((el) => io.observe(el));
}

/**
 * Run a route/view swap inside a View Transition when supported.
 * @param {() => void | Promise<void>} update  DOM mutation to animate
 */
export function withViewTransition(update) {
  if (prefersReducedMotion() || !document.startViewTransition) {
    return Promise.resolve(update());
  }
  return document.startViewTransition(update).finished;
}
