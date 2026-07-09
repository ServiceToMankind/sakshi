// Service worker: an offline glance.
//   - summary.json     -> stale-while-revalidate (instant last-known, refreshed).
//   - navigations      -> network-first, falling back to the cached app shell.
//   - everything else  -> network-first with a cache fallback.
// Path checks use endsWith so the same code works at a subpath (/sakshi/) or a
// custom-domain root.

const CACHE = 'sakshi-v2';

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

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then((res) => {
      if (res.ok) cache.put(request, res.clone());
      return res;
    })
    .catch(() => cached);
  return cached || network;
}

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
  if (url.pathname.endsWith('/data/summary.json')) {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }
  event.respondWith(networkFirst(request));
});
