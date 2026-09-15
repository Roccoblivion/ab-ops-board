/*
 * A&B Ops Board — root service worker, retired 2026-09-15.
 *
 * The office board is live data and is served straight from the network.
 * Earlier builds cached the shell for offline use, but behind Cloudflare
 * Access that caching trapped devices on a blank screen when a sign-in
 * lapsed. This build removes the worker instead: on activation it clears
 * the office caches, unregisters itself, and reloads any open windows so
 * they run with no service worker at all. It never caches or intercepts
 * anything. The field app keeps its own worker at /field/sw.js.
 */
self.addEventListener('install', function (e) {
  self.skipWaiting();
});

self.addEventListener('activate', function (e) {
  e.waitUntil((async function () {
    try {
      const keys = await caches.keys();
      // Office caches only ("ab-..."). Field caches ("abf-...") are left alone.
      await Promise.all(
        keys.filter(function (k) { return k.indexOf('ab-') === 0; })
            .map(function (k) { return caches.delete(k); })
      );
    } catch (err) {}
    try { await self.registration.unregister(); } catch (err) {}
    try {
      const cs = await self.clients.matchAll({ type: 'window' });
      cs.forEach(function (c) { try { c.navigate(c.url); } catch (e2) {} });
    } catch (err) {}
  })());
});

/* No fetch handler: every request goes to the network. */
