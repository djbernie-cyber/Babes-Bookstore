/* Babe's Bookstore — author detail page. */
function slugFromUrl() {
  var path = location.pathname.replace(/^\/authors\//, '').replace(/\/$/, '');
  return decodeURIComponent(path);
}
function titleFromSlug(s) {
  return s.split('-').map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1) }).join(' ');
}
var slug = slugFromUrl();
var authorName = titleFromSlug(slug);
document.getElementById('author-title').textContent = authorName;
document.getElementById('author-desc').textContent = 'Browse the works of ' + authorName + ' available in the public-domain library.';
document.title = authorName + " — Babe's Bookstore";

function coverHtml(b) {
  if (b.cover_path && /^https?:\/\//.test(b.cover_path)) {
    return `<img src="${b.cover_path}" alt="${String(b.title).replace(/"/g, '&quot;')}" class="w-full h-56 object-cover bg-[#f6f1e7]" loading="lazy">`;
  }
  var letter = String(b.title || '?').charAt(0).toUpperCase();
  return `<div class="w-full h-56 bg-[#f6f1e7] border-b flex flex-col items-center justify-center p-4"><span class="font-serif text-5xl text-[#0b0b0c]">${letter}</span><span class="text-[11px] tracking-wide uppercase font-medium text-[#8a8683] mt-2 text-center line-clamp-2">${esc(b.title)}</span></div>`;
}
function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function card(b) {
  return '<div class="book-card group overflow-hidden flex flex-col">' +
    '<a href="/books/' + b.id + '" class="block">' + coverHtml(b) + '</a>' +
    '<div class="p-4 flex-1 flex flex-col">' +
    '<a href="/books/' + b.id + '" class="font-serif font-semibold leading-tight line-clamp-2 hover:underline">' + esc(b.title) + '</a>' +
    '<p class="text-sm text-[#57534e] mt-1">' + esc(b.author) + '</p>' +
    '<div class="flex flex-wrap gap-1.5 mt-2">' + (b.category ? '<span class="text-[11px] px-2 py-1 rounded-full bg-white border text-[#57534e]">' + esc(b.category) + '</span>' : '') + (b.publication_year ? '<span class="text-xs text-[#8a8683]">' + b.publication_year + '</span>' : '') + '</div>' +
    '<div class="mt-3 flex gap-2">' +
    '<a href="/api/v1/books/' + b.id + '/download" class="flex-1 text-center text-xs font-semibold px-3 py-2 rounded-full bg-[#0b0b0c] text-white hover:bg-black">Free download</a>' +
    '<a href="/books/' + b.id + '" class="text-xs font-medium px-3 py-2 rounded-full border bg-white hover:bg-[#fcfaf7]">Preview</a>' +
    '</div>' +
    '</div>' +
    '</div>';
}
var curPage = 1, activeTag = null, taggedTotal = null;
async function tagTotal() {
  try {
    var r = await fetch('/api/v1/authors/' + slug + '?page_size=1&tag=' + encodeURIComponent('African Literature'));
    if (r.ok) { var d = await r.json(); taggedTotal = d.total; renderTagToggle(); }
  } catch (e) { }
}
function renderTagToggle() {
  var el = document.getElementById('african-toggle'); if (!el) return;
  if (typeof taggedTotal === 'number' && taggedTotal > 0) { el.style.display = 'inline-flex'; }
}
async function load(page) {
  if (page) curPage = page;
  var loading = document.getElementById('loading'), err = document.getElementById('error'), res = document.getElementById('results'), empty = document.getElementById('empty'), meta = document.getElementById('meta'), pag = document.getElementById('pagination');
  loading.classList.remove('hidden'); err.classList.add('hidden'); res.innerHTML = ''; empty.classList.add('hidden'); meta.classList.add('hidden'); pag.innerHTML = '';
  var params = new URLSearchParams(); params.set('page', curPage); params.set('page_size', '24'); if (activeTag) params.set('tag', activeTag);
  try {
    var r = await fetch('/api/v1/authors/' + slug + '?' + params.toString()); if (!r.ok) throw new Error(r.status);
    var d = await r.json(); var items = d.items || []; var total = d.total || 0;
    loading.classList.add('hidden');
    if (!items.length) { empty.classList.remove('hidden'); return }
    meta.textContent = (activeTag ? 'African works' : 'All works') + ' by ' + authorName + ' · ' + total + ' book' + (total === 1 ? '' : 's'); meta.classList.remove('hidden');
    res.innerHTML = items.map(card).join('');
    var tp = Math.ceil(total / 24);
    if (tp > 1) { var h = '';
      h += '<button data-action="load" data-arg-1="' + (curPage - 1) + '" ' + (curPage <= 1 ? 'disabled' : '') + ' class="px-4 py-2 rounded-full border bg-white text-sm ' + (curPage <= 1 ? 'opacity-40' : '') + '">Previous</button>';
      for (var i = Math.max(1, curPage - 2); i <= Math.min(tp, curPage + 2); i++) h += '<button data-action="load" data-arg-1="' + i + '" class="w-10 h-10 rounded-full text-sm ' + (i === curPage ? 'bg-stone-900 text-white' : 'border bg-white') + '">' + i + '</button>';
      if (curPage + 2 < tp) h += '<span class="text-stone-400">…</span><button data-action="load" data-arg-1="' + tp + '" class="w-10 h-10 rounded-full border bg-white text-sm">' + tp + '</button>';
      h += '<button data-action="load" data-arg-1="' + (curPage + 1) + '" ' + (curPage >= tp ? 'disabled' : '') + ' class="px-4 py-2 rounded-full border bg-white text-sm ' + (curPage >= tp ? 'opacity-40' : '') + '">Next</button>';
      pag.innerHTML = h;
    }
  } catch (e) { loading.classList.add('hidden'); err.textContent = 'Could not load: ' + e.message; err.classList.remove('hidden') }
}
function toggleAfrican() {
  activeTag = activeTag ? null : 'African Literature';
  document.getElementById('african-toggle').classList.toggle('active');
  curPage = 1; load(1); scrollTo({ top: 0, behavior: 'smooth' });
}
document.addEventListener('DOMContentLoaded', function () { load(1); tagTotal(); });