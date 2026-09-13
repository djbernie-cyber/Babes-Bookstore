/* Babe's Bookstore — global event delegation. */
/* CSP-safe: no inline handlers anywhere. Buttons use data-action/data-args,
 * selects/inputs use data-change/data-enter, forms use data-submit or
 * data-nosubmit. All handlers are resolved through the global scope at
 * call-time so page scripts can register functions freely. */
(function () {
  'use strict';

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