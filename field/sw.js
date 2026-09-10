/* A&B Field - service worker for the tech page.
   Lives under /field/ because that path is the one Cloudflare Access lets through
   without a login. Scope is /field so it never fights the office board worker at /. */

var VERSION = 'fv1';
var SHELL = 'abf-shell-' + VERSION;
var PAGES = 'abf-pages-' + VERSION;
var PRECACHE = [
  '/field/offline.html',
  '/field/manifest.webmanifest',
  '/field/icon-192.png',
  '/field/icon-512.png',
  '/field/icon-maskable-512.png',
  '/field/apple-touch-icon.png'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(SHELL).then(function (c) {
      return Promise.all(PRECACHE.map(function (u) {
        return c.add(new Request(u, { cache: 'reload' })).catch(function () {});
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) {
        return k.indexOf('abf-') === 0 && k.indexOf(VERSION) === -1;
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

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;
  var url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.origin !== self.location.origin) return;

  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then(function (net) {
        if (usable(net)) { var copy = net.clone(); caches.open(PAGES).then(function (c) { c.put(req, copy); }); }
        return net;
      }).catch(function () {
        return caches.match(req, { ignoreSearch: true }).then(function (hit) {
          if (hit) return hit;
          return caches.match('/field/offline.html').then(function (off) {
            return off || new Response('Offline', { status: 503, headers: { 'content-type': 'text/plain' } });
          });
        });
      })
    );
    return;
  }

  if (/^\/field\/.*\.(png|jpg|jpeg|gif|svg|ico|css|webmanifest|woff2?)$/i.test(url.pathname)) {
    event.respondWith(
      caches.match(req).then(function (hit) {
        if (hit) return hit;
        return fetch(req).then(function (net) {
          if (usable(net)) { var copy = net.clone(); caches.open(SHELL).then(function (c) { c.put(req, copy); }); }
          return net;
        }).catch(function () { return new Response('', { status: 504 }); });
      })
    );
  }
});
