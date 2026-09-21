/* Babe's Bookstore — library search page. */
function coverHtml(b) {
  if (b.cover_path && /^https?:\/\//.test(b.cover_path)) {
    return `<img src="${b.cover_path}" alt="${b.title.replace(/"/g, '&quot;')}" class="w-full h-56 object-cover bg-[#f6f1e7]" loading="lazy">`;
  }
  const letter = (b.title || '?').charAt(0).toUpperCase();
  return `<div class="w-full h-56 bg-[#f6f1e7] border-b flex flex-col items-center justify-center p-4"><span class="font-serif text-5xl text-[#0b0b0c]">${letter}</span><span class="text-[11px] tracking-wide uppercase font-medium text-[#8a8683] mt-2 text-center line-clamp-2">${b.title}</span></div>`;
}
function card(b) {
  return `<div class="book-card group overflow-hidden flex flex-col">
    <a href="/books/${b.id}" class="block">${coverHtml(b)}</a>
    <div class="p-4 flex-1 flex flex-col">
      <a href="/books/${b.id}" class="font-serif font-semibold leading-tight line-clamp-2 hover:underline">${b.title}</a>
      <p class="text-sm text-[#57534e] mt-1">${b.author || 'Unknown author'}</p>
      <div class="flex flex-wrap gap-1.5 mt-2">${b.category ? `<span class="text-[11px] px-2 py-1 rounded-full bg-white border text-[#57534e]">${b.category}</span>` : ''}${b.publication_year ? `<span class="text-xs text-[#8a8683]">${b.publication_year}</span>` : ''}</div>
      <div class="mt-3 flex gap-2">
        <a href="/api/v1/books/${b.id}/download" class="flex-1 text-center text-xs font-semibold px-3 py-2 rounded-full bg-[#0b0b0c] text-white hover:bg-black">Free download</a>
        <a href="/books/${b.id}" class="text-xs font-medium px-3 py-2 rounded-full border bg-white hover:bg-[#fcfaf7]">Preview</a>
      </div>
      <p class="text-[11px] text-[#8a8683] mt-2">Free individual book · Bundles £10</p>
    </div>
  </div>`;
}
let curPage = 1, lastQ = "", lastCat = "";
// Category dropdown entries that are shelves backed by a book *tag* rather
// than the subject ``category`` column.
const TAG_OPS = { 'African Literature': 'African Literature', 'Revolutionary': 'Revolutionary', 'Socialist Theory': 'Socialist Theory', 'Banned & Suppressed': 'Suppressed Classics' };
async function search(p) {
  if (p) curPage = p;
  const q = document.getElementById('q').value.trim();
  const cat = document.getElementById('category').value;
  lastQ = q; lastCat = cat;
  const loading = document.getElementById('loading'), err = document.getElementById('error'), res = document.getElementById('results'), empty = document.getElementById('empty'), meta = document.getElementById('meta'), pag = document.getElementById('pagination');
  loading.classList.remove('hidden'); err.classList.add('hidden'); res.innerHTML = ""; empty.classList.add('hidden'); meta.classList.add('hidden'); pag.innerHTML = "";
  const params = new URLSearchParams(); if (q) params.set('search', q); if (cat) params.set(TAG_OPS[cat] ? 'tag' : 'category', TAG_OPS[cat] || cat); params.set('page', curPage); params.set('page_size', '24');
  try {
    const r = await fetch(`/api/v1/books?${params.toString()}`); if (!r.ok) throw new Error(r.status);
    const d = await r.json(); const items = d.items || []; const total = d.total || 0;
    loading.classList.add('hidden');
    if (!items.length) { empty.classList.remove('hidden'); return }
    meta.textContent = `Showing ${items.length} of ${total.toLocaleString()}${q ? ` for “${q}”` : ''}${cat ? ` in ${cat}` : ''}`; meta.classList.remove('hidden');
    res.innerHTML = items.map(card).join('');
    const tp = Math.ceil(total / 24);
    if (tp > 1) { let h = ""; h += `<button data-action="search" data-arg-1="${curPage - 1}" ${curPage <= 1 ? 'disabled' : ''} class="px-4 py-2 rounded-full border bg-white text-sm ${curPage <= 1 ? 'opacity-40' : ''}">Previous</button>`;
      for (let i = Math.max(1, curPage - 2); i <= Math.min(tp, curPage + 2); i++) h += `<button data-action="search" data-arg-1="${i}" class="w-10 h-10 rounded-full text-sm ${i === curPage ? 'bg-stone-900 text-white' : 'border bg-white'}">${i}</button>`;
      if (curPage + 2 < tp) h += `<span class="text-stone-400">…</span><button data-action="search" data-arg-1="${tp}" class="w-10 h-10 rounded-full border bg-white text-sm">${tp}</button>`;
      h += `<button data-action="search" data-arg-1="${curPage + 1}" ${curPage >= tp ? 'disabled' : ''} class="px-4 py-2 rounded-full border bg-white text-sm ${curPage >= tp ? 'opacity-40' : ''}">Next</button>`; pag.innerHTML = h;
    }
    const u = new URL(location.href); if (q) u.searchParams.set('q', q); else u.searchParams.delete('q'); if (cat) u.searchParams.set('category', cat); else u.searchParams.delete('category'); history.replaceState(null, "", u);
  } catch (e) { loading.classList.add('hidden'); err.textContent = "Search failed: " + e.message; err.classList.remove('hidden') }
}
document.addEventListener('DOMContentLoaded', () => {
  const sp = new URLSearchParams(location.search); const q = sp.get('q') || ""; const c = sp.get('category') || "";
  document.getElementById('q').value = q; document.getElementById('category').value = c;
  search(1);
  document.getElementById('q').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); search(1) } });
  let debT = null;
  document.getElementById('q').addEventListener('input', function () { clearTimeout(debT); debT = setTimeout(function () { search(1); }, 400); });
});