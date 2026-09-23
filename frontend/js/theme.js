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
  var ORDER = ['sepia', 'light', 'dark'];
  var LABELS = { sepia: 'Sepia', light: 'Light', dark: 'Dark' };
  var ICONS = {
    sepia: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18z"/></svg>',
    light: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>',
    dark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
  };

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

  function metaColor(t) {
    return t === 'light' ? '#ffffff' : t === 'dark' ? '#0b0b0c' : '#f6f1e7';
  }

  /* Keep the browser-chrome colour (address bar, overscroll) in step. */
  function syncMeta(t) {
    var m = document.querySelector('meta[name="theme-color"]');
    if (m) { m.setAttribute('content', metaColor(t)); }
    else {
      m = document.createElement('meta');
      m.setAttribute('name', 'theme-color');
      m.setAttribute('content', metaColor(t));
      document.head.appendChild(m);
    }
  }

  var current = detect();
  apply(current);
  syncMeta(current);

  function switchTheme(t) {
    if (!VALID[t]) t = 'sepia';
    if (t === current) return;
    current = t;
    apply(t);
    save(t);
    syncMeta(t);
    document.dispatchEvent(new CustomEvent('babes-theme', { detail: { theme: t } }));
    if (window.isSignedIn && window.isSignedIn()) {
      window.api('/library/prefs', { method: 'PUT', body: { theme: t } })
        .catch(function () {});
    }
  }

  /* Alt+Shift+T cycles sepia → light → dark from anywhere. */
  document.addEventListener('keydown', function (e) {
    if (e.altKey && e.shiftKey && (e.key === 'T' || e.key === 't')) {
      e.preventDefault();
      switchTheme(ORDER[(ORDER.indexOf(current) + 1) % ORDER.length]);
    }
  });

  /* Sync the account theme the first time we know we're signed in. */
  (function syncAccount() {
    if (!window.isSignedIn || !window.isSignedIn()) return;
    window.api('/library/prefs').then(function (p) {
      if (p && VALID[p.theme]) {
        current = p.theme;
        apply(p.theme);
        save(p.theme);
        syncMeta(p.theme);
      }
      if (p && p.reader_font_size) {
        try { localStorage.setItem('reader-size', p.reader_font_size); } catch (e) {}
      }
    }).catch(function () {});
  })();

  /* Keep the floating switcher's active state in sync. */
  document.addEventListener('babes-theme', function (ev) {
    var t = ev.detail.theme;
    document.querySelectorAll('.babes-theme-switcher button').forEach(function (b) {
      var on = b.dataset.t === t;
      b.classList.toggle('active', on);
      b.setAttribute('aria-checked', String(on));
    });
  });

  function icon(t) {
    var s = document.createElement('span');
    s.className = 'babes-theme-icon';
    s.innerHTML = ICONS[t];
    return s;
  }

  function mountSwitcher() {
    if (document.querySelector('.babes-theme-switcher')) return;
    var wrap = document.createElement('div');
    wrap.className = 'babes-theme-switcher';
    wrap.setAttribute('role', 'radiogroup');
    wrap.setAttribute('aria-label', 'Colour theme');

    var lab = document.createElement('span');
    lab.className = 'babes-theme-label';
    lab.textContent = 'Theme';
    wrap.appendChild(lab);

    ORDER.forEach(function (t, i) {
      var b = document.createElement('button');
      b.type = 'button';
      b.dataset.t = t;
      b.className = 'switcher-button';
      b.setAttribute('role', 'radio');
      b.setAttribute('aria-checked', String(current === t));
      b.title = t === 'sepia' ? 'Warm paper (default)' : t === 'light' ? 'Clean white' : 'Night reading';
      b.appendChild(icon(t));
      var label = document.createElement('span');
      label.textContent = LABELS[t];
      b.appendChild(label);
      b.classList.toggle('active', current === t);
      b.addEventListener('click', function () { switchTheme(t); });
      b.addEventListener('keydown', function (e) {
        if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
        e.preventDefault();
        var next = ORDER[(i + (e.key === 'ArrowRight' ? 1 : -1) + ORDER.length) % ORDER.length];
        switchTheme(next);
        var btn = wrap.querySelector('button[data-t="' + next + '"]');
        if (btn) btn.focus();
      });
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