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
      return '<img src="' + esc(b.cover_url) + '" alt="' + esc(b.title) + '" loading="lazy" class="w-full h-44 object-cover bg-[#1c1b1a]">';
    }
    return '<div class="w-full h-44 bg-[#1c1b1a] list-none flex flex-col items-center justify-center p-3"><span class="font-serif text-5xl text-stone-200">' + esc(String(b.title || '?').charAt(0).toUpperCase()) + '</span><span class="text-[10px] tracking-wide uppercase font-medium text-stone-500 mt-2 text-center line-clamp-2">' + esc(b.title) + '</span></div>';
  }

  function card(b) {
    var resume = b.percent != null;
    var pct = resume ? Math.max(0, Math.min(100, Math.round((b.percent || 0) * 100))) : 0;
    return '<a href="/books/' + b.id + '" class="group flex-shrink-0 w-[168px] sm:w-[188px] overflow-hidden rounded-2xl border border-[#1f1f1f] bg-[#121212] text-[#fcfaf7] hover:border-stone-500 transition">' +
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
    return '<section class="mb-9">' +
      '<div class="flex items-end justify-between gap-4 mb-3">' +
        '<h2 class="font-serif text-lg sm:text-xl font-semibold tracking-[-0.01em]">' + esc(s.title) + '</h2>' +
        (s.items.length ? '<span class="text-[11px] text-stone-500">' + s.items.length + (s.items.length === 1 ? ' title' : ' titles') + '</span>' : '') +
      '</div>' +
      '<div class="flex gap-4 overflow-x-auto pb-2 scrollbar-thin">' + s.items.map(card).join('') + '</div>' +
    '</section>';
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
    }).catch(function () {
      mount.classList.add('hidden');
    });
  });
})();