/* Babe's Bookstore — African authors page. */
function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
var curPage = 1;
function authorCard(a) {
  return '<a href="/authors/' + a.slug + '" class="block bg-white border rounded-2xl p-5 hover:border-stone-900 transition group">' +
    '<div class="w-14 h-14 rounded-full bg-[#f6efe1] border grid place-items-center font-serif text-xl text-stone-800 mb-3">' + esc((a.name || '?').charAt(0).toUpperCase()) + '</div>' +
    '<p class="font-serif font-semibold leading-tight group-hover:underline">' + esc(a.name) + '</p>' +
    '<p class="text-xs text-stone-500 mt-1">' + a.book_count + ' work' + (a.book_count === 1 ? '' : 's') + '</p>' +
    (a.banned ? '<p class="text-[11px] font-semibold text-red-700 mt-2 inline-block bg-red-50 border border-red-200 rounded-full px-2 py-0.5">Banned / imprisoned writer</p>' : '') +
    '</a>';
}
function featuredCard(a) {
  var initials = esc((a.name || '?').split(/\s+/).map(function (w) { return w.charAt(0) }).slice(0, 2).join('').toUpperCase());
  return '<div class="bg-white border rounded-2xl p-6 flex flex-col">' +
    '<div class="w-16 h-16 rounded-full bg-gradient-to-br from-stone-800 to-stone-600 text-white grid place-items-center font-serif text-xl mb-4">' + initials + '</div>' +
    '<p class="font-serif text-xl font-bold leading-tight">' + esc(a.name) + '</p>' +
    '<p class="text-sm text-stone-500 mt-1">' + a.book_count + ' work' + (a.book_count === 1 ? '' : 's') + ' in the library</p>' +
    (a.banned ? '<p class="text-[11px] font-semibold text-red-700 mt-2 inline-block bg-red-50 border border-red-200 rounded-full px-2 py-0.5">Banned / imprisoned writer</p>' : '') +
    '<div class="mt-4 pt-4 border-t"><a href="/authors/' + a.slug + '" class="text-sm font-semibold text-stone-900 hover:underline">Browse catalogue →</a></div>' +
    '</div>';
}
async function fetchJSON(url, cacheKey, attempts) {
  attempts = attempts || 3;
  for (var i = 0; i < attempts; i++) {
    try {
      var r = await fetch(url); if (!r.ok) throw new Error(r.status);
      var d = await r.json(); try { localStorage.setItem(cacheKey, JSON.stringify({ t: Date.now(), d: d })) } catch (_) { }
      return d;
    } catch (e) {
      if (i === attempts - 1) throw e;
      await new Promise(function (res) { setTimeout(res, 400 * (i + 1)) });
    }
  }
}
function stale(cacheKey, hours) {
  try {
    var raw = localStorage.getItem(cacheKey); if (!raw) return null;
    var o = JSON.parse(raw); if (Date.now() - o.t > hours * 3600 * 1000) return null;
    return o.d;
  } catch (_) { return null }
}
async function load(page) {
  if (page) curPage = page;
  var loading = document.getElementById('loading'), err = document.getElementById('error'), grid = document.getElementById('grid'), empty = document.getElementById('empty'), pag = document.getElementById('pagination'), meta = document.getElementById('meta');
  loading.classList.remove('hidden'); err.classList.add('hidden'); grid.innerHTML = ''; empty.classList.add('hidden'); pag.innerHTML = ''; meta.classList.add('hidden');
  var q = document.getElementById('q').value.trim();
  var params = new URLSearchParams(); params.set('page', curPage); params.set('page_size', '48'); if (q) params.set('q', q);
  var cacheKey = 'african-authors:' + params.toString();
  var d = null, cached = false;
  try {
    d = await fetchJSON('/api/v1/authors/african?' + params.toString(), cacheKey, 3);
  } catch (fe) {
    d = stale(cacheKey, 24); cached = !!d;
  }
  if (!d) throw new Error('network');
  var items = d.items || [];
  try {
    loading.classList.add('hidden');
    if (cached) { var st = document.getElementById('stale'); if (st) st.classList.remove('hidden'); }
    if (typeof d.total_african_books === 'number') { var htc = document.getElementById('hero-total'); if (htc) { var cc = (typeof d.total_continent_books === 'number') ? (' — ' + d.total_continent_books.toLocaleString() + ' by Black African (continent) authors.') : '.'; htc.textContent = 'Now spanning ' + d.total_african_books.toLocaleString() + ' African works' + cc; } }
    if (q) { meta.textContent = items.length + ' African author' + (items.length === 1 ? '' : 's') + ' matching “' + esc(q) + '”'; meta.classList.remove('hidden'); }
    if (!items.length) { empty.classList.remove('hidden'); return }
    grid.innerHTML = items.map(authorCard).join('');
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
async function loadFeatured() {
  var el = document.getElementById('featured'); if (!el) return;
  try {
    var r = await fetch('/api/v1/authors/african?page_size=5'); if (!r.ok) return;
    var d = await r.json(); var ft = d.featured || []; el.innerHTML = ft.map(featuredCard).join('') || '';
  } catch (e) { }
}
document.addEventListener('DOMContentLoaded', function () { loadFeatured(); load(1); });