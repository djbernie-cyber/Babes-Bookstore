/* Babe's Bookstore — Service Worker
 * Network-first for everything: API calls, HTML pages, and static assets.
 * Only caches as an offline fallback — never serves stale data when online.
 * Bump CACHE_NAME to force a fresh install on deploys.
 */
const CACHE_NAME = 'babes-v3';
const PRECACHE = [
  '/',
  '/static/site.css',
  '/static/icon.svg',
  '/js/store.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Only cache GET requests
  if (request.method !== 'GET') return;

  // Network-first for everything: API, HTML, and assets.
  // Stale data is worse than no data for a live catalogue.
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match('/')))
  );
});
