/* Babe's Bookstore — bundles listing page. */
const ORBS = ["📚", "🌙", "💌", "🧭", "🧚", "⚗️", "🏛️", "🎭", "🦇", "🗝️", "🌊", "✒️"];
function orb(s) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return ORBS[h % ORBS.length] }
let page = 1, cat = "", PS = 12;
async function load() {
  const grid = document.getElementById('grid'), pag = document.getElementById('pagination'), empty = document.getElementById('empty');
  grid.innerHTML = '<div class="col-span-full text-center py-12"><div class="inline-block w-8 h-8 border-4 border-stone-200 border-t-stone-800 rounded-full animate-spin"></div><p class="text-stone-500 mt-3 text-sm">Loading bundles…</p></div>';
  let url = `/api/v1/bundles?page=${page}&page_size=${PS}`; if (cat) url += `&category=${encodeURIComponent(cat)}`;
  try {
    const r = await fetch(url); if (!r.ok) throw new Error(r.status); const d = await r.json();
    const items = d.items || []; const total = d.total || items.length; document.getElementById('bundle-count').textContent = total;
    if (!items.length) { grid.innerHTML = ""; empty.classList.remove('hidden'); pag.innerHTML = ""; return } empty.classList.add('hidden');
    grid.innerHTML = items.map(b => {
      const n = Array.isArray(b.books) ? b.books.length : '?';
      return `<a href="/bundles/${b.slug}" class="bundle-card group"><div class="cover"><div class="bundle-orb">${orb(b.slug || b.name)}</div></div>
      <div class="p-5"><div class="flex justify-between gap-3"><h3 class="font-serif text-lg font-bold leading-tight">${b.name}</h3><span class="shrink-0 text-xs font-semibold px-2 py-1 rounded-full bg-stone-900 text-white">${n} books</span></div>
      ${b.category ? `<p class="text-xs uppercase tracking-wide font-medium text-stone-500 mt-1">${b.category}</p>` : ''}
      <p class="text-sm leading-6 text-stone-600 mt-2 line-clamp-2">${b.description || 'A wonderful set.'}</p>
      <div class="flex items-center justify-between mt-4 pt-4 border-t"><span class="font-semibold">${formatPrice(b.price_cents, b.currency)}</span><span class="text-sm font-medium text-stone-600 group-hover:text-stone-900">View →</span></div></div></a>`;
    }).join('');
    const tp = Math.ceil(total / PS); let h = ""; if (tp > 1) {
      h += `<button data-action="go" data-arg-1="${page - 1}" ${page <= 1 ? 'disabled' : ''} class="px-4 py-2 rounded-full border bg-white text-sm ${page <= 1 ? 'opacity-40' : ''}">Previous</button>`;
      for (let i = Math.max(1, page - 2); i <= Math.min(tp, page + 2); i++) h += `<button data-action="go" data-arg-1="${i}" class="w-10 h-10 rounded-full text-sm ${i === page ? 'bg-stone-900 text-white' : 'border bg-white'}">${i}</button>`;
      if (page + 2 < tp) h += `<span class="text-stone-400">…</span><button data-action="go" data-arg-1="${tp}" class="w-10 h-10 rounded-full border bg-white text-sm">${tp}</button>`;
      h += `<button data-action="go" data-arg-1="${page + 1}" ${page >= tp ? 'disabled' : ''} class="px-4 py-2 rounded-full border bg-white text-sm ${page >= tp ? 'opacity-40' : ''}">Next</button>`;
    } pag.innerHTML = h;
  } catch (e) { grid.innerHTML = '<div class="col-span-full text-center py-12 bg-white rounded-2xl border"><p class="text-stone-600">Could not load bundles.</p><button data-action="load" class="mt-3 px-5 py-2 rounded-full bg-stone-900 text-white text-sm">Retry</button></div>' }
}
function go(p) { if (p < 1) return; page = p; load(); scrollTo({ top: 0, behavior: 'smooth' }) }
document.querySelectorAll('#cat-filters button').forEach(b => b.addEventListener('click', e => {
  document.querySelectorAll('#cat-filters button').forEach(x => x.classList.remove('active')); e.target.classList.add('active');
  cat = e.target.dataset.cat; page = 1; load();
}));
document.addEventListener('DOMContentLoaded', load);