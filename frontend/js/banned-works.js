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
        downloadCta(b, true) +
        '<a href="/books/' + b.id + '" class="text-xs font-medium px-3 py-2 rounded-full border border-stone-700 text-stone-300 hover:bg-stone-800">Preview</a>' +
      '</div>' +
    '</div>' +
  '</div>';
}

/* One row of the archive: a work we document but do not carry. */
function bArchiveRow(r) {
  const title = r.work_title || (r.book && r.book.title) || 'Untitled';
  const author = r.work_author || (r.book && r.book.author) || 'Unknown author';
  const country = r.country_name || r.country_code || '—';
  const status = (r.status || '').replace(/_/g, ' ').toLowerCase();
  const year = r.work_year || (r.book && r.book.publication_year) || '';
  const heading = r.book && r.book.id
    ? '<a href="/books/' + r.book.id + '" class="font-serif font-semibold text-stone-900 hover:underline">' + bEsc(title) + '</a>'
    : '<span class="font-serif font-semibold text-stone-900">' + bEsc(title) + '</span>';
  return '<div class="rounded-xl border border-stone-300 bg-white p-4">' +
    '<div class="flex flex-wrap items-baseline justify-between gap-2">' + heading +
      '<span class="text-[11px] uppercase tracking-wide font-semibold text-stone-500">' + bEsc(country) + '</span>' +
    '</div>' +
    '<p class="text-sm text-stone-700 mt-0.5">' + bEsc(author) + (year ? ' · ' + bEsc(year) : '') + '</p>' +
    '<p class="text-xs text-stone-600 mt-2 leading-5">' + bEsc(String(r.ban_reason || '').slice(0, 220)) + (String(r.ban_reason || '').length > 220 ? '…' : '') + '</p>' +
    '<p class="text-[11px] mt-2 font-medium ' + (r.book ? 'text-emerald-800' : 'text-stone-500') + '">' +
      bEsc(status) + (r.book ? ' · in our catalogue' : ' · not in catalogue') + '</p>' +
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
      if (meta) {
        /* d.total is the size of the whole tag (3,520 and counting), not the
           48 fetched. Saying "48 titles" made a large shelf look nearly empty. */
        const total = typeof d.total === 'number' ? d.total : items.length;
        meta.textContent = total > items.length
          ? 'Showing ' + items.length + ' of ' + total.toLocaleString() + ' titles · free to read and download'
          : items.length.toLocaleString() + ' title' + (items.length === 1 ? '' : 's') + ' · free to read and download';
        meta.classList.remove('hidden');
      }
      res.innerHTML = items.map(bCard).join('');
    } catch (e) {
      if (loading) loading.classList.add('hidden');
      if (err) { err.textContent = 'Could not load the suppressed-classics shelf: ' + e.message; err.classList.remove('hidden'); }
    }
  })();

  /* The archive. Records with no carried edition are the whole point: they are
     how a ban on an in-copyright African novel gets recorded at all. Records
     that do have a book are already on the shelf above, so they are skipped
     here to avoid printing the same title twice. */
  (async function () {
    const box = document.getElementById('archive-results');
    if (!box) return;
    const loading = document.getElementById('archive-loading');
    const empty = document.getElementById('archive-empty');
    const err = document.getElementById('archive-error');
    const meta = document.getElementById('archive-meta');
    try {
      const r = await fetch('/api/v1/banned/records');
      if (!r.ok) throw new Error(r.status);
      const d = await r.json();
      const all = d.items || [];
      const docs = all.filter(function (x) { return !x.book; })
                      .sort(function (a, b) {
                        return String(a.country_name || '').localeCompare(String(b.country_name || '')) ||
                               String(a.work_title || '').localeCompare(String(b.work_title || ''));
                      });
      loading.classList.add('hidden');
      if (!docs.length) {
        empty.innerHTML = 'No archive-only records yet. Every suppression we can currently document is for a title we carry, or the wider archive has not been loaded into this database yet — the reference timelines below are maintained by hand in the meantime.';
        empty.classList.remove('hidden');
        return;
      }
      if (meta) {
        const countries = {};
        docs.forEach(function (x) { countries[x.country_name || '—'] = 1; });
        meta.textContent = docs.length + ' works · ' + Object.keys(countries).length + ' countries';
        meta.classList.remove('hidden');
      }
      box.innerHTML = docs.map(bArchiveRow).join('');
    } catch (e) {
      loading.classList.add('hidden');
      if (err) { err.textContent = 'Could not load the suppression archive: ' + e.message; err.classList.remove('hidden'); }
    }
  })();
});
