// Clears everything the phone saved for B.E.T.A.'s offline mode, then opens the app fresh.
(function () {
  var done = function () { location.replace('/'); };
  var work = [];
  if (navigator.serviceWorker && navigator.serviceWorker.getRegistrations) {
    work.push(navigator.serviceWorker.getRegistrations().then(function (rs) { return Promise.all(rs.map(function (r) { return r.unregister(); })); }));
  }
  if (window.caches && caches.keys) {
    work.push(caches.keys().then(function (ks) { return Promise.all(ks.map(function (k) { return caches.delete(k); })); }));
  }
  Promise.all(work).then(done, done);
  setTimeout(done, 4000);   // never get stuck here
})();
