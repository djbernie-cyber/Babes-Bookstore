/* Babe's Bookstore reader — Kindle-style.
   Chapter-aware TOC, two modes (Pages / Scroll), measured pagination, and
   "read elsewhere" export links. Progress syncs to the account (percent +
   a position anchor that also drives resume). */
(function () {
  'use strict';

  function bookId() {
    var p = location.pathname.split('/').filter(Boolean);
    if (p[p.length - 1] === 'read' && p.length >= 3) return p[p.length - 2];
    return p[p.length - 1];
  }
  var BID = bookId();
  var ID = encodeURIComponent(BID);
  var SCROLL_KEY = 'reader-size', THEME_KEY = 'reader-theme', MODE_KEY = 'reader-mode';
  /* Set only when the reader actually picks a mode. An earlier build stored
     MODE_KEY without this, so a single stray tap put a visitor in scroll mode
     and localStorage outvoted the default on every later visit, with nothing
     on screen to explain why. A stored mode is now honoured only once the
     reader is known to have chosen it. */
  var MODE_SET_KEY = 'reader-mode-chosen';
  var FONT_KEY = 'reader-font', LH_KEY = 'reader-leading',
      JUSTIFY_KEY = 'reader-justify', MEASURE_KEY = 'reader-measure';

  var CHUNK = 160;
  var SIZES = ['s', 'm', 'l', 'xl'];
  var PAPERS = { sepia: 1, light: 1, dark: 1 };

  function token() { return localStorage.getItem('token'); }
  function el(id) { return document.getElementById(id); }

  /* ── preferences ────────────────────────────────────────────────── */
  function setPrefs() {
    var size = localStorage.getItem(SCROLL_KEY) || 'm';
    var theme = localStorage.getItem(THEME_KEY) || 'sepia';
    var mode = localStorage.getItem(MODE_SET_KEY) ? (localStorage.getItem(MODE_KEY) || 'pages') : 'pages';
    if (SIZES.indexOf(size) < 0) size = 'm';
    if (!PAPERS[theme]) theme = 'sepia';
    document.documentElement.setAttribute('data-size', size);
    // The reader paints its own paper colour. It deliberately does not share
    // the storefront's theme: the two used to fight over one saved preference,
    // so reading in Dark silently recoloured the whole site and vice versa.
    document.documentElement.setAttribute('data-theme', theme);
    applyTypography();
    document.querySelectorAll('.fs-btn button').forEach(function (b) {
      var on = b.dataset.size === size;
      b.classList.toggle('active', on);
      b.setAttribute('aria-checked', String(on));
    });
    var ts = el('theme');
    if (ts) ts.value = theme;
    document.querySelectorAll('.mode-btn').forEach(function (b) {
      var on = b.dataset.mode === mode;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', String(on));
    });
    var label = el('paper-label');
    if (label) label.textContent = (ts && ts.options[ts.selectedIndex] || {}).textContent || '';
    setMode(mode, false);
  }
  function saveAccountPrefs() {
    var t = token(); if (!t) return;
    var size = localStorage.getItem(SCROLL_KEY) || 'm';
    var theme = localStorage.getItem(THEME_KEY) || 'sepia';
    fetch('/api/v1/library/prefs', {
      method: 'PUT', headers: { 'Authorization': 'Bearer ' + t, 'Content-Type': 'application/json' },
      body: JSON.stringify({ reader_font_size: size, reader_theme: theme })
    }).catch(function () {});
  }
  function loadAccountPrefs() {
    var t = token();
    if (!t) { setPrefs(); return; }
    fetch('/api/v1/library/prefs', { headers: { 'Authorization': 'Bearer ' + t } }).then(function (r) {
      if (!r.ok) throw 0; return r.json();
    }).then(function (p) {
      if (p && p.reader_theme) localStorage.setItem(THEME_KEY, p.reader_theme);
      if (p && p.reader_font_size) localStorage.setItem(SCROLL_KEY, p.reader_font_size);
      setPrefs();
    }).catch(function () { setPrefs(); });
  }

  /* ── structure: chapters + blocks ───────────────────────────────── */
  var chapters = [];
  var blockCount = 0;
  var BLOCK_TAGS = { P: 1, LI: 1, TD: 1, TH: 1, PRE: 1, BLOCKQUOTE: 1, DD: 1, DT: 1 };
  var CONTAINER_TAGS = { DIV: 1, SECTION: 1, ARTICLE: 1, MAIN: 1, TABLE: 1, OL: 1, UL: 1, TR: 1, DL: 1, FIGURE: 1, BODY: 1, HTML: 1 };

  function walk(node, chapter) {
    if (node.nodeType === 1) {
      var tag = node.tagName;
      if (/^H[1-6]$/.test(tag)) {
        var t = (node.textContent || '').replace(/\s+/g, ' ').trim();
        if (t) {
          chapter = { title: t, blocks: [] };
          chapters.push(chapter);
        }
        return;
      }
      if (BLOCK_TAGS[tag]) {
        var text = (node.textContent || '').replace(/[ \t\r\n]+/g, ' ').trim();
        if (text) { chapter.blocks.push({ text: text }); blockCount++; }
        return;
      }
      if (node.tagName === 'IMG') {
        var src = node.getAttribute('src') || node.getAttribute('data-src') || '';
        if (src) { chapter.blocks.push({ img: true, src: src }); blockCount++; }
        return;
      }
      if (!CONTAINER_TAGS[tag]) return; // inline/unknown: skip, parent handles
    }
    var kids = node.childNodes;
    for (var i = 0; i < kids.length; i++) walk(kids[i], chapter);
  }

  function flatCursors() {
    /* map every block to (chapterIndex) and give each chapter a start index */
    var starts = [0], n = 0;
    for (var i = 0; i < chapters.length; i++) { n += chapters[i].blocks.length; starts.push(n); }
    return starts;
  }

  function makeEl(block) {
    var node;
    if (block.img) {
      node = document.createElement('img');
      node.style.display = 'block'; node.style.margin = '1.4em auto';
      node.alt = '';
      node.src = block.src;
    } else {
      node = document.createElement('p');
      node.textContent = block.text;
    }
    return node;
  }

  /* ── pagination (measured) ──────────────────────────────────────── */
  var pageCache = {};   // chapterIndex -> array of arrays of block indices
  var measure = null;

  /* Measure the space actually available between the sticky toolbar and the
     fixed pager instead of assuming a fixed chrome height. The old guess
     (viewport minus 148px) clipped text on phones — the toolbar wraps to
     three rows under 600px — and on short landscape screens it produced pages
     taller than the viewport, hiding whole paragraphs. */
  function viewportBox() {
    var bar = document.querySelector('.toolbar');
    var pager = el('pager');
    var cs = getComputedStyle(document.body);
    var top = bar ? bar.getBoundingClientRect().bottom : 0;
    var bottom = (pager && pager.style.display !== 'none')
      ? pager.getBoundingClientRect().top
      : window.innerHeight;
    var avail = bottom - top - 24;
    if (!(avail > 120)) avail = Math.max(200, window.innerHeight - 160);
    var width = el('page');
    var w = (width && width.clientWidth) || document.documentElement.clientWidth || window.innerWidth;
    var pad = parseFloat(cs.paddingLeft || 0) + parseFloat(cs.paddingRight || 0);
    return { h: Math.max(160, Math.floor(avail)), w: Math.max(240, Math.min(760, w - pad)) };
  }

  function buildPages(chapterIndex) {
    if (pageCache[chapterIndex]) return pageCache[chapterIndex];
    if (!measure) {
      measure = document.createElement('div');
      measure.className = 'text-body';
      measure.style.cssText = 'position:absolute;left:-10000px;top:0;visibility:hidden;';
      document.body.appendChild(measure);
    }
    var box = viewportBox();
    measure.style.width = box.w + 'px';
    measure.textContent = '';
    var blocks = chapters[chapterIndex].blocks;
    var pages = [], cur = [], curIds = [], maxH = box.h;
    for (var i = 0; i < blocks.length; i++) {
      var block = blocks[i];
      var node = makeEl(block);
      measure.appendChild(node);
      if (measure.scrollHeight > maxH && curIds.length) {
        pages.push(curIds); curIds = [];
        measure.textContent = '';
        measure.appendChild(makeEl(block));
        cur = [block];
      } else {
        cur.push(block);
      }
      curIds.push(i);
      if (i === blocks.length - 1 && curIds.length) pages.push(curIds);
    }
    if (!pages.length) pages = [[]];
    pageCache[chapterIndex] = pages;
    return pages;
  }

  function renderPageButtonless(pageEl, chapterIndex, pageIndex) {
    var pages = buildPages(chapterIndex);
    var blocks = chapters[chapterIndex].blocks;
    pageEl.textContent = '';
    if (pageIndex === 0 && chapters[chapterIndex].title) {
      var h = document.createElement('h1');
      h.className = 'chap-title';
      h.textContent = chapters[chapterIndex].title;
      pageEl.appendChild(h);
    }
    var idxs = pages[Math.min(pageIndex, pages.length - 1)] || [];
    idxs.forEach(function (bi) { pageEl.appendChild(makeEl(blocks[bi])); });
  }

  function renderPage() {
    if (!chapters.length) return;
    pageState.c = Math.min(pageState.c, chapters.length - 1);
    var pages = buildPages(pageState.c);
    pageState.j = Math.min(pageState.j, pages.length - 1);
    renderPageButtonless(el('page-body'), pageState.c, pageState.j);
    var ind = el('page-ind');
    ind.textContent = 'Page ' + (pageState.j + 1) + ' of ' + pages.length +
      (chapters.length > 1 ? ' · Chapter ' + (pageState.c + 1) + ' of ' + chapters.length : '');
    el('p-prev').disabled = pageState.c === 0 && pageState.j === 0;
    el('p-next').disabled = pageState.c === chapters.length - 1 && pageState.j === pages.length - 1;
    updateProgressBar();
    /* keep the current match marked after paging */
    if (find.q && find.q.trim().length >= 2) highlightOnPage();
  }

  function turn(delta) {
    if (mode !== 'pages' || !chapters.length) return;
    var pages = buildPages(pageState.c);
    var next = pageState.j + delta;
    if (next < 0) {
      if (pageState.c === 0) return;
      pageState.c--; pageState.j = buildPages(pageState.c).length - 1;
    } else if (next >= pages.length) {
      if (pageState.c === chapters.length - 1) return;
      pageState.c++; pageState.j = 0;
    } else {
      pageState.j = next;
    }
    renderPage();
    saveProgress();
  }

  /* ── scroll mode ────────────────────────────────────────────────── */
  var flatStarts = [];
  var flatIndex = 0;

  function resetScroll() {
    el('text-body').textContent = '';
    flatIndex = 0;
  }
  function buildFlat() {
    flatStarts = flatCursors();
  }
  function appendBlock(chapterIndex, bi) {
    var ch = chapters[chapterIndex];
    if (bi === 0) {
      var h = document.createElement('h1');
      h.className = 'chap-title';
      h.textContent = ch.title;
      el('text-body').appendChild(h);
    }
    el('text-body').appendChild(makeEl(ch.blocks[bi]));
  }
  function renderChunk() {
    var done = true;
    for (var c = 0; c < chapters.length; c++) {
      var start = flatStarts[c];
      var end = flatStarts[c + 1] || blockCount;
      if (flatIndex < end) {
        done = false;
        var from = Math.max(flatIndex, start);
        var to = Math.min(from + CHUNK, end);
        for (var bi = from; bi < to; bi++) appendBlock(c, bi - start);
        flatIndex = to;
        if (flatIndex >= blockCount) showScrollEnd();
        break;
      }
    }
    if (done) { flatIndex = blockCount; showScrollEnd(); }
  }
  function showScrollEnd() {
    var end = el('scroll-end');
    if (end) end.style.display = 'block';
  }
  function jumpScrollTo(chapterIndex) {
    resetScroll();
    el('scroll-end').style.display = 'none';
    flatIndex = flatStarts[chapterIndex];
    renderChunk(); renderChunk(); renderChunk();
    requestAnimationFrame(function () { window.scrollTo(0, 0); });
  }

  /* ── typography prefs ───────────────────────────────────────────── */
  var FONTS = ['serif', 'sans', 'mono'];
  var LEADINGS = ['tight', 'snug', 'relaxed'];
  var MEASURES = ['narrow', 'normal', 'wide'];
  var JUSTIFY = ['off', 'on'];

  function applyTypography() {
    var root = document.documentElement;
    [['font', FONT_KEY, FONTS, 'serif'],
     ['leading', LH_KEY, LEADINGS, 'snug'],
     ['measure', MEASURE_KEY, MEASURES, 'normal'],
     ['justify', JUSTIFY_KEY, JUSTIFY, 'off']].forEach(function (spec) {
      var attr = spec[0], key = spec[1], allowed = spec[2], fallback = spec[3];
      var v = localStorage.getItem(key);
      if (allowed.indexOf(v) < 0) v = fallback;
      root.setAttribute('data-' + attr, v);
      document.querySelectorAll('#type-pop [data-' + attr + ']').forEach(function (b) {
        var on = b.getAttribute('data-' + attr) === v;
        b.classList.toggle('active', on);
        b.setAttribute('aria-checked', String(on));
      });
    });
  }

  function saveTypography() {
    /* Any typographic change invalidates the measured page boxes: a wider
       measure or looser leading moves every break in the book. */
    pageCache = {};
    applyTypography();
    saveProgress();
    if (contentVisible) {
      if (mode === 'pages') renderPage();
      else renderChunk();
    }
  }

  /* ── find in book ───────────────────────────────────────────────── */
  /* Search the block model rather than the DOM. The DOM holds one page (or
     one rendered chunk in scroll mode), so a match in a later chapter would
     be invisible to it. */
  var find = { q: '', hits: [], at: -1 };

  function blockText(b) {
    if (b.text != null) return b.text;
    if (typeof b.html === 'string') {
      var d = document.createElement('div');
      d.innerHTML = b.html;
      return d.textContent || '';
    }
    return '';
  }

  function runFind(q) {
    find.q = q;
    find.hits = [];
    find.at = -1;
    var needle = q.trim().toLowerCase();
    if (needle.length >= 2) {
      for (var c = 0; c < chapters.length; c++) {
        var blocks = chapters[c].blocks;
        for (var i = 0; i < blocks.length; i++) {
          var hay = blockText(blocks[i]).toLowerCase();
          var from = 0, at;
          while ((at = hay.indexOf(needle, from)) !== -1) {
            find.hits.push({ c: c, i: i });
            from = at + needle.length;
            if (find.hits.length >= 2000) break;
          }
          if (find.hits.length >= 2000) break;
        }
        if (find.hits.length >= 2000) break;
      }
    }
    find.at = find.hits.length ? 0 : -1;
    paintFindCount();
    if (find.at >= 0) gotoHit(0);
  }

  function paintFindCount() {
    var n = el('find-count');
    if (!n) return;
    if (!find.q || find.q.trim().length < 2) { n.textContent = find.q ? 'Type 2+ letters' : ''; return; }
    n.textContent = find.hits.length
      ? (find.at + 1) + ' of ' + find.hits.length
      : 'No matches';
  }

  /* Page index that contains block `i` of chapter `c`, in the mode we are in.
     In scroll mode the block is simply appended. */
  function locate(c, i) {
    if (mode === 'pages') {
      var pages = buildPages(c);
      for (var j = 0; j < pages.length; j++) {
        if (pages[j].indexOf(i) !== -1) return j;
      }
      return 0;
    }
    return -1;
  }

  function gotoHit(k) {
    if (!find.hits.length) return;
    find.at = ((k % find.hits.length) + find.hits.length) % find.hits.length;
    var hit = find.hits[find.at];
    if (mode === 'pages') {
      pageState.c = hit.c;
      pageState.j = locate(hit.c, hit.i);
      renderPage();
    } else {
      jumpScrollTo(hit.c);
    }
    paintFindCount();
    highlightOnPage();
    saveProgress();
  }

  /* Mark matches inside the text currently on screen only. */
  function highlightOnPage() {
    var host = mode === 'pages' ? el('page-body') : el('text-body');
    if (!host) return;
    host.querySelectorAll('mark.find-hit').forEach(function (m) {
      var p = m.parentNode;
      while (m.firstChild) p.insertBefore(m.firstChild, m);
      p.removeChild(m);
      p.normalize();
    });
    var needle = find.q.trim();
    if (needle.length < 2) return;
    var lc = needle.toLowerCase();
    var scope = host.querySelectorAll('p, h1, h2, h3, li');
    for (var n = 0; n < scope.length; n++) {
      var node = scope[n];
      var walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, null);
      var texts = [], t;
      while ((t = walker.nextNode())) {
        if (t.nodeValue.toLowerCase().indexOf(lc) !== -1) texts.push(t);
      }
      texts.forEach(function (text) {
        var frag = document.createDocumentFragment();
        var rest = text.nodeValue, low = rest.toLowerCase(), at;
        while ((at = low.indexOf(lc)) !== -1) {
          if (at > 0) frag.appendChild(document.createTextNode(rest.slice(0, at)));
          var mk = document.createElement('mark');
          mk.className = 'find-hit';
          mk.textContent = rest.substr(at, needle.length);
          frag.appendChild(mk);
          rest = rest.slice(at + needle.length);
          low = rest.toLowerCase();
        }
        if (rest) frag.appendChild(document.createTextNode(rest));
        text.parentNode.replaceChild(frag, text);
      });
    }
    var marks = host.querySelectorAll('mark.find-hit');
    if (!marks.length) return;
    /* The current hit is whichever mark lies inside the visible page; with
       paging there is normally exactly one page of them. */
    var target = find.hits[find.at];
    var idx = 0, found = null;
    if (mode === 'pages' && target && target.c === pageState.c) {
      var pages = buildPages(pageState.c);
      var seen = 0;
      for (var p = 0; p <= pageState.j && p < pages.length; p++) seen += pages[p].length;
      for (var b = 0; b < pages[pageState.j].length; b++) {
        if (pages[pageState.j][b] === target.i) { found = marks[Math.min(idx, marks.length - 1)]; break; }
        idx++;
      }
    }
    (found || marks[0]).classList.add('is-current');
  }

  function openFind() {
    var bar = el('find-bar');
    if (!bar) return;
    bar.hidden = false;
    var input = el('find-input');
    if (input) { input.focus(); input.select(); }
  }
  function closeFind() {
    var bar = el('find-bar');
    if (bar) bar.hidden = true;
    find = { q: '', hits: [], at: -1 };
    var host = mode === 'pages' ? el('page-body') : el('text-body');
    if (host) {
      host.querySelectorAll('mark.find-hit').forEach(function (m) {
        var p = m.parentNode;
        while (m.firstChild) p.insertBefore(m.firstChild, m);
        p.removeChild(m); p.normalize();
      });
    }
    paintFindCount();
  }

  /* ── mode ───────────────────────────────────────────────────────── */
  var mode = 'pages';
  var pageState = { c: 0, j: 0 };
  function setMode(m, persist) {
    mode = m === 'scroll' ? 'scroll' : 'pages';
    document.body.classList.toggle('pages', mode === 'pages');
    el('pager').style.display = mode === 'pages' ? 'flex' : 'none';
    el('btt').style.display = 'none';
    document.querySelectorAll('.mode-btn').forEach(function (b) {
      b.classList.toggle('active', b.dataset.mode === mode);
    });
    if (persist !== false) localStorage.setItem(MODE_KEY, mode);
    if (contentVisible) {
      if (mode === 'pages') { buildPages(); renderPage(); }
      else { if (flatIndex === 0) { jumpScrollTo(0); } renderChunk(); }
      saveProgress();
    }
  }

  /* ── progress ───────────────────────────────────────────────────── */
  var savedAnchor = '';
  function overallPercent() {
    if (mode === 'pages') {
      var pages = buildPages(pageState.c);
      return Math.min(0.98, (pageState.c + (pageState.j + 1) / pages.length) / chapters.length);
    }
    var max = (document.body.scrollHeight || 1) - (window.innerHeight || 1);
    if (max <= 0) return 0;
    return Math.min(0.98, (scrollY || 0) / max);
  }
  function saveProgress() {
    var t = token(); if (!t) return;
    var anchor = mode === 'pages'
      ? 'c' + pageState.c + ':p:' + pageState.j
      : 'para-' + Math.round(overallPercent() * 1000);
    fetch('/api/v1/library/progress/' + ID, {
      method: 'PUT',
      headers: { 'Authorization': 'Bearer ' + t, 'Content-Type': 'application/json' },
      body: JSON.stringify({ percent: Math.round(overallPercent() * 100) / 100, position: anchor })
    }).catch(function () {});
  }
  function updateProgressBar() {
    var i = el('progressbar').firstElementChild;
    if (i) i.style.width = Math.round(overallPercent() * 100) + '%';
  }
  var _reporting = false;

  /* ── export / suppression ───────────────────────────────────────── */
  function suppressedMeta(meta) { return (meta.tags || []).some(function (t) { return /suppress|banned/i.test(t); }); }
  function ackKey() { return 'bb-spp-' + BID; }
  function isAcked() { return localStorage.getItem(ackKey()) === '1'; }

  function buildExportPop() {
    var dlBook = el('dl-book'), dlGate = el('dl-gate');
    if (suppressedMeta(meta) && !isAcked()) {
      dlBook.href = '#'; dlBook.style.display = 'none';
      dlGate.hidden = false;
      dlGate.addEventListener('click', function (e) {
        e.preventDefault();
        localStorage.setItem(ackKey(), '1');
        dlGate.hidden = true; dlBook.style.display = 'block';
        dlBook.href = '/api/v1/books/' + ID + '/download';
      });
    } else {
      dlBook.href = '/api/v1/books/' + ID + '/download';
      dlGate.hidden = true;
    }
  }
  function initExport() {
    el('export-btn').addEventListener('click', function () {
      buildExportPop();
      el('export-pop').hidden = !el('export-pop').hidden;
    });
    el('export-close').addEventListener('click', function () { el('export-pop').hidden = true; });
  }

  /* ── suppressed gate (for online reading) ───────────────────────── */
  function showSuppressedGate() {
    var gate = el('suppressed-gate');
    el('loading').style.display = 'none';
    gate.style.display = 'block';
    el('suppressed-acknowledge').addEventListener('click', function () {
      localStorage.setItem(ackKey(), '1');
      gate.style.display = 'none';
      start(false);
    }, { once: true });
  }

  /* ── toc ────────────────────────────────────────────────────────── */
  function buildToc() {
    var sel = el('toc-sel');
    sel.innerHTML = '';
    chapters.forEach(function (ch, i) {
      var o = document.createElement('option');
      o.value = i;
      o.textContent = ch.title || ('Chapter ' + (i + 1));
      sel.appendChild(o);
    });
    sel.disabled = false;
    sel.addEventListener('change', function () {
      var i = parseInt(sel.value, 10);
      if (isNaN(i)) return;
      if (mode === 'pages') { pageState.c = i; pageState.j = 0; renderPage(); saveProgress(); }
      else { jumpScrollTo(i); saveProgress(); }
      scrollTo(0, 0);
    });
  }

  /* ── resume ─────────────────────────────────────────────────────── */
  function applySavedAnchor() {
    var m = /^c(\d+):p:(\d+)$/.exec(savedAnchor);
    if (m) {
      setMode('pages', false);
      pageState.c = Math.min(parseInt(m[1], 10), Math.max(0, chapters.length - 1));
      /* The saved anchor carries the page within the chapter, but only the
         chapter index was ever restored — so resuming dropped the reader back
         to the start of the chapter they were part-way through. */
      var pages = buildPages(pageState.c);
      pageState.j = Math.min(parseInt(m[2], 10) || 0, pages.length - 1);
      renderPage();
      return;
    }
    if (mode === 'pages') renderPage();
    else { jumpScrollTo(0); }
  }

  /* ── boot ───────────────────────────────────────────────────────── */
  var meta = { title: '', author: '', tags: [] };
  var contentVisible = false;

  async function start(allowGate) {
    if (allowGate !== false && suppressedMeta(meta) && !isAcked()) { showSuppressedGate(); return; }
    var r = await fetch('/api/v1/books/' + ID + '/text');
    if (!r.ok) {
      var body = await r.json().catch(function () { return {}; });
      var f = failureFor(r, body);
      renderFailure(f[0], f[1]);
      return;
    }
    contentVisible = true;
    var html = await r.text();
    var doc = new DOMParser().parseFromString(html, 'text/html');
    chapters = [];
    blockCount = 0;
    walk(doc.body || doc, { title: '', blocks: [] });
    if (!chapters.length) chapters = [{ title: '', blocks: [{ text: (doc.body ? doc.body.textContent : '').trim() }] }];
    if (!chapters[0].title) chapters[0].title = 'Opening';
    blockCount = 0; chapters.forEach(function (c) { blockCount += c.blocks.length; });
    el('book-title').textContent = (meta.title || '') + (meta.author ? ' — ' + meta.author : '');
    buildFlat();
    buildToc();
    el('loading').style.display = 'none';
    el('content').style.display = 'block';
    // fetch any saved anchor + go
    if (token()) {
      try {
        var pr = await (await fetch('/api/v1/library/progress/' + ID, { headers: { 'Authorization': 'Bearer ' + token() } })).json();
        if (pr && pr.position) savedAnchor = pr.position;
      } catch (e) {}
    }
    applySavedAnchor();
    saveProgress();
  }

  function renderFailure(kind, detail) {
    el('loading').style.display = 'none';
    var box = el('err');
    box.style.display = 'block';
    box.textContent = '';

    var h = document.createElement('h2');
    h.className = 'err-title';
    var p = document.createElement('p');
    p.className = 'err-body';

    if (kind === 'withdrawn') {
      h.textContent = 'This edition is no longer available';
      p.textContent = detail ||
        'We withdrew this title from the catalogue, so it cannot be read here or downloaded. ' +
        'It is most often because the only free edition we could find is not a lawful public-domain copy.';
    } else if (kind === 'forbidden') {
      h.textContent = 'Not available to read';
      p.textContent = detail || 'This title is not cleared for reading on Babe’s Bookstore.';
    } else {
      h.textContent = 'We could not load the text';
      p.textContent = (detail || 'The edition could not be fetched from its source.') +
        ' You can try again, or download the file and open it in another reader.';
    }
    box.appendChild(h);
    box.appendChild(p);

    var actions = document.createElement('div');
    actions.className = 'err-actions';
    var back = document.createElement('a');
    back.className = 'btn';
    back.href = '#';
    back.textContent = '← Back to the catalogue';
    back.addEventListener('click', function (e) { e.preventDefault(); history.back(); });
    var search = document.createElement('a');
    search.className = 'btn ghost';
    search.href = '/search';
    search.textContent = 'Find another book';
    actions.appendChild(back);
    actions.appendChild(search);
    box.appendChild(actions);
  }

  /* Map an API failure onto a state a reader can act on. 410 means the title
     exists but was withdrawn; 403 means it is not cleared. */
  function failureFor(r, body) {
    if (r.status === 410) return ['withdrawn', body && body.detail];
    if (r.status === 403) return ['forbidden', body && body.detail];
    if (r.status === 404) return ['withdrawn', null];
    return ['error', (body && body.detail) || ('The source returned HTTP ' + r.status + '.')];
  }

  async function boot() {
    try {
      var mr = await fetch('/api/v1/books/' + ID);
      if (!mr.ok) {
        var body = await mr.json().catch(function () { return {}; });
        var f = failureFor(mr, body);
        renderFailure(f[0], f[1]);
        return;
      }
      var m = await mr.json();
      if (m.title) meta.title = m.title;
      if (m.author) meta.author = m.author;
      if (Array.isArray(m.tags)) meta.tags = m.tags;
      document.title = (meta.title || 'Read') + " — Babe's Bookstore";
      await start(true);
    } catch (e) {
      renderFailure('error', e.message || String(e));
    }
  }

  /* The document may already be parsed if this script is loaded late, in which
     case DOMContentLoaded has fired and the listener above never runs. */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { boot(); });
  } else {
    boot();
  }

  /* controls */
  function repaginate() { pageCache = {}; if (mode === 'pages') renderPage(); }

  document.querySelectorAll('.fs-btn button').forEach(function (b) {
    b.addEventListener('click', function () {
      localStorage.setItem(SCROLL_KEY, b.dataset.size);
      setPrefs();
      saveAccountPrefs();
      repaginate();
    });
  });
  var themeSel = el('theme');
  if (themeSel) {
    themeSel.addEventListener('change', function () {
      localStorage.setItem(THEME_KEY, this.value);
      setPrefs();
      saveAccountPrefs();
    });
  }
  document.querySelectorAll('.mode-btn').forEach(function (b) {
    b.addEventListener('click', function () {
      localStorage.setItem(MODE_SET_KEY, '1');
      setMode(b.dataset.mode, true);
    });
  });
  document.querySelector('[data-action="back"]').addEventListener('click', function (e) {
    e.preventDefault();
    history.back();
  });
  el('btt').addEventListener('click', function () { window.scrollTo({ top: 0, behavior: 'smooth' }); });
  el('p-prev').addEventListener('click', function () { turn(-1); });
  el('p-next').addEventListener('click', function () { turn(1); });

  /* typography popover */
  var typeBtn = el('type-btn'), typePop = el('type-pop');
  function toggleTypePop(force) {
    if (!typePop) return;
    var open = force != null ? force : typePop.hidden;
    typePop.hidden = !open;
    if (typeBtn) typeBtn.setAttribute('aria-expanded', String(open));
  }
  if (typeBtn) typeBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleTypePop(); });
  if (typePop) {
    typePop.addEventListener('click', function (e) { e.stopPropagation(); });
    [['font', FONT_KEY], ['leading', LH_KEY], ['measure', MEASURE_KEY], ['justify', JUSTIFY_KEY]]
      .forEach(function (pair) {
        typePop.querySelectorAll('[data-' + pair[0] + ']').forEach(function (b) {
          b.addEventListener('click', function () {
            localStorage.setItem(pair[1], b.getAttribute('data-' + pair[0]));
            saveTypography();
          });
        });
      });
    var reset = el('type-reset');
    if (reset) reset.addEventListener('click', function () {
      [FONT_KEY, LH_KEY, MEASURE_KEY, JUSTIFY_KEY].forEach(function (k) { localStorage.removeItem(k); });
      saveTypography();
    });
    var go = el('goto-go'), gotoInput = el('goto-page');
    function doGoto() {
      if (!gotoInput) return;
      var n = parseInt(gotoInput.value, 10);
      if (!(n > 0) || !chapters.length) return;
      if (mode !== 'pages') setMode('pages', true);
      pageState.j = Math.max(0, n - 1);
      renderPage();
    }
    if (go) go.addEventListener('click', doGoto);
    if (gotoInput) gotoInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') doGoto(); });
  }
  document.addEventListener('click', function (e) {
    if (typePop && !typePop.hidden && !typePop.contains(e.target) && e.target !== typeBtn) toggleTypePop(false);
  });

  /* find in book */
  var findBtn = el('find-btn'), findInput = el('find-input');
  if (findBtn) findBtn.addEventListener('click', function () { openFind(); });
  var findClose = el('find-close');
  if (findClose) findClose.addEventListener('click', closeFind);
  if (findInput) {
    var findTimer = null;
    findInput.addEventListener('input', function () {
      clearTimeout(findTimer);
      findTimer = setTimeout(function () { runFind(findInput.value); }, 180);
    });
    findInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); runFind(findInput.value); gotoHit(find.at + (e.shiftKey ? -1 : 1)); }
      if (e.key === 'Escape') { e.preventDefault(); closeFind(); }
    });
  }
  var findNext = el('find-next'), findPrev = el('find-prev');
  if (findNext) findNext.addEventListener('click', function () { gotoHit(find.at + 1); });
  if (findPrev) findPrev.addEventListener('click', function () { gotoHit(find.at - 1); });

  /* ── touch paging ───────────────────────────────────────────────── */
  /* Page turning was keyboard-only plus two fixed buttons, which left a
     phone user tapping a dead text column. Kindle-style: tap the outer
     thirds to turn, centre to open the chapter list, and support a
     horizontal swipe in either direction. */
  (function touchPaging() {
    var area = el('page');
    if (!area) return;
    var sx = 0, sy = 0, moved = false;

    function point(e) {
      var t = e.changedTouches && e.changedTouches[0];
      return t ? { x: t.clientX, y: t.clientY } : { x: e.clientX, y: e.clientY };
    }
    area.addEventListener('touchstart', function (e) {
      var p = point(e); sx = p.x; sy = p.y; moved = false;
    }, { passive: true });
    area.addEventListener('touchmove', function () { moved = true; }, { passive: true });
    area.addEventListener('touchend', function (e) {
      if (mode !== 'pages') return;
      var p = point(e), dx = p.x - sx, dy = p.y - sy;
      if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.4) {
        moved = true;
        turn(dx < 0 ? 1 : -1);
        return;
      }
      if (moved) return;                       // a scroll/drag, not a tap
      var rect = area.getBoundingClientRect();
      var frac = (p.x - rect.left) / (rect.width || 1);
      if (frac < 0.3) turn(-1);
      else if (frac > 0.7) turn(1);
      else { var sel = el('toc-sel'); if (sel) sel.focus(); }
    }, { passive: true });
  })();
  document.addEventListener('keydown', function (e) {
    /* Cmd/Ctrl+F belongs to the book, not the browser: the page holds one
       chapter at a time, so the browser's find can only ever see the current
       page and reports "no matches" for a word that is plainly in the text. */
    if ((e.metaKey || e.ctrlKey) && (e.key === 'f' || e.key === 'F')) {
      e.preventDefault();
      openFind();
      return;
    }
    if (e.key === 'Escape') {
      var bar = el('find-bar');
      if (bar && !bar.hidden) { closeFind(); return; }
      if (typePop && !typePop.hidden) { toggleTypePop(false); return; }
    }
    if (mode !== 'pages') return;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === ' ' || e.key === 'PageDown' || e.key === 'Enter') { e.preventDefault(); turn(1); }
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); turn(-1); }
    else if (e.key === 'Home') { pageState.c = 0; pageState.j = 0; renderPage(); saveProgress(); }
    else if (e.key === 'End') { pageState.c = chapters.length - 1; pageState.j = buildPages(pageState.c).length - 1; renderPage(); saveProgress(); }
  });

  var resizeTimer = null;
  function onViewportChange() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(repaginate, 220);
  }
  window.addEventListener('resize', onViewportChange);
  // Rotating a phone changes the toolbar height and the page box, so the
  // measured page breaks have to be rebuilt or text is clipped.
  window.addEventListener('orientationchange', onViewportChange);
  if (window.visualViewport) window.visualViewport.addEventListener('resize', onViewportChange);

  window.addEventListener('scroll', function () {
    var btt = el('btt');
    if (mode === 'pages') { if (btt) btt.style.display = 'none'; return; }
    if (btt) btt.style.display = scrollY > 600 ? 'block' : 'none';
    if (_reporting) return; _reporting = true;
    setTimeout(function () { _reporting = false; if (mode === 'scroll') { saveProgress(); updateProgressBar(); } }, 900);
    if (scrollY > (document.body.scrollHeight - window.innerHeight - 900)) { renderChunk(); }
  }, { passive: true });

  loadAccountPrefs();
  initExport();
})();