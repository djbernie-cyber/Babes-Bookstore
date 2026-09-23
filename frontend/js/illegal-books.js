/* The William Majanja Illegal Books Catalog.
   Cookie-gated, country/status/search filters, "why banned" cards, and a
   flag-a-book flow that POSTs candidate censorship records to the backend.
   The catalog routes live under /api/v1/banned/* (see censorship.py). */
(function () {
  'use strict';

  var COOKIE = 'bb-illegal-ack';
  var STATUSES = {
    banned: { label: 'Banned', cls: 'bg-red-950/60 text-red-300 border-red-900/60' },
    restricted: { label: 'Restricted', cls: 'bg-amber-950/60 text-amber-300 border-amber-900/60' },
    contested: { label: 'Contested', cls: 'bg-sky-950/60 text-sky-300 border-sky-900/60' }
  };

  var state = { country: '', status: '', q: '', countries: [] };
  var bookIdByRecord = {};

  function getCookie(name) {
    return document.cookie.split('; ').filter(function (c) { return c.indexOf(name + '=') === 0; }).length > 0;
  }
  function setCookie(name, value, days) {
    var d = new Date();
    d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
    document.cookie = name + '=' + value + '; expires=' + d.toUTCString() + '; path=/; SameSite=Lax';
  }
  function clearCookie(name) {
    document.cookie = name + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  }

  /* ---- Gate ---- */
  function initGate() {
    var gate = document.getElementById('gate');
    if (!getCookie(COOKIE)) {
      gate.classList.remove('hidden');
      gate.classList.add('flex');
      var accept = document.getElementById('gate-accept');
      var remember = document.getElementById('gate-remember');
      accept.addEventListener('click', function () {
        setCookie(COOKIE, '1', remember.checked ? 30 : 0);
        gate.classList.add('hidden');
        gate.classList.remove('flex');
      });
    } else {
      gate.classList.add('hidden');
    }
    var reset = document.getElementById('gate-reset');
    if (reset) reset.addEventListener('click', function () { clearCookie(COOKIE); location.reload(); });
  }

  /* ---- Data ---- */
  window.addEventListener('DOMContentLoaded', function () {
    initGate();
    initFilters();
    load();
  });

  function initFilters() {
    var apply = document.getElementById('f-apply');
    apply.addEventListener('click', function () {
      state.country = document.getElementById('f-country').value;
      state.status = document.getElementById('f-status').value;
      state.q = document.getElementById('f-q').value.trim().toLowerCase();
      load();
    });
    document.getElementById('f-q').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') apply.click();
    });
  }

  function load() {
    var el = document.getElementById('results');
    var meta = document.getElementById('results-meta');
    var loading = document.getElementById('loading');
    var empty = document.getElementById('empty');
    var errorEl = document.getElementById('error');
    el.classList.add('hidden');
    empty.classList.add('hidden');
    errorEl.classList.add('hidden');
    loading.classList.remove('hidden');
    meta.textContent = '';

    var params = [];
    if (state.country) params.push('country=' + encodeURIComponent(state.country));
    if (state.status) params.push('status=' + encodeURIComponent(state.status));
    if (state.q) params.push('q=' + encodeURIComponent(state.q));

    api('/banned/records' + (params.length ? '?' + params.join('&') : '')).then(function (data) {
      loading.classList.add('hidden');
      el.classList.remove('hidden');
      var items = data.items || [];
      var byCountry = {};
      items.forEach(function (it) {
        bookIdByRecord[it.id] = it.book ? it.book.id : null;
        var k = it.country_name || 'Unknown';
        (byCountry[k] = byCountry[k] || []).push(it);
        byCountry[k].country = k;
      });
      var groups = Object.keys(byCountry).sort().map(function (k) { return byCountry[k]; });
      groups.forEach(function (group) {
        var label = '<p class="text-xs uppercase tracking-widest text-stone-500 mt-6 mb-1">' +
          '<span class="text-stone-300 font-semibold">' + esc(group.country) + '</span> — ' +
          group.length + ' record' + (group.length === 1 ? '' : 's') + '</p>';
        el.insertAdjacentHTML('beforeend', label);
        group.forEach(function (it) { el.insertAdjacentHTML('beforeend', renderCard(it)); });
      });
      if (!items.length) empty.classList.remove('hidden');
      meta.innerHTML = '<p class="text-sm text-stone-500">' + items.length + ' record' + (items.length === 1 ? '' : 's') + ' shown.</p>';
      bindFlags();
    }).catch(function (err) {
      loading.classList.add('hidden');
      errorEl.textContent = err.message;
      errorEl.classList.remove('hidden');
    });

    if (!state.countries.length) {
      api('/banned/countries').then(function (d) {
        state.countries = (d.items || []).map(function (c) {
          return { code: c.country_code, name: c.country_name, total: c.total };
        });
        state.countries.sort(function (a, b) { return b.total - a.total; });
        var sel = document.getElementById('f-country');
        state.countries.forEach(function (c) {
          var o = document.createElement('option');
          o.value = c.code; o.textContent = c.name + ' (' + c.total + ')';
          sel.appendChild(o);
        });
      }).catch(function () {});
    }
  }

  function renderCard(it) {
    var b = it.book || {};
    var badge = STATUSES[it.status] || STATUSES.contested;
    var cover = b.cover_url
      ? '<img src="' + esc(b.cover_url) + '" alt="Cover" loading="lazy" class="w-20 h-28 object-cover rounded-lg border border-stone-700 bg-stone-800" onerror="this.style.visibility=\'hidden\'">'
      : '<div class="w-20 h-28 rounded-lg border border-stone-700 bg-stone-800 flex items-center justify-center text-[10px] uppercase tracking-widest text-stone-500 px-2 text-center">No cover</div>';
    var readCta = b.id
      ? '<a class="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-white text-[#0b0b0c] text-xs font-semibold hover:bg-stone-200" href="/books/' + b.id + '">Read / Download</a>'
      : '<span class="inline-flex items-center px-4 py-2 rounded-full border border-stone-600 text-stone-500 text-xs font-medium">Not in catalogue</span>';
    var years = b.publication_year ? ' · ' + esc(b.publication_year) : '';
    return '' +
      '<article class="rounded-2xl border ' + badge.cls + ' bg-[#1c1b1a] p-5 flex gap-5" data-book-id="' + (b.id || '') + '">' +
      '  <div class="shrink-0">' + cover + '</div>' +
      '  <div class="min-w-0 flex-1">' +
      '    <div class="flex flex-wrap items-center gap-2">' +
      '      <span class="px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-bold border ' + badge.cls + '">' + badge.label + '</span>' +
      (it.banned_since ? '<span class="text-[11px] text-stone-500">since ' + esc(it.banned_since) + '</span>' : '') +
      '    </div>' +
      '    <h3 class="font-serif text-lg font-semibold text-stone-100 mt-1.5 leading-snug">' + esc(b.title || 'Untitled') +
      (b.author ? ' <span class="font-normal text-stone-400 text-base">— ' + esc(b.author) + years + '</span>' : '') + '</h3>' +
      '    <p class="text-[11px] uppercase tracking-widest text-stone-500 mt-1">Banned in ' + esc(it.country_name || '?') + '</p>' +
      '    <p class="text-sm text-stone-300 leading-6 mt-2">' + esc(it.ban_reason || 'No documented reason recorded yet.') + '</p>' +
      '    <div class="flex flex-wrap items-center gap-2 mt-4">' + readCta +
      '      <button data-action="flag" class="px-4 py-2 rounded-full border border-stone-600 text-stone-300 text-xs font-medium hover:bg-stone-800">Flag in another country</button>' +
      '    </div>' +
      '  </div>' +
      '</article>';
  }

  function bindFlags() {
    var toggles = document.querySelectorAll('[data-action="flag"]');
    if (toggles.length) {
      document.querySelectorAll('#results article').forEach(function (card) {
        if (card.querySelector('.flag-form')) card.querySelector('.flag-form').remove();
      });
    }
    toggles.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var card = btn.closest('[data-book-id]');
        var existing = card.querySelector('.flag-form');
        if (existing) { existing.remove(); return; }
        card.insertAdjacentHTML('beforeend', flagForm());
        card.querySelector('.flag-form').addEventListener('submit', function (e) { submitFlag(e, card); });
      });
    });
  }

  function flagForm() {
    if (!state.countries.length) {
      return '<div class="flag-form mt-4 pt-4 border-t border-stone-700 w-full">' +
        '<p class="text-xs text-stone-500">Country list still loading — try again in a moment.</p></div>';
    }
    var opts = state.countries.map(function (c) {
      return '<option value="' + esc(c.code) + '">' + esc(c.name) + '</option>';
    }).join('');
    return '' +
      '<div class="flag-form mt-4 pt-4 border-t border-stone-700 w-full">' +
      '<p class="text-xs font-semibold uppercase tracking-widest text-stone-400">Flag this book in another country</p>' +
      '<div class="grid sm:grid-cols-2 gap-3 mt-3">' +
      '  <select class="ff-country bg-[#0b0b0c] border border-stone-700 rounded-lg px-3 py-2 text-sm"><option value="">Select country…</option>' + opts + '</select>' +
      '  <select class="ff-status bg-[#0b0b0c] border border-stone-700 rounded-lg px-3 py-2 text-sm">' +
      '    <option value="banned">Banned</option><option value="restricted">Restricted</option><option value="contested">Contested</option></select>' +
      '</div>' +
      '<textarea class="ff-reason bg-[#0b0b0c] border border-stone-700 rounded-lg px-3 py-2 text-sm w-full mt-3 min-h-[72px]" placeholder="Where / when / why was it banned there? (facts, dates, sources help the curator)"></textarea>' +
      '<div class="flex items-center gap-3 mt-3">' +
      '  <button type="submit" class="px-4 py-2 rounded-full bg-red-600 text-white text-xs font-semibold hover:bg-red-500">Submit flag</button>' +
      '  <span class="ff-msg text-xs"></span>' +
      '</div></div>';
  }

  function submitFlag(e, card) {
    e.preventDefault();
    var frm = card.querySelector('.flag-form');
    var msg = frm.querySelector('.ff-msg');
    var reason = frm.querySelector('.ff-reason').value.trim();
    var countryCode = frm.querySelector('.ff-country').value;
    var status = frm.querySelector('.ff-status').value;
    var bookId = card.getAttribute('data-book-id');
    if (!countryCode || !reason) {
      msg.textContent = 'Choose a country and describe the ban.';
      msg.classList.remove('text-stone-400'); msg.classList.add('text-amber-400');
      return;
    }
    if (!bookId) {
      msg.textContent = 'This book is not in the catalogue — please use a book page directly.';
      msg.classList.remove('text-stone-400'); msg.classList.add('text-amber-400');
      return;
    }
    msg.textContent = 'Submitting…'; msg.className = 'ff-msg text-xs text-stone-400';

    api('/banned/books/' + bookId + '/flag', {
      method: 'POST',
      body: { reason: reason, country_code: countryCode, status: status }
    }).then(function () {
      msg.textContent = 'Submitted for review — thank you. The catalogue grows by verification, not opinion.';
      msg.classList.remove('text-stone-400'); msg.classList.add('text-emerald-400');
      frm.querySelectorAll('button, input, select, textarea').forEach(function (x) { x.disabled = true; });
    }).catch(function (err) {
      msg.textContent = err.status === 409
        ? 'A record for that country is already on file.'
        : err.status === 401
          ? 'Sign in required before you can flag a book.'
          : err.message;
      msg.classList.remove('text-stone-400'); msg.classList.add('text-amber-400');
    });
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (m) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
    });
  }
})();