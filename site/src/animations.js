// Motion helpers. All motion is gated on prefers-reduced-motion: when the user
// asks for reduced motion, revealed content is shown immediately with no
// transition, and callers skip smooth scrolling / view transitions.

export function prefersReducedMotion() {
  return Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

let observer = null;

function ensureObserver() {
  if (observer || typeof IntersectionObserver === 'undefined') return observer;
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      }
    },
    { rootMargin: '0px 0px -8% 0px', threshold: 0.05 },
  );
  return observer;
}

/** Reveal `.reveal` elements under `root` on scroll (or immediately if reduced). */
export function revealOnScroll(root = document) {
  const targets = root.querySelectorAll('.reveal:not(.is-visible)');
  const obs = ensureObserver();
  if (prefersReducedMotion() || !obs) {
    targets.forEach((node) => node.classList.add('is-visible'));
    return;
  }
  targets.forEach((node) => obs.observe(node));
}
