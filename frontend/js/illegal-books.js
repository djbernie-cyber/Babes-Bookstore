/* The William Majanja Illegal Books Catalog.
   Cookie-gated, country/status/search filters, "why banned" cards, and a
   flag-a-book flow that POSTs candidate censorship records to the backend.
   The catalog routes live under /api/v1/banned/* (see censorship.py).

   Rendering notes: the results are built as one HTML string and handed to the
   DOM in a single assignment, and "Show more" appends the next slice in one
   insertAdjacentHTML call. The previous version called insertAdjacentHTML once
   per country heading and once per card, so a large catalogue paid a parse and
   a reflow for every record. Flag buttons use one delegated listener on the
   results container rather than rebinding every card on every render. */
(function () {
  'use strict';

  var COOKIE = 'bb-illegal-ack';
  var PAGE_UNITS = 30;
  var SEARCH_DEBOUNCE_MS = 250;

  /* Light-surface badge pairs. Each label clears WCAG AA against its own pill
     in the light theme, and theme.css remaps both halves for dark. */
  var STATUSES = {
    banned: { label: 'Banned', chip: 'bg-red-50 text-red-700 border-red-200', edge: 'border-l-red-600' },
    restricted: { label: 'Restricted', chip: 'bg-amber-50 text-amber-800 border-amber-200', edge: 'border-l-amber-600' },
    contested: { label: 'Contested', chip: 'bg-sky-50 text-sky-800 border-sky-200', edge: 'border-l-sky-600' }
  };

  var state = { country: '', status: '', q: '', countries: [] };
  var units = [];        /* flattened render units: {label,count} | {item} */
  var unitsShown = 0;
  var records = 0;       /* total records returned by the current query */
  var inFlight = null;   /* AbortController for the active records request */
  var searchTimer = null;

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

  function $(id) { return document.getElementById(id); }

  /* ---- Gate ---- */
  function initGate() {
    var gate = $('gate');
    if (!gate) return;
    if (getCookie(COOKIE)) {
      gate.classList.add('hidden');
    } else {
      gate.classList.remove('hidden');
      gate.classList.add('flex');
      $('gate-accept').addEventListener('click', function () {
        setCookie(COOKIE, '1', $('gate-remember').checked ? 30 : 0);
        gate.classList.add('hidden');
        gate.classList.remove('flex');
      });
    }
    var reset = $('gate-reset');
    if (reset) {
      reset.addEventListener('click', function () { clearCookie(COOKIE); location.reload(); });
    }
  }

  /* ---- Boot ---- */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { initGate(); initFilters(); bindResults(); load(); });
  } else {
    initGate(); initFilters(); bindResults(); load();
  }

  function readFilters() {
    state.country = $('f-country').value;
    state.status = $('f-status').value;
    state.q = $('f-q').value.trim().toLowerCase();
  }

  function initFilters() {
    $('f-apply').addEventListener('click', function () {
      if (searchTimer) { clearTimeout(searchTimer); searchTimer = null; }
      readFilters();
      load();
    });
    $('f-q').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); $('f-apply').click(); }
    });
    /* Typing filters on its own, but not on every keystroke. */
    $('f-q').addEventListener('input', function () {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(function () { searchTimer = null; readFilters(); load(); }, SEARCH_DEBOUNCE_MS);
    });
    $('f-country').addEventListener('change', function () { readFilters(); load(); });
    $('f-status').addEventListener('change', function () { readFilters(); load(); });
  }

  /* One delegated listener for every flag button, attached once. */
  function bindResults() {
    var results = $('results');
    results.addEventListener('click', function (e) {
      var btn = e.target.closest ? e.target.closest('[data-action="flag"]') : null;
      if (btn) { e.preventDefault(); toggleFlag(btn.closest('[data-book-id]')); }
    });

    /* "Show more" is rendered into #more-wrap, which is a SIBLING of #results,
       not a descendant. A listener on #results therefore never saw the click,
       and on any page with more than PAGE_UNITS records the button did
       nothing at all. Bind it where the button actually lives. #more-wrap
       persists across loads (updateMore only rewrites its innerHTML), so this
       is bound once alongside the others. */
    $('more-wrap').addEventListener('click', function (e) {
      var more = e.target.closest ? e.target.closest('[data-action="more"]') : null;
      if (more) { e.preventDefault(); showMore(); }
    });

    results.addEventListener('submit', function (e) {
      if (e.target.classList && e.target.classList.contains('flag-form')) {
        submitFlag(e, e.target.closest('[data-book-id]'));
      }
    });
  }

  /* ---- Data ---- */
  function load() {
    var results = $('results');
    var meta = $('results-meta');
    var loading = $('loading');
    var empty = $('empty');
    var errorEl = $('error');
    var moreWrap = $('more-wrap');

    /* Drop any in-flight request so a slow earlier filter cannot overwrite a
       newer one. */
    if (inFlight) { inFlight.abort(); inFlight = null; }

    results.classList.add('hidden');
    results.setAttribute('aria-busy', 'true');
    empty.classList.add('hidden');
    errorEl.classList.add('hidden');
    moreWrap.classList.add('hidden');
    moreWrap.innerHTML = '';
    loading.classList.remove('hidden');
    meta.textContent = '';

    var params = [];
    if (state.country) params.push('country=' + encodeURIComponent(state.country));
    if (state.status) params.push('status=' + encodeURIComponent(state.status));
    if (state.q) params.push('q=' + encodeURIComponent(state.q));

    var ctrl = typeof AbortController === 'function' ? new AbortController() : null;
    inFlight = ctrl;

    var req = api('/banned/records' + (params.length ? '?' + params.join('&') : ''),
                  ctrl ? { signal: ctrl.signal } : undefined);

    req.then(function (data) {
      if (inFlight !== ctrl) return;      /* a newer request already won */
      inFlight = null;
      loading.classList.add('hidden');
      results.classList.remove('hidden');
      results.setAttribute('aria-busy', 'false');

      var items = data.items || [];
      records = items.length;
      buildUnits(items);
      /* unitsShown must describe what is actually on the page. Leaving it at 0
         made the first render claim "Showing 0 of N" and, once Show more
         worked at all, re-insert units[0:30] -- a duplicate of page one. */
      unitsShown = Math.min(PAGE_UNITS, units.length);
      results.innerHTML = sliceMarkup(0, unitsShown);

      if (!items.length) {
        empty.classList.remove('hidden');
        meta.textContent = 'No records match.';
      } else {
        meta.textContent = 'Showing ' + countItems(0, unitsShown) + ' of ' + records + ' record' + (records === 1 ? '' : 's') + '.';
        updateMore();
      }
      guardCovers(results);
    }).catch(function (err) {
      if (inFlight !== ctrl) return;
      inFlight = null;
      if (err && err.cancelled) return;            /* a newer request won */
      loading.classList.add('hidden');
      results.setAttribute('aria-busy', 'false');
      errorEl.textContent = err.message || 'Could not load the catalogue.';
      errorEl.classList.remove('hidden');
    });

    if (!state.countries.length) loadCountries();
  }

  function loadCountries() {
    api('/banned/countries').then(function (d) {
      state.countries = (d.items || []).map(function (c) {
        return { code: c.country_code, name: c.country_name, total: c.total };
      }).sort(function (a, b) { return b.total - a.total; });
      var sel = $('f-country');
      state.countries.forEach(function (c) {
        var o = document.createElement('option');
        o.value = c.code; o.textContent = c.name + ' (' + c.total + ')';
        sel.appendChild(o);
      });
    }).catch(function () { /* the flag form degrades to a message */ });
  }

  function buildUnits(items) {
    var byCountry = {};
    items.forEach(function (it) {
      var k = it.country_name || 'Unknown';
      (byCountry[k] = byCountry[k] || []).push(it);
    });
    var out = [];
    Object.keys(byCountry).sort().forEach(function (k) {
      out.push({ label: k, count: byCountry[k].length });
      byCountry[k].forEach(function (it) { out.push({ item: it }); });
    });
    units = out;
  }

  function isLabel(u) { return u.label !== undefined; }

  function countItems(from, to) {
    var n = 0;
    for (var i = from; i < to && i < units.length; i++) if (!isLabel(units[i])) n++;
    return n;
  }

  /* Markup for units[from:to]. One join(), so the caller does one DOM write. */
  function sliceMarkup(from, to) {
    var out = [];
    for (var i = from; i < to && i < units.length; i++) {
      var u = units[i];
      if (isLabel(u)) {
        out.push('<p class="text-xs uppercase tracking-widest text-stone-500 mt-6 mb-1 col-span-full">'
          + '<span class="text-stone-900 font-semibold">' + esc(u.label) + '</span> — '
          + u.count + ' record' + (u.count === 1 ? '' : 's') + '</p>');
      } else {
        out.push(renderCard(u.item));
      }
    }
    return out.join('');
  }

  function showMore() {
    var results = $('results');
    /* Clamp to what exists, so the final click cannot claim a page past the
       end of the list. */
    var next = Math.min(unitsShown + PAGE_UNITS, units.length);
    if (next <= unitsShown) { updateMore(); return; }
    results.insertAdjacentHTML('beforeend', sliceMarkup(unitsShown, next));
    unitsShown = next;
    $('results-meta').textContent = 'Showing ' + countItems(0, unitsShown) + ' of ' + records
      + ' record' + (records === 1 ? '' : 's') + '.';
    updateMore();
    guardCovers(results);
  }

  function updateMore() {
    var wrap = $('more-wrap');
    if (unitsShown >= units.length) {
      wrap.classList.add('hidden');
      wrap.innerHTML = '';
      return;
    }
    wrap.classList.remove('hidden');
    wrap.innerHTML = '<button data-action="more" class="min-h-[44px] px-6 py-3 rounded-full border border-stone-300 bg-white text-sm font-medium hover:bg-stone-50">Show more</button>';
  }

  /* CSP is script-src 'self', so an inline onerror attribute never fires.
     Broken covers are hidden here instead. */
  function guardCovers(scope) {
    scope.querySelectorAll('img[data-cover]').forEach(function (img) {
      if (img.dataset.guarded) return;
      img.dataset.guarded = '1';
      img.addEventListener('error', function () { img.style.visibility = 'hidden'; });
    });
  }

  function renderCard(it) {
    var b = it.book || {};
    // A record may document a work we do not carry (still in copyright). Fall
    // back to the work's own identity so the card is never anonymous.
    var title = b.title || it.work_title || 'Untitled';
    var author = b.author || it.work_author || '';
    var year = b.publication_year || it.work_year || '';
    var badge = STATUSES[it.status] || STATUSES.contested;
    var cover = b.cover_url
      ? '<img data-cover src="' + esc(b.cover_url) + '" alt="Cover of ' + esc(title) + '" loading="lazy" decoding="async" class="w-20 h-28 object-cover rounded-lg border border-stone-200 bg-stone-100">'
      : '<div class="w-20 h-28 rounded-lg border border-stone-200 bg-stone-100 flex items-center justify-center text-[10px] uppercase tracking-widest text-stone-500 px-2 text-center">No cover</div>';
    var readCta = b.id
      ? '<a class="inline-flex items-center gap-1.5 min-h-[44px] px-4 py-2 rounded-full bg-stone-900 text-white text-xs font-semibold hover:bg-stone-700" href="/books/' + b.id + '">Read / Download</a>'
      : '<span class="inline-flex items-center min-h-[44px] px-4 py-2 rounded-full border border-stone-300 text-stone-600 text-xs font-medium">Not in catalogue</span>';
    var years = year ? ' · ' + esc(year) : '';
    /* Provenance is shown on the card, not just the page notice. A harvested
       entry and a hand-written one are not the same kind of claim, and a reader
       looking at a specific book should not have to go hunting for which it is. */
    var prov = it.provenance === 'harvested'
      ? '<a class="text-[10px] uppercase tracking-widest font-semibold text-stone-500 border border-stone-300 rounded px-1.5 py-0.5 hover:text-stone-900 hover:border-stone-500" href="' + esc(it.source_url || '#') + '" target="_blank" rel="noopener noreferrer" title="Machine-read from a cited public source. Not editorially verified.">harvested · check source</a>'
      : (it.provenance === 'curated'
        ? '<span class="text-[10px] uppercase tracking-widest font-semibold text-stone-500 border border-stone-300 rounded px-1.5 py-0.5" title="Written and checked by an editor.">curated</span>'
        : '');
    return '' +
      '<article class="rounded-2xl border border-stone-200 border-l-4 ' + badge.edge + ' bg-white p-5 flex gap-5" data-book-id="' + (b.id || '') + '">' +
      '  <div class="shrink-0">' + cover + '</div>' +
      '  <div class="min-w-0 flex-1">' +
      '    <div class="flex flex-wrap items-center gap-2">' +
      '      <span class="px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-bold border ' + badge.chip + '">' + badge.label + '</span>' +
      (it.banned_since ? '<span class="text-[11px] text-stone-500">since ' + esc(it.banned_since) + '</span>' : '') +
      prov +
      '    <h3 class="font-serif text-lg font-semibold text-stone-900 mt-1.5 leading-snug">' + esc(title) +
      (author ? ' <span class="font-normal text-stone-600 text-base">— ' + esc(author) + years + '</span>' : '') + '</h3>' +
      '    <p class="text-[11px] uppercase tracking-widest text-stone-500 mt-1">Banned in ' + esc(it.country_name || '?') + '</p>' +
      '    <p class="text-sm text-stone-700 leading-6 mt-2">' + esc(it.ban_reason || 'No documented reason recorded yet.') + '</p>' +
      '    <div class="flex flex-wrap items-center gap-2 mt-4">' + readCta +
      '      <button data-action="flag" class="min-h-[44px] px-4 py-2 rounded-full border border-stone-300 text-stone-700 text-xs font-medium hover:bg-stone-50">Flag in another country</button>' +
      '    </div>' +
      '  </div>' +
      '</article>';
  }

  function toggleFlag(card) {
    if (!card) return;
    var existing = card.querySelector('.flag-form');
    if (existing) { existing.remove(); return; }
    card.insertAdjacentHTML('beforeend', flagForm());
  }

  function flagForm() {
    if (!state.countries.length) {
      return '<div class="flag-form mt-4 pt-4 border-t border-stone-200 w-full">'
        + '<p class="text-xs text-stone-600">Country list still loading — try again in a moment.</p></div>';
    }
    var opts = state.countries.map(function (c) {
      return '<option value="' + esc(c.code) + '">' + esc(c.name) + '</option>';
    }).join('');
    return '' +
      '<div class="flag-form mt-4 pt-4 border-t border-stone-200 w-full">' +
      '<p class="text-xs font-semibold uppercase tracking-widest text-stone-600">Flag this book in another country</p>' +
      '<div class="grid sm:grid-cols-2 gap-3 mt-3">' +
      '  <label class="sr-only" for="ff-c1">Country</label>' +
      '  <select id="ff-c1" class="ff-country w-full min-h-[44px] bg-white border border-stone-300 rounded-lg px-3 py-2 text-base"><option value="">Select country…</option>' + opts + '</select>' +
      '  <label class="sr-only" for="ff-s1">Status</label>' +
      '  <select id="ff-s1" class="ff-status w-full min-h-[44px] bg-white border border-stone-300 rounded-lg px-3 py-2 text-base">' +
      '    <option value="banned">Banned</option><option value="restricted">Restricted</option><option value="contested">Contested</option></select>' +
      '</div>' +
      '<label class="sr-only" for="ff-r1">Why was it banned there?</label>' +
      '<textarea id="ff-r1" class="ff-reason w-full mt-3 min-h-[72px] bg-white border border-stone-300 rounded-lg px-3 py-2 text-base" placeholder="Where / when / why was it banned there? (facts, dates, sources help the curator)"></textarea>' +
      '<div class="flex flex-wrap items-center gap-3 mt-3">' +
      '  <button type="submit" class="min-h-[44px] px-4 py-2 rounded-full bg-red-600 text-white text-xs font-semibold hover:bg-red-700">Submit flag</button>' +
      '  <span class="ff-msg text-xs text-stone-600"></span>' +
      '</div></div>';
  }

  function setMsg(el, text, tone) {
    el.textContent = text;
    el.className = 'ff-msg text-xs ' + (tone === 'bad' ? 'text-amber-700'
      : tone === 'good' ? 'text-emerald-700' : 'text-stone-600');
  }

  function submitFlag(e, card) {
    e.preventDefault();
    var frm = e.target;
    var msg = frm.querySelector('.ff-msg');
    var reason = frm.querySelector('.ff-reason').value.trim();
    var countryCode = frm.querySelector('.ff-country').value;
    var status = frm.querySelector('.ff-status').value;
    var bookId = card ? card.getAttribute('data-book-id') : '';
    if (!countryCode || !reason) { setMsg(msg, 'Choose a country and describe the ban.', 'bad'); return; }
    if (!bookId) { setMsg(msg, 'This book is not in the catalogue — please use a book page directly.', 'bad'); return; }
    setMsg(msg, 'Submitting…', 'idle');

    api('/banned/books/' + bookId + '/flag', {
      method: 'POST',
      body: { reason: reason, country_code: countryCode, status: status }
    }).then(function () {
      setMsg(msg, 'Submitted for review — thank you. The catalogue grows by verification, not opinion.', 'good');
      frm.querySelectorAll('button, input, select, textarea').forEach(function (x) { x.disabled = true; });
    }).catch(function (err) {
      setMsg(msg, err && err.status === 409
        ? 'A record for that country is already on file.'
        : err && err.status === 401
          ? 'Sign in required before you can flag a book.'
          : (err && err.message) || 'Could not submit the flag.', 'bad');
    });
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (m) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
    });
  }
})();
