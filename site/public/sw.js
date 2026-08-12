// Service worker: an offline glance, but NEVER a stale record count.
//   - navigations    -> network-first, falling back to the cached app shell.
//   - everything else (data/*.json, assets) -> network-first with a cache fallback.
// summary.json used to be stale-while-revalidate ("instant last-known"), which meant the
// map tiles, state tables, scorecards and the "last updated" footer showed the PREVIOUS
// day's counts for a whole extra load after every data update — while the recent feed
// (network-first) was already fresh. For an accountability record, a stale count is a wrong
// count, so ALL data is network-first now; the cache is only a fallback when offline.
// Path checks use endsWith so the same code works at a subpath (/sakshi/) or a
// custom-domain root.

const CACHE = 'sakshi-v3';

self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

async function networkFirst(request, shellFallback = false) {
  const cache = await caches.open(CACHE);
  try {
    const res = await fetch(request);
    if (res.ok) cache.put(request, res.clone());
    return res;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (shellFallback) {
      const shell = await cache.match('index.html');
      if (shell) return shell;
    }
    throw err;
  }
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, true));
    return;
  }
  event.respondWith(networkFirst(request));
});
