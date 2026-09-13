/* Babe's Bookstore — authors listing page. */
var curPage = 1;
function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] }) }
function stale(key, hours) {
  try { var raw = localStorage.getItem(key); if (!raw) return null; var o = JSON.parse(raw); if (Date.now() - o.t > hours * 3600000) return null; return o.d } catch (_) { return null }
}
async function fetchJSON(url, key, attempts) {
  var last;
  for (var i = 0; i < attempts; i++) {
    try {
      var r = await fetch(url); if (!r.ok) throw new Error(r.status);
      var d = await r.json(); if (key) try { localStorage.setItem(key, JSON.stringify({ t: Date.now(), d: d })) } catch (_) { }
      return d;
    } catch (e) { last = e; if (i < attempts - 1) await new Promise(function (R) { setTimeout(R, 400 * (i + 1)) }) }
  }
  throw last;
}
function card(a) {
  return '<a href="/authors/' + a.slug + '" class="block bg-white border rounded-2xl p-5 hover:border-stone-900 transition group">' +
    '<div class="w-14 h-14 rounded-full bg-stone-100 border grid place-items-center font-serif text-xl text-stone-700 mb-3">' + (a.name || '?').charAt(0).toUpperCase() + '</div>' +
    '<p class="font-serif font-semibold leading-tight group-hover:underline">' + a.name + '</p>' +
    '<p class="text-xs text-stone-500 mt-1">' + a.book_count + ' work' + (a.book_count === 1 ? '' : 's') + '</p>' +
    '</a>';
}
async function load(page) {
  if (page) curPage = page;
  var loading = document.getElementById('loading'), err = document.getElementById('error'), res = document.getElementById('results'), empty = document.getElementById('empty'), pag = document.getElementById('pagination');
  loading.classList.remove('hidden'); err.classList.add('hidden'); res.innerHTML = ''; empty.classList.add('hidden'); pag.innerHTML = '';
  var q = document.getElementById('q').value.trim();
  var params = new URLSearchParams(); params.set('page', curPage); params.set('page_size', '48'); if (q) params.set('q', q);
  var cacheKey = 'authors:' + params.toString();
  var d = null, cached = false;
  try {
    d = await fetchJSON('/api/v1/authors?' + params.toString(), cacheKey, 3);
  } catch (fe) { d = stale(cacheKey, 24); cached = !!d; }
  if (!d) throw new Error('network');
  try {
    var items = d.items || [];
    loading.classList.add('hidden');
    if (cached) { var st = document.getElementById('stale'); if (st) st.classList.remove('hidden'); }
    if (!items.length) { empty.classList.remove('hidden'); return }
    res.innerHTML = items.map(card).join('');
    var tp = Math.ceil(d.total / 48);
    if (tp > 1) { var h = '';
      h += '<button data-action="load" data-arg-1="' + (curPage - 1) + '" ' + (curPage <= 1 ? 'disabled' : '') + ' class="px-4 py-2 rounded-full border bg-white text-sm ' + (curPage <= 1 ? 'opacity-40' : '') + '">Previous</button>';
      for (var i = Math.max(1, curPage - 2); i <= Math.min(tp, curPage + 2); i++) h += '<button data-action="load" data-arg-1="' + i + '" class="w-10 h-10 rounded-full text-sm ' + (i === curPage ? 'bg-stone-900 text-white' : 'border bg-white') + '">' + i + '</button>';
      if (curPage + 2 < tp) h += '<span class="text-stone-400">…</span><button data-action="load" data-arg-1="' + tp + '" class="w-10 h-10 rounded-full border bg-white text-sm">' + tp + '</button>';
      h += '<button data-action="load" data-arg-1="' + (curPage + 1) + '" ' + (curPage >= tp ? 'disabled' : '') + ' class="px-4 py-2 rounded-full border bg-white text-sm ' + (curPage >= tp ? 'opacity-40' : '') + '">Next</button>';
      pag.innerHTML = h;
    }
  } catch (e) { loading.classList.add('hidden'); err.textContent = 'Could not load: ' + e.message; err.classList.remove('hidden') }
}
document.addEventListener('DOMContentLoaded', function () { load(1); });