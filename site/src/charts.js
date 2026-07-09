// Sakshi — chart helpers (Phase-4 scaffold STUB).
//
// Uses chart.js for the donut and trend line; the India state map is a
// hand-built SVG tile-grid (one square per state/UT) rather than a heavy geo
// library. All helpers must honour prefers-reduced-motion (skip animated
// tweens when the user asks for reduced motion).

/**
 * Animate a number from 0 to `target` inside `el`.
 * @param {HTMLElement} el
 * @param {number} target
 * @param {{ durationMs?: number }} [opts]
 */
export function countUp(el, target, opts = {}) {
  // TODO: requestAnimationFrame tween; jump straight to target under reduced motion.
  void opts;
  el.textContent = String(target);
}

/**
 * Render the status distribution donut.
 * @param {HTMLElement} mount
 * @param {Record<string, number>} statusCounts  keyed by the status enum
 * @returns {unknown} chart handle (for teardown)
 */
export function renderStatusDonut(mount, statusCounts) {
  // TODO: new Chart(mount, { type: 'doughnut', ... }) with theme-aware colors.
  void mount;
  void statusCounts;
  return null;
}

/**
 * Render the 24-month trend line.
 * @param {HTMLElement} mount
 * @param {Array<{ month: string, count: number }>} monthly
 * @returns {unknown} chart handle
 */
export function renderTrend(mount, monthly) {
  // TODO: new Chart(mount, { type: 'line', ... }).
  void mount;
  void monthly;
  return null;
}

/**
 * Render the SVG state tile-grid (one tile per state/UT, shaded by count).
 * @param {HTMLElement} mount
 * @param {Record<string, number>} stateCounts  keyed by 2-letter state code
 */
export function renderStateGrid(mount, stateCounts) {
  // TODO: build an <svg> tile-grid; each tile links to #/explore?state=XX.
  void mount;
  void stateCounts;
}
