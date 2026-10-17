// B.E.T.A. service worker. It exists so the app OPENS INSTANTLY even while Render's free server is still waking
// up (up to ~a minute) - and, since v7, so that a new release shows up on the very next open.
//   - Pages: network first. If the server answers within 3 seconds you always get the newest page; if it is
//     asleep or offline you get the saved copy instead of a blank screen.
//   - Scripts/styles carry the release number in their address (?v=...), so a new release can never be
//     mixed up with an old saved copy.
//   - API calls are never touched: chat data is always live.
var V = new URL(self.location.href).searchParams.get('v') || '0';
var CACHE = 'beta-shell-' + V;
var SHELL = ['/', '/static/style.css?v=' + V, '/static/themes.css?v=' + V, '/static/theme-init.js?v=' + V, '/static/app.js?v=' + V,
             '/static/logo.jpg', '/static/icon-192.png', '/manifest.webmanifest'];

self.addEventListener('install', function (e) {
  // Cache each file on its own: with addAll(), ONE missing file makes the whole install fail.
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return Promise.all(SHELL.map(function (u) { return c.add(new Request(u, { cache: 'reload' })).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  var url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.indexOf('/api/') === 0 || url.pathname === '/reset' || url.pathname === '/static/reset.js' || url.pathname === '/sw.js') return;

  if (req.mode === 'navigate') {                       // the page itself: network first, saved copy as the fallback
    e.respondWith(new Promise(function (resolve) {
      var settled = false;
      var fallback = function () {
        caches.match('/').then(function (hit) { if (!settled && hit) { settled = true; resolve(hit); } });
      };
      var timer = setTimeout(fallback, 3000);
      fetch(req).then(function (res) {
        clearTimeout(timer);
        if (res && res.ok) { var copy = res.clone(); caches.open(CACHE).then(function (c) { c.put('/', copy); }); }
        if (!settled) { settled = true; resolve(res); }
      }).catch(function () {
        clearTimeout(timer);
        caches.match('/').then(function (hit) { if (!settled) { settled = true; resolve(hit || Response.error()); } });
      });
    }));
    return;
  }

  // everything else on this site: saved copy first (instant), refreshed in the background
  e.respondWith(caches.open(CACHE).then(function (cache) {
    return cache.match(req).then(function (hit) {
      var fresh = fetch(req, { cache: 'no-cache' }).then(function (res) {
        if (res && res.ok) cache.put(req, res.clone());
        return res;
      }).catch(function () { return hit; });
      return hit || fresh;
    });
  }));
});

// ---- notifications ("your reply is ready") ----
// The server sends a small push message when a reply finishes while you are away; this shows it. Tapping it
// brings B.E.T.A. back to the front (or opens it).
self.addEventListener('push', function (e) {
  var data = {};
  try { data = e.data ? e.data.json() : {}; } catch (err) { /* plain text or empty - use the defaults */ }
  e.waitUntil(self.registration.showNotification(data.title || 'B.E.T.A.', {
    body: data.body || 'Your reply is ready.',
    icon: '/static/icon-192.png',
    tag: 'beta-reply'                                  // a newer notification replaces an older one instead of piling up
  }));
});

self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) { if ('focus' in list[i]) return list[i].focus(); }
    return self.clients.openWindow('/');
  }));
});
