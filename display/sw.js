let BUILD_VERSION = 'dev';
try {
  BUILD_VERSION = new URL(self.location.href).searchParams.get('v') || 'dev';
} catch (e) {}

const ASSET_SUFFIX = BUILD_VERSION ? '?v=' + encodeURIComponent(BUILD_VERSION) : '';
const CACHE_NAME = 'reserve-board-' + BUILD_VERSION;
const STATIC_URLS = ['./', './index.html', './styles.css' + ASSET_SUFFIX, './app.js' + ASSET_SUFFIX, './manifest.json' + ASSET_SUFFIX];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_URLS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.url.startsWith(self.location.origin) && event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request).then((cached) => cached || caches.match('./index.html')))
    );
  }
});
