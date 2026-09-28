/* Babe's Bookstore — global event delegation. */
/* CSP-safe: no inline handlers anywhere. Buttons use data-action/data-args,
 * selects/inputs use data-change/data-enter, forms use data-submit or
 * data-nosubmit. All handlers are resolved through the global scope at
 * call-time so page scripts can register functions freely. */
(function () {
  'use strict';

  /* The per-book download call to use in a listing card.
   *
   * Listing pages and the detail page must agree: the catalogue now shows
   * approved titles whose licence is still unconfirmed, and the download
   * endpoint refuses those. Rendering an unconditional <a href=...download>
   * therefore produces a card with a button that 403s the moment anyone
   * touches it, on every page that lists books. This lives here because
   * app.js is the one script loaded before every page's own code.
   *
   * An unconfirmed title gets the book page instead of a dead download --
   * the reader still gets somewhere to go, and can see the explanation. */
  window.downloadCta = function (b, dark) {
    if (b && b.asset_verified === false) {
      return '<a href="/books/' + b.id + '" class="flex-1 text-center text-xs font-semibold px-3 py-2 rounded-full bg-amber-50 text-amber-800 border border-amber-200">Asset check pending</a>';
    }
    if (dark) {
      return '<a href="/api/v1/books/' + b.id + '/download" class="flex-1 text-center text-xs font-semibold px-3 py-2 rounded-full bg-stone-100 text-stone-900 hover:bg-white">Free download</a>';
    }
    return '<a href="/api/v1/books/' + b.id + '/download" class="flex-1 text-center text-xs font-semibold px-3 py-2 rounded-full bg-[#0b0b0c] text-white hover:bg-black">Free download</a>';
  };

  function resolveArgs(el) {
    var argsAttr = el.getAttribute('data-args');
    if (argsAttr) {
      try {
        var raw = argsAttr.charAt(0) === '%' ? decodeURIComponent(argsAttr) : argsAttr;
        return JSON.parse(raw);
      } catch (e) { return []; }
    }
    var args = [];
    for (var i = 1; i <= 9; i++) {
      var v = el.getAttribute('data-arg-' + i);
      if (v === null) break;
      try { args.push(JSON.parse(v)); } catch (e) { args.push(v); }
    }
    return args;
  }

  function invoke(el) {
    var action = el.getAttribute('data-action');
    if (!action) return;
    var fn = window[action];
    if (typeof fn !== 'function') return;
    var args = resolveArgs(el);
    if (el.getAttribute('data-args')) {
      fn.apply(el, args);
    } else {
      fn.apply(el, args);
    }
  }

  function menuToggle(el) {
    var id = el.getAttribute('data-menu-id') || 'm';
    var target = document.getElementById(id);
    if (target) target.classList.toggle('hidden');
  }

  document.addEventListener('click', function (ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest('[data-action]') : null;
    if (!el) return;
    var action = el.getAttribute('data-action');
    if (action === 'menu-toggle') { menuToggle(el); return; }
    if (action === 'back') { ev.preventDefault(); history.back(); return; }
    if (action === 'scroll-top') { window.scrollTo({ top: 0, behavior: 'smooth' }); return; }
    if (el.tagName === 'A' || el.hasAttribute('data-prevent')) ev.preventDefault();
    invoke(el);
    var rm = el.getAttribute('data-remove-closest');
    if (rm) {
      var anc = el.closest(rm);
      if (anc) anc.remove();
    }
  });

  document.addEventListener('submit', function (ev) {
    var form = ev.target;
    if (form.hasAttribute('data-nosubmit')) { ev.preventDefault(); return; }
    var action = form.getAttribute('data-submit');
    if (action && typeof window[action] === 'function') {
      ev.preventDefault();
      window[action].call(form, ev);
    }
  });

  document.addEventListener('change', function (ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest('[data-change]') : null;
    if (!el) return;
    invoke(el);
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter') return;
    var el = ev.target && ev.target.closest ? ev.target.closest('[data-enter]') : null;
    if (!el) return;
    ev.preventDefault();
    invoke(el);
  });
})();