/* Service Worker: hält die App-Hülle offline verfügbar.
   API-Antworten werden bewusst nicht gecacht - veraltete Todos wären
   schlimmer als eine ehrliche Fehlermeldung. */

const CACHE = 'familie-todos-v27';
const SHELL = ['/', '/index.html', '/style.css', '/app.js', '/icon.svg',
               '/icon-192.png', '/icon-512.png', '/manifest.webmanifest'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname.endsWith('.ics')) return;

  // Netz zuerst, damit Änderungen an der App sofort ankommen; Cache als Netz.
  event.respondWith(
    fetch(request)
      .then(response => {
        const copy = response.clone();
        caches.open(CACHE).then(cache => cache.put(request, copy)).catch(() => {});
        return response;
      })
      .catch(() => caches.match(request).then(hit => hit || caches.match('/index.html')))
  );
});
