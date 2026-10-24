// Runs before the page paints, so the saved theme shows from the first frame (no flash of the wrong colours).
(function () {
  var bars = { 'icon-dark': '#051a22', 'icon-light': '#e8f5f8', dark: '#05060a', light: '#f2f6fb', midnight: '#0b0720', forest: '#04140d', sunset: '#190c05', rose: '#1a0711', ocean: '#04122b', amoled: '#000000', paper: '#f6f1e7', mint: '#e9f7ef', lavender: '#f1ecfb' };
  try {
    var t = localStorage.getItem('beta_theme');
    if (bars[t]) {
      document.documentElement.setAttribute('data-theme', t);
      var m = document.querySelector('meta[name="theme-color"]');
      if (m) m.setAttribute('content', bars[t]);
    }
  } catch (e) { /* storage blocked: the default (logo colours, dark) stays */ }
})();
