// B.E.T.A. service worker. Its one job: make the app shell appear INSTANTLY from the
// phone's cache, even while Render's free server is still waking up (up to ~1 minute),
// so you see a friendly "waking up" screen instead of a blank page. API calls are
// never cached - chat data always comes live from the server.
var CACHE = 'beta-shell-v2';
var SHELL = ['/', '/static/style.css', '/static/app.js', '/static/logo.jpg', '/static/icon-192.png', '/manifest.webmanifest'];

self.addEventListener('install', function (e) {
  // Cache each file on its own: with addAll(), ONE missing file makes the whole install fail,
  // and a service worker that never installs is a common reason a browser won't offer "Install".
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); }));
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
  if (req.method !== 'GET' || url.origin !== location.origin || url.pathname.indexOf('/api/') === 0) return;
  // Stale-while-revalidate: answer from cache now, refresh the cache in the background.
  e.respondWith(caches.open(CACHE).then(function (cache) {
    return cache.match(req).then(function (hit) {
      var fresh = fetch(req).then(function (res) {
        if (res && res.ok) cache.put(req, res.clone());
        return res;
      }).catch(function () { return hit; });
      return hit || fresh;
    });
  }));
});
