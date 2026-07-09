// Sakshi — service worker (Phase-4 scaffold STUB).
//
// Strategy:
//   - data/summary.json  -> cache-first, so the landing page shows a last-known
//     glance while offline (then refreshed in the background on next load).
//   - everything else     -> network-first, falling back to cache when offline.
//
// TODO: precache the app shell (index.html + built JS/CSS) on install, add a
// stale-while-revalidate refresh for summary.json, and version-bump CACHE on
// each release so stale assets are evicted.

const CACHE = 'sakshi-v1';
const SUMMARY_PATH = '/data/summary.json';

self.addEventListener('install', (event) => {
  // TODO: precache app shell here.
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  if (url.pathname.endsWith(SUMMARY_PATH)) {
    // Cache-first for the offline glance.
    event.respondWith(
      caches.open(CACHE).then(async (cache) => {
        const cached = await cache.match(request);
        if (cached) return cached;
        const res = await fetch(request);
        cache.put(request, res.clone());
        return res;
      }),
    );
    return;
  }

  // Network-first for everything else.
  event.respondWith(
    fetch(request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
        return res;
      })
      .catch(() => caches.match(request)),
  );
});
