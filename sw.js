/* Above & Beyond Operations - service worker
   v2 - 14 September 2026

   IMPORTANT: this worker deliberately does NOT intercept page navigations.
   The board sits behind Cloudflare Access. When an Access session expires,
   a navigation returns a redirect to the login screen. A service worker
   cannot read or safely re-serve that redirect, and the page comes back
   blank instead of showing the sign-in screen. Letting the browser handle
   navigations itself fixes that, at the cost of an offline page on
   navigation - which is no real loss on a board whose whole value is live
   data. Static files are still cached so the shell loads fast.
*/

var VERSION = 'v2';
var SHELL   = 'ab-shell-' + VERSION;
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

self.addEventListener('message', function (e) {
  if (e.data === 'skip-waiting') self.skipWaiting();
});

function usable(res) {
  if (!res || !res.ok) return false;
  if (res.type === 'opaqueredirect' || res.redirected) return false;
  try { if (new URL(res.url).origin !== self.location.origin) return false; } catch (e) { return false; }
  return true;
}

self.addEventListener('fetch', function (event) {
  var req = event.request;

  // Navigations are handled by the browser. Do not touch them.
  if (req.mode === 'navigate') return;
  if (req.method !== 'GET') return;

  var url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.origin !== self.location.origin) return;

  if (!/\.(png|jpg|jpeg|gif|svg|ico|css|js|webmanifest|woff2?)$/i.test(url.pathname)) return;

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
});
