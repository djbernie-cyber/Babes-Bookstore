/* Babe's Bookstore — Netflix-style personalized home feed.
   Renders the row-by-row home screen returned by /api/v1/home/feed:
   Continue reading, Picked for you (signed in), curated tag rows for
   everyone, and an optional admin-orchestrated seasonal band. */
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function cover(b) {
    if (b.cover_url) {
      return '<img src="' + esc(b.cover_url) + '" alt="Cover of ' + esc(b.title) + '" loading="lazy" class="w-full h-44 object-cover bg-[#1c1b1a]">';
    }
    // The card body already prints the title underneath, so this placeholder
    // must not repeat it -- showing the full title here made every uncovered
    // book print its name twice. Monogram + spine only.
    var initial = esc(String(b.title || '?').trim().charAt(0).toUpperCase());
    var author = esc(String(b.author || '').trim());
    return '<div class="w-full h-44 bg-[#1c1b1a] flex flex-col items-center justify-center gap-2 px-4">' +
      '<span class="font-serif text-5xl text-stone-200 leading-none">' + initial + '</span>' +
      '<span class="h-px w-8 bg-stone-700"></span>' +
      (author ? '<span class="text-[10px] tracking-wide uppercase font-medium text-stone-500 text-center line-clamp-2">' + author + '</span>' : '') +
      '</div>';
  }

  function card(b) {
    var resume = b.percent != null;
    var pct = resume ? Math.max(0, Math.min(100, Math.round((b.percent || 0) * 100))) : 0;
    return '<a href="/books/' + b.id + '" class="group flex-shrink-0 w-[158px] sm:w-[184px] overflow-hidden rounded-2xl border border-[#1f1f1f] bg-[#121212] text-[#fcfaf7] hover:border-stone-500 transition">' +
      cover(b) +
      '<div class="p-3">' +
        '<p class="font-serif font-semibold leading-tight line-clamp-2 text-sm group-hover:underline">' + esc(b.title) + '</p>' +
        '<p class="text-xs text-stone-400 mt-1 line-clamp-1">' + esc(b.author || 'Unknown author') + '</p>' +
        (resume
          ? '<div class="mt-2 h-1 bg-stone-700 rounded-full overflow-hidden"><div class="h-full bg-red-500" style="width:' + pct + '%"></div></div><p class="text-[10px] text-stone-400 mt-1">Read ' + pct + '% · resume</p>'
          : '<p class="text-[10px] uppercase tracking-wide text-stone-500 mt-2">' + esc(b.category || 'Free to read') + '</p>') +
      '</div></a>';
  }

  function seasonSection(s) {
    var href = s.href ? esc(s.href) : null;
    var inner = '<span class="text-2xl mr-3">' + esc(s.emoji) + '</span>' +
      '<p class="font-serif text-xl sm:text-2xl font-semibold">' + esc(s.title) + '</p>' +
      (s.body ? '<p class="text-sm text-stone-300 mt-1 max-w-xl">' + esc(s.body) + '</p>' : '');
    return '<div class="rounded-2xl border border-red-800/40 bg-[#161514] px-5 py-4 flex items-center gap-3">' +
      (href ? '<a href="' + href + '" class="flex items-center gap-3 hover:opacity-90">' + inner + '</a>' : inner) +
    '</div>';
  }

  function row(s) {
    if (s.key === 'season') {
      return '<div class="mb-8">' + seasonSection(s) + '</div>';
    }
    var label = esc(s.title);
    return '<section class="shelf mb-9" data-shelf>' +
      '<div class="flex items-end justify-between gap-4 mb-3">' +
        '<h2 class="font-serif text-lg sm:text-xl font-semibold tracking-[-0.01em]">' + label + '</h2>' +
        '<div class="flex items-center gap-3">' +
          '<span class="text-[11px] text-stone-500">' + s.items.length + (s.items.length === 1 ? ' title' : ' titles') + '</span>' +
          '<div class="shelf-arrows flex items-center gap-1.5">' +
            '<button type="button" class="shelf-arrow shelf-arrow-prev" data-dir="-1" aria-label="Scroll ' + label + ' left" aria-controls="">‹</button>' +
            '<button type="button" class="shelf-arrow shelf-arrow-next" data-dir="1" aria-label="Scroll ' + label + ' right" aria-controls="">›</button>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="shelf-track" tabindex="0" role="group" aria-label="' + label + ', horizontally scrollable">' +
        s.items.map(card).join('') +
      '</div>' +
      '<div class="shelf-progress mt-1" aria-hidden="true"><span></span></div>' +
    '</section>';
  }

  /* Arrows, edge fades and the progress hairline. Each row reports whether it
     actually overflows, so a shelf that fits on screen shows no arrows rather
     than two dead controls. */
  function wireShelves(mount) {
    var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    mount.querySelectorAll('[data-shelf]').forEach(function (shelf) {
      var track = shelf.querySelector('.shelf-track');
      var prev = shelf.querySelector('.shelf-arrow-prev');
      var next = shelf.querySelector('.shelf-arrow-next');
      var bar = shelf.querySelector('.shelf-progress span');
      if (!track) return;
      if (prev) prev.setAttribute('aria-controls', track.id || (track.id = 'shelf-' + Math.random().toString(36).slice(2, 9)));
      if (next) next.setAttribute('aria-controls', track.id);

      function overflow() {
        return track.scrollWidth - track.clientWidth > 4;
      }

      function sync() {
        var max = track.scrollWidth - track.clientWidth;
        var x = track.scrollLeft;
        var scrollable = max > 4;
        shelf.classList.toggle('is-end-start', x <= 1);
        shelf.classList.toggle('is-end-end', x >= max - 1);
        if (prev) prev.disabled = x <= 1;
        if (next) next.disabled = x >= max - 1;
        if (!scrollable) {
          shelf.classList.add('is-end-start', 'is-end-end');
          if (bar) bar.style.width = '100%';
        } else if (bar) {
          var visible = track.clientWidth / track.scrollWidth;
          bar.style.width = Math.max(12, visible * 100) + '%';
          bar.style.transform = 'translateX(' + (x / max) * (100 / Math.max(visible, 0.12) - 100) + '%)';
        }
      }

      function page(dir) {
        // Advance by a whole "page" of cards so the snap points stay meaningful.
        var card = track.querySelector(':scope > *');
        var step = card ? card.getBoundingClientRect().width + 16 : track.clientWidth * 0.8;
        var per = Math.max(1, Math.floor(track.clientWidth / step) - 1);
        track.scrollBy({ left: dir * step * per, behavior: reduced ? 'auto' : 'smooth' });
      }

      if (prev) prev.addEventListener('click', function () { page(-1); });
      if (next) next.addEventListener('click', function () { page(1); });

      track.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowRight') { page(1); e.preventDefault(); }
        else if (e.key === 'ArrowLeft') { page(-1); e.preventDefault(); }
        else if (e.key === 'Home') { track.scrollTo({ left: 0, behavior: reduced ? 'auto' : 'smooth' }); e.preventDefault(); }
        else if (e.key === 'End') { track.scrollTo({ left: track.scrollWidth, behavior: reduced ? 'auto' : 'smooth' }); e.preventDefault(); }
      });

      var raf = null;
      track.addEventListener('scroll', function () {
        if (raf) return;
        raf = requestAnimationFrame(function () { raf = null; sync(); });
      }, { passive: true });

      window.addEventListener('resize', sync);
      if (window.ResizeObserver) new ResizeObserver(sync).observe(track);
      sync();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var mount = document.getElementById('home-feed');
    if (!mount) return;
    api('/home/feed').then(function (data) {
      var sections = data.sections || [];
      if (!sections.length) return;
      var html = '';
      if (data.user && data.user.name) {
        html += '<div class="mb-6"><p class="text-[11px] tracking-[0.18em] uppercase font-semibold text-stone-500">Welcome back</p><h2 class="font-serif text-2xl font-semibold mt-1">Your library, latest first</h2></div>';
      }
      html += sections.map(row).join('');
      mount.innerHTML = html;
      mount.classList.remove('hidden');
      wireShelves(mount);
    }).catch(function () {
      mount.classList.add('hidden');
    });
  });
})();