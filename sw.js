/* Above & Beyond Operations - service worker
   Strategy:
     navigation  -> network first, fall back to the last good copy, then /offline.html
     static file -> cache first
   Never caches a Cloudflare Access login redirect as if it were the board. */

var VERSION = 'v1';
var SHELL   = 'ab-shell-' + VERSION;
var PAGES   = 'ab-pages-' + VERSION;
var PRECACHE = [
  '/offline.html',
  '/manifest.webmanifest',
  '/icon-192.png',
  '/icon-512.png',
  '/icon-maskable-512.png',
  '/apple-touch-icon.png',
  '/favicon-32.png'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(SHELL).then(function (c) {
      return Promise.all(PRECACHE.map(function (u) {
        return c.add(new Request(u, { cache: 'reload' })).catch(function () { /* keep going */ });
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) {
        return k.indexOf('ab-') === 0 && k.indexOf(VERSION) === -1;
      }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

function usable(res) {
  if (!res || !res.ok) return false;
  if (res.type === 'opaqueredirect' || res.redirected) return false;
  try { if (new URL(res.url).origin !== self.location.origin) return false; } catch (e) { return false; }
  return true;
}

self.addEventListener('message', function (e) {
  if (e.data === 'skip-waiting') self.skipWaiting();
});

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;

  var url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.origin !== self.location.origin) return;

  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then(function (net) {
        if (usable(net)) {
          var copy = net.clone();
          caches.open(PAGES).then(function (c) { c.put(req, copy); });
        }
        return net;
      }).catch(function () {
        return caches.match(req, { ignoreSearch: true }).then(function (hit) {
          if (hit) return hit;
          return caches.match('/offline.html').then(function (off) {
            return off || new Response('Offline', { status: 503, headers: { 'content-type': 'text/plain' } });
          });
        });
      })
    );
    return;
  }

  if (/\.(png|jpg|jpeg|gif|svg|ico|css|js|webmanifest|woff2?)$/i.test(url.pathname)) {
    event.respondWith(
      caches.match(req).then(function (hit) {
        if (hit) return hit;
        return fetch(req).then(function (net) {
          if (usable(net)) {
            var copy = net.clone();
            caches.open(SHELL).then(function (c) { c.put(req, copy); });
          }
          return net;
        }).catch(function () {
          return new Response('', { status: 504 });
        });
      })
    );
  }
});
