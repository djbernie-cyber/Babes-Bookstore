/* Babe's Bookstore — banned works page. */
function bEsc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function bCover(b) {
  if (b.cover_path && /^https?:\/\//.test(b.cover_path)) {
    return '<img src="' + bEsc(b.cover_path) + '" alt="' + bEsc(b.title) + '" class="w-full h-40 object-cover bg-[#1c1b1a]" loading="lazy">';
  }
  return '<div class="w-full h-40 bg-[#1c1b1a] border-b flex flex-col items-center justify-center p-3"><span class="font-serif text-4xl text-stone-200">' + bEsc(String(b.title || '?').charAt(0).toUpperCase()) + '</span><span class="text-[10px] tracking-wide uppercase font-medium text-stone-500 mt-2 text-center line-clamp-2">' + bEsc(b.title) + '</span></div>';
}
function bCard(b) {
  const banned = Array.isArray(b.tags) && b.tags.some(function (t) { return t === 'Suppressed Classics' || t === 'Revolutionary'; });
  const badge = banned
    ? '<span class="text-[10px] px-2 py-0.5 rounded-full bg-red-900/60 text-red-200 border border-red-700/50 font-semibold" title="Historically banned, burned or suppressed">Suppressed</span>'
    : '';
  return '<div class="book-card overflow-hidden flex flex-col bg-stone-900 rounded-2xl border border-stone-800 hover:border-stone-600 transition">' +
    '<a href="/books/' + b.id + '" class="block">' + bCover(b) + '</a>' +
    '<div class="p-4 flex-1 flex flex-col">' +
      '<div class="flex items-start justify-between gap-2"><a href="/books/' + b.id + '" class="font-serif font-semibold leading-tight line-clamp-2 text-stone-100 hover:underline">' + bEsc(b.title) + '</a>' + badge + '</div>' +
      '<p class="text-sm text-stone-400 mt-1">' + bEsc(b.author || 'Unknown author') + '</p>' +
      '<div class="flex flex-wrap gap-1.5 mt-2">' + (b.category ? '<span class="text-[10px] px-2 py-1 rounded-full bg-stone-800 border border-stone-700 text-stone-300">' + bEsc(b.category) + '</span>' : '') + (b.publication_year ? '<span class="text-xs text-stone-500">' + bEsc(b.publication_year) + '</span>' : '') + '</div>' +
      '<div class="mt-auto pt-3 flex gap-2">' +
        '<a href="/api/v1/books/' + b.id + '/download" class="flex-1 text-center text-xs font-semibold px-3 py-2 rounded-full bg-stone-100 text-stone-900 hover:bg-white">Free download</a>' +
        '<a href="/books/' + b.id + '" class="text-xs font-medium px-3 py-2 rounded-full border border-stone-700 text-stone-300 hover:bg-stone-800">Preview</a>' +
      '</div>' +
    '</div>' +
  '</div>';
}
document.addEventListener('DOMContentLoaded', function () {
  const sections = document.querySelectorAll('details');
  sections.forEach(function (s) { s.addEventListener('toggle', function () { const summary = s.querySelector('summary'); summary.classList.toggle('text-stone-200', s.open); }); });

  const loading = document.getElementById('banned-loading'), err = document.getElementById('banned-error'), res = document.getElementById('banned-results'), empty = document.getElementById('banned-empty'), meta = document.getElementById('banned-meta');
  if (!res) return;
  const params = new URLSearchParams();
  params.set('tag', 'Suppressed Classics');
  params.set('page', '1');
  params.set('page_size', '48');
  (async function () {
    try {
      const r = await fetch('/api/v1/books?' + params.toString());
      if (!r.ok) throw new Error(r.status);
      const d = await r.json();
      const items = d.items || [];
      if (loading) loading.classList.add('hidden');
      if (!items.length) { if (empty) empty.classList.remove('hidden'); return; }
      if (meta) { meta.textContent = items.length.toLocaleString() + ' title' + (items.length === 1 ? '' : 's') + ' · free to read and download'; meta.classList.remove('hidden'); }
      res.innerHTML = items.map(bCard).join('');
    } catch (e) {
      if (loading) loading.classList.add('hidden');
      if (err) { err.textContent = 'Could not load the suppressed-classics shelf: ' + e.message; err.classList.remove('hidden'); }
    }
  })();
});