/* Babe's Bookstore — African Literature category page. */
function coverHtml(b) {
  if (b.cover_path && /^https?:\/\//.test(b.cover_path)) {
    return `<img src="${b.cover_path}" alt="${String(b.title).replace(/"/g, '&quot;')}" class="w-full h-56 object-cover bg-[#f6f1e7]" loading="lazy">`;
  }
  const letter = String(b.title || '?').charAt(0).toUpperCase();
  return `<div class="w-full h-56 bg-[#f6f1e7] border-b flex flex-col items-center justify-center p-4"><span class="font-serif text-5xl text-[#0b0b0c]">${letter}</span><span class="text-[11px] tracking-wide uppercase font-medium text-[#8a8683] mt-2 text-center line-clamp-2">${b.title}</span></div>`;
}
function card(b) {
  const isColonial = Array.isArray(b.tags) && b.tags.indexOf('Colonial Sauce') !== -1;
  const isContinent = Array.isArray(b.tags) && b.tags.indexOf('African Author') !== -1;
  const badge = isColonial
    ? '<span class="text-[11px] px-2 py-0.5 rounded-full bg-red-100 text-red-800 border border-red-200 font-medium" title="Colonial-era / coloniser framing">Colonial Sauce</span>'
    : (isContinent
      ? '<span class="text-[11px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 font-medium">African Author</span>'
      : '<span class="text-[11px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200 font-medium">Diaspora</span>');
  return `<div class="book-card group overflow-hidden flex flex-col">
    <a href="/books/${b.id}" class="block">${coverHtml(b)}</a>
    <div class="p-4 flex-1 flex flex-col">
      <div class="flex items-start justify-between gap-2"><a href="/books/${b.id}" class="font-serif font-semibold leading-tight line-clamp-2 hover:underline">${b.title}</a>${badge}</div>
      <p class="text-sm text-[#57534e] mt-1">${b.author || 'Unknown author'}</p>
      <div class="flex flex-wrap gap-1.5 mt-2">${b.category ? `<span class="text-[11px] px-2 py-1 rounded-full bg-white border text-[#57534e]">${b.category}</span>` : ''}${b.publication_year ? `<span class="text-xs text-[#8a8683]">${b.publication_year}</span>` : ''}</div>
      <div class="mt-3 flex gap-2">
        <a href="/api/v1/books/${b.id}/download" class="flex-1 text-center text-xs font-semibold px-3 py-2 rounded-full bg-[#0b0b0c] text-white hover:bg-black">Free download</a>
        <a href="/books/${b.id}" class="text-xs font-medium px-3 py-2 rounded-full border bg-white hover:bg-[#fcfaf7]">Preview</a>
      </div>
    </div>
  </div>`;
}
let curPage = 1;
function colonialHidden() {
  var cb = document.getElementById('hide-colonial');
  return !cb || cb.checked;
}
async function load(page) {
  if (page) curPage = page;
  const loading = document.getElementById('loading'), err = document.getElementById('error'), res = document.getElementById('results'), empty = document.getElementById('empty'), meta = document.getElementById('meta'), pag = document.getElementById('pagination');
  loading.classList.remove('hidden'); err.classList.add('hidden'); res.innerHTML = ""; empty.classList.add('hidden'); meta.classList.add('hidden'); pag.innerHTML = "";
  const hideColonial = colonialHidden();
  const params = new URLSearchParams(); params.set('tag', 'African Literature'); if (hideColonial) params.set('exclude_tag', 'Colonial Sauce'); params.set('page', curPage); params.set('page_size', '24');
  try {
    const r = await fetch(`/api/v1/books?${params.toString()}`); if (!r.ok) throw new Error(r.status);
    const d = await r.json(); const items = d.items || []; const total = d.total || 0;
    loading.classList.add('hidden');
    if (!items.length) { empty.classList.remove('hidden'); return }
    meta.textContent = hideColonial
      ? `${total.toLocaleString()} African titles shown · Colonial Sauce works hidden`
      : `${total.toLocaleString()} African titles, including Colonial Sauce (coloniser) works`;
    meta.classList.remove('hidden');
    res.innerHTML = items.map(card).join('');
    const tp = Math.ceil(total / 24);
    if (tp > 1) { let h = ""; h += `<button data-action="load" data-arg-1="${curPage - 1}" ${curPage <= 1 ? 'disabled' : ''} class="px-4 py-2 rounded-full border bg-white text-sm ${curPage <= 1 ? 'opacity-40' : ''}">Previous</button>`;
      for (let i = Math.max(1, curPage - 2); i <= Math.min(tp, curPage + 2); i++) h += `<button data-action="load" data-arg-1="${i}" class="w-10 h-10 rounded-full text-sm ${i === curPage ? 'bg-stone-900 text-white' : 'border bg-white'}">${i}</button>`;
      if (curPage + 2 < tp) h += `<span class="text-stone-400">…</span><button data-action="load" data-arg-1="${tp}" class="w-10 h-10 rounded-full border bg-white text-sm">${tp}</button>`;
      h += `<button data-action="load" data-arg-1="${curPage + 1}" ${curPage >= tp ? 'disabled' : ''} class="px-4 py-2 rounded-full border bg-white text-sm ${curPage >= tp ? 'opacity-40' : ''}">Next</button>`; pag.innerHTML = h;
    }
  } catch (e) { loading.classList.add('hidden'); err.textContent = "Could not load: " + e.message; err.classList.remove('hidden') }
}
function hideColonial() { load(1); }
document.addEventListener('DOMContentLoaded', () => load(1));