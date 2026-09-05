/* Whole-site theme: sepia (default) / light / dark.
   Reads the saved theme immediately to avoid a flash, then, for signed-in
   users, pulls the account preference from the API (so a theme set on the
   library page follows the account across devices). A small floating
   switcher is injected on every page that includes this script.

   Emits a 'babes-theme' CustomEvent when the theme changes so pages with
   bespoke theming (e.g. the reader) can stay in sync. */
(function () {
  'use strict';

  var KEY = 'site-theme';
  var VALID = { sepia: 1, light: 1, dark: 1 };

  function detect() {
    var t = localStorage.getItem(KEY) || 'sepia';
    return VALID[t] ? t : 'sepia';
  }

  function apply(t) {
    document.documentElement.setAttribute('data-theme', VALID[t] ? t : 'sepia');
  }

  function save(t) {
    try { localStorage.setItem(KEY, t); } catch (e) {}
  }

  var current = detect();
  apply(current);

  function switchTheme(t) {
    if (!VALID[t]) t = 'sepia';
    if (t === current) return;
    current = t;
    apply(t);
    save(t);
    document.dispatchEvent(new CustomEvent('babes-theme', { detail: { theme: t } }));
    if (window.isSignedIn && window.isSignedIn()) {
      window.api('/library/prefs', { method: 'PUT', body: { theme: t } })
        .catch(function () {});
    }
  }

  /* Sync the account theme the first time we know we're signed in. */
  (function syncAccount() {
    if (!window.isSignedIn || !window.isSignedIn()) return;
    window.api('/library/prefs').then(function (p) {
      if (p && VALID[p.theme]) {
        current = p.theme;
        apply(p.theme);
        save(p.theme);
      }
      if (p && p.reader_font_size) {
        try { localStorage.setItem('reader-size', p.reader_font_size); } catch (e) {}
      }
    }).catch(function () {});
  })();

  /* Keep the floating switcher's active state in sync. */
  document.addEventListener('babes-theme', function (ev) {
    document.querySelectorAll('.babes-theme-switcher button').forEach(function (b) {
      b.classList.toggle('active', b.dataset.t === ev.detail.theme);
    });
  });

  function mountSwitcher() {
    if (document.querySelector('.babes-theme-switcher')) return;
    var wrap = document.createElement('div');
    wrap.className = 'babes-theme-switcher';
    wrap.setAttribute('role', 'group');
    wrap.setAttribute('aria-label', 'Colour theme');
    var l = document.createElement('b');
    l.textContent = 'A';
    wrap.appendChild(l);
    ['sepia', 'light', 'dark'].forEach(function (t) {
      var b = document.createElement('button');
      b.type = 'button';
      b.dataset.t = t;
      b.textContent = 'S' === t ? 'Sepia' : t === 'light' ? 'Light' : 'Dark';
      b.style.width = 'auto';
      b.style.paddingLeft = '12px';
      b.style.paddingRight = '12px';
      b.title = t.charAt(0).toUpperCase() + t.slice(1) + ' theme';
      b.setAttribute('aria-pressed', String(current === t));
      b.classList.toggle('active', current === t);
      b.addEventListener('click', function () { switchTheme(t); });
      wrap.appendChild(b);
    });
    (document.body || document.documentElement).appendChild(wrap);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountSwitcher);
  } else {
    mountSwitcher();
  }
})();