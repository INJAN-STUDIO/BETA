// Runs before the page paints, so the saved theme shows from the first frame (no flash of the wrong colours).
(function () {
  var bars = { 'icon-dark': '#051a22', 'icon-light': '#e8f5f8', dark: '#05060a', light: '#f2f6fb' };
  try {
    var t = localStorage.getItem('beta_theme');
    if (bars[t]) {
      document.documentElement.setAttribute('data-theme', t);
      var m = document.querySelector('meta[name="theme-color"]');
      if (m) m.setAttribute('content', bars[t]);
    }
  } catch (e) { /* storage blocked: the default (logo colours, dark) stays */ }
})();
