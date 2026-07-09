// Sakshi — client-side router (Phase-4 scaffold STUB).
//
// Routes are hash-based so the site works as a static GitHub Pages deployment
// without server rewrites. The filter state (status, year, district,
// minor_involved, sort, free-text) is URL-encoded into the query portion of the
// hash so any view is a shareable, bookmarkable link.
//
//   #/                         landing (summary only)
//   #/explore?state=TG         state drill-down
//   #/explore?state=TG&district=Hyderabad&status=UNDER_TRIAL&sort=pending
//   #/case/SKS-2026-TG-000123  case detail
//
// TODO: implement view mounting, transition hooks (View Transitions API),
// and integration with filters.js for the query segment.

/** @typedef {'landing' | 'explore' | 'case'} RouteName */

/**
 * Parse the current location hash into a route descriptor.
 * @returns {{ name: RouteName, params: URLSearchParams, path: string }}
 */
export function parseRoute() {
  const raw = window.location.hash.replace(/^#/, '') || '/';
  const [path, query = ''] = raw.split('?');
  let name = /** @type {RouteName} */ ('landing');
  if (path.startsWith('/explore')) name = 'explore';
  else if (path.startsWith('/case/')) name = 'case';
  return { name, params: new URLSearchParams(query), path };
}

/**
 * Register the router. Calls the (future) view dispatcher on hashchange.
 */
export function initRouter() {
  const handle = () => {
    const route = parseRoute();
    console.info('[sakshi] route ->', route.name, route.path);
    // TODO: dispatch to the matching view renderer.
  };
  window.addEventListener('hashchange', handle);
  handle();
}
