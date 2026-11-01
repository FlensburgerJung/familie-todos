/* Service Worker: hält die App-Hülle offline und sofort verfügbar.
   API-Antworten werden bewusst nicht gecacht - veraltete Todos wären
   schlimmer als eine ehrliche Fehlermeldung. */

const CACHE = 'familie-todos-v38';
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

  /* Cache zuerst, Aktualisierung im Hintergrund.

     Vorher stand hier "Netz zuerst". Das klang richtig - Änderungen kommen
     sofort an -, hieß in der Praxis aber: Schläft der Dienst beim Hoster,
     wartet die App bis zu einer Minute auf Hülle, CSS und JavaScript, obwohl
     all das längst im Cache liegt. Man starrt auf eine weiße Seite, um am
     Ende genau das zu sehen, was schon da war.

     Jetzt wird sofort aus dem Cache geliefert und parallel nachgeladen. Die
     App öffnet sich unabhängig davon, ob der Server wach ist. Preis dafür:
     Eine neue Fassung erscheint erst beim übernächsten Start. */
  event.respondWith(
    caches.match(request).then(treffer => {
      const ausDemNetz = fetch(request)
        .then(response => {
          if (response && response.ok) {
            const kopie = response.clone();
            caches.open(CACHE).then(cache => cache.put(request, kopie)).catch(() => {});
          }
          return response;
        })
        // Ohne Netz und ohne Treffer bleibt die Hülle. Liegt auch die nicht
        // im Cache, muss hier trotzdem eine Antwort herauskommen: Gibt der
        // Service Worker `undefined` zurück, scheitert die Anfrage mit einem
        // TypeError und die Seite bleibt weiß - ohne jeden Hinweis, warum.
        .catch(async () => (treffer
          || await caches.match('/index.html')
          || new Response(
              '<!doctype html><meta charset="utf-8">'
              + '<p style="font:16px system-ui;padding:24px">Keine Verbindung — '
              + 'und nichts gespeichert. Sobald der Server wieder da ist, '
              + '<a href="/">hier weiter</a>.',
              { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } })));

      // Liegt etwas im Cache, zählt nur das - der Rest läuft nebenher.
      return treffer || ausDemNetz;
    })
  );
});
