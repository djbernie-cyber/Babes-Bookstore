/* Babe's Bookstore — custom bundle builder. */
let picks = [];
let curPage = 1, totalPages = 1;
let __searchItems = [];

function renderTray() {
  const tray = document.getElementById('tray'), empty = document.getElementById('tray-empty');
  const count = document.getElementById('count'), hint = document.getElementById('count-hint'), btn = document.getElementById('create'), pn = document.getElementById('preview-n');
  count.textContent = picks.length + " / 100"; pn.textContent = picks.length;
  if (!picks.length) { empty.classList.remove('hidden'); tray.querySelectorAll('.pick').forEach(e => e.remove()); }
  else {
    empty.classList.add('hidden');
    tray.querySelectorAll('.pick').forEach(e => e.remove());
    picks.forEach((b, i) => {
      const div = document.createElement('div');
      div.className = 'pick flex items-center gap-3 bg-white border rounded-xl p-3';
      div.draggable = true;
      div.dataset.idx = i;
      div.innerHTML = `<span class="w-7 h-7 rounded-full bg-stone-900 text-white grid place-items-center text-xs font-bold shrink-0">${i + 1}</span>
        <div class="min-w-0 flex-1"><p class="text-sm font-medium leading-tight truncate">${esc(b.title)}</p><p class="text-xs text-stone-500 truncate">${esc(b.author || '')}</p></div>
        <div class="flex items-center gap-1 shrink-0">
          <button data-action="move" data-arg-1="${i}" data-arg-2="-1" class="w-7 h-7 rounded-full border bg-white text-xs" ${i === 0 ? 'disabled' : ''}>↑</button>
          <button data-action="move" data-arg-1="${i}" data-arg-2="1" class="w-7 h-7 rounded-full border bg-white text-xs" ${i === picks.length - 1 ? 'disabled' : ''}>↓</button>
          <button data-action="removePick" data-arg-1="${i}" class="w-7 h-7 rounded-full bg-red-50 border border-red-200 text-red-700 text-xs">✕</button>
        </div>`;
      div.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', i) });
      div.addEventListener('dragover', e => e.preventDefault());
      div.addEventListener('drop', e => { e.preventDefault(); const from = +e.dataTransfer.getData('text/plain'); const to = i; if (from !== to) reorder(from, to) });
      tray.appendChild(div);
    });
  }
  const ok = picks.length >= 3 && picks.length <= 100;
  const name = document.getElementById('b-name').value.trim();
  btn.disabled = !(ok && name.length >= 3);
  btn.className = btn.disabled ? "mt-4 w-full py-3.5 rounded-full bg-stone-300 text-stone-500 font-semibold cursor-not-allowed" : "mt-4 w-full py-3.5 rounded-full bg-stone-900 text-white font-semibold hover:bg-black";
  btn.textContent = !picks.length ? "Add 3+ books to continue" : picks.length < 3 ? `Add ${3 - picks.length} more book${3 - picks.length === 1 ? '' : 's'}` : name.length < 3 ? "Enter a bundle name" : `Create bundle — £10 →`;
  hint.textContent = ok ? `${picks.length} books · ready to create` : `Add at least 3 books to create your bundle.`;
  hint.className = ok ? "text-xs text-emerald-700 mt-1 font-medium" : "text-xs text-stone-500 mt-1";
}
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML }
function addPick(i) { const b = __searchItems[i]; if (!b) return; if (picks.find(p => p.id === b.id)) return; if (picks.length >= 100) return alert('Custom bundles are limited to 100 books.'); picks.push({ id: b.id, title: b.title, author: b.author }); renderTray() }
function removePick(i) { picks.splice(i, 1); renderTray() }
function move(i, dir) { const j = i + dir; if (j < 0 || j >= picks.length) return; const t = picks[i]; picks[i] = picks[j]; picks[j] = t; renderTray() }
function reorder(from, to) { const [m] = picks.splice(from, 1); picks.splice(to, 0, m); renderTray() }

async function doSearch(page) {
  if (page) curPage = page;
  const q = document.getElementById('q').value.trim(), cat = document.getElementById('cat').value;
  const meta = document.getElementById('meta'), results = document.getElementById('results'), pag = document.getElementById('r-pag'), empty = document.getElementById('r-empty');
  meta.classList.add('hidden'); results.innerHTML = '<div class="text-center py-8"><div class="inline-block w-7 h-7 border-4 border-stone-200 border-t-stone-800 rounded-full animate-spin"></div><p class="text-xs text-stone-500 mt-2">Searching…</p></div>'; empty.classList.add('hidden'); pag.innerHTML = "";
  const params = new URLSearchParams(); if (q) params.set('search', q); if (cat) params.set('category', cat); params.set('page', curPage); params.set('page_size', '12');
  try {
    const r = await fetch('/api/v1/books?' + params.toString()); if (!r.ok) throw new Error(r.status);
    const d = await r.json(); const items = d.items || []; const total = d.total || 0; totalPages = Math.ceil(total / 12) || 1;
    meta.textContent = `${total.toLocaleString()} result${total === 1 ? '' : 's'}${q ? ' for “' + q + '”' : ''}${cat ? ' in ' + cat : ''}`; meta.classList.remove('hidden');
    if (!items.length) { results.innerHTML = ""; empty.classList.remove('hidden'); return }
    __searchItems = items;
    results.innerHTML = items.map((b, i) => {
      const added = !!picks.find(p => p.id === b.id);
      return `<div class="flex gap-3 bg-stone-50 border rounded-xl p-3">
        <div class="w-12 h-16 rounded-lg bg-gradient-to-br from-stone-800 to-stone-600 shrink-0 grid place-items-center text-white font-serif font-bold">${esc((b.title || '?').charAt(0))}</div>
        <div class="min-w-0 flex-1"><p class="text-sm font-semibold leading-tight line-clamp-2">${esc(b.title)}</p><p class="text-xs text-stone-500 truncate">${esc(b.author || 'Unknown')} ${b.category ? '· ' + esc(b.category) : ''}</p>
        <div class="mt-2 flex gap-2"><a href="/books/${b.id}" target="_blank" class="text-xs px-2.5 py-1 rounded-full border bg-white hover:bg-stone-50">View</a>
        <button data-action="addPick" data-arg-1="${i}" ${added ? 'disabled' : ''} class="text-xs px-3 py-1 rounded-full ${added ? 'bg-emerald-50 border border-emerald-200 text-emerald-700' : 'bg-stone-900 text-white hover:bg-black'}">${added ? 'Added ✓' : 'Add →'}</button></div></div></div>`;
    }).join('');
    let h = ""; if (totalPages > 1) {
      h += `<button data-action="doSearch" data-arg-1="${curPage - 1}" ${curPage <= 1 ? 'disabled' : ''} class="px-3 py-1.5 rounded-full border bg-white text-xs ${curPage <= 1 ? 'opacity-40' : ''}">Prev</button>`;
      h += `<span class="text-xs text-stone-500 px-2">Page ${curPage} / ${totalPages}</span>`;
      h += `<button data-action="doSearch" data-arg-1="${curPage + 1}" ${curPage >= totalPages ? 'disabled' : ''} class="px-3 py-1.5 rounded-full border bg-white text-xs ${curPage >= totalPages ? 'opacity-40' : ''}">Next</button>`;
    } pag.innerHTML = h;
  } catch (e) { results.innerHTML = `<p class="text-center py-8 text-sm text-red-600">Search failed: ${esc(e.message)}</p>` }
}

document.getElementById('b-name').addEventListener('input', renderTray);
document.getElementById('b-slug').addEventListener('input', () => { document.getElementById('b-slug').value = document.getElementById('b-slug').value.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/--+/g, '-') });
document.getElementById('q').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); doSearch(1) } });

async function createBundle() {
  const err = document.getElementById('err'); err.classList.add('hidden');
  const name = document.getElementById('b-name').value.trim(), slug = document.getElementById('b-slug').value.trim(), desc = document.getElementById('b-desc').value.trim();
  if (name.length < 3) { err.textContent = 'Bundle name must be at least 3 characters.'; err.classList.remove('hidden'); return }
  if (picks.length < 3) { err.textContent = 'Add at least 3 books.'; err.classList.remove('hidden'); return }
  const btn = document.getElementById('create'); const orig = btn.textContent; btn.textContent = 'Creating…'; btn.disabled = true;
  const payload = { name, slug: slug || name, description: desc || `A custom bundle of ${picks.length} hand-picked books.`, long_description: desc || '', price_cents: BUNDLE_PRICE_PENCE || 1000, currency: 'gbp', category: 'Custom', bundle_type: 'custom', book_ids: picks.map(p => p.id) };
  const headers = { 'Content-Type': 'application/json' }; const t = localStorage.getItem('token'); if (t) headers['Authorization'] = 'Bearer ' + t;
  try {
    const r = await fetch('/api/v1/bundles/custom', { method: 'POST', headers, body: JSON.stringify(payload) });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail || 'Failed to create bundle');
    location.href = '/bundles/' + encodeURIComponent(d.slug);
  } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); btn.textContent = orig; btn.disabled = false }
}
var BUNDLE_PRICE_PENCE = 1000, SYM = '£';
async function loadConfig() {
  try {
    const r = await fetch('/api/v1/checkout/config?_=' + Date.now()); if (!r.ok) return;
    const c = await r.json();
    if (typeof c.price_pence === 'number' && c.price_pence > 0) BUNDLE_PRICE_PENCE = c.price_pence;
    if (c.currency_symbol) SYM = c.currency_symbol;
    const disp = SYM + (BUNDLE_PRICE_PENCE / 100).toFixed(2);
    var hp = document.getElementById('h-price'); if (hp) hp.textContent = ' for ' + disp;
    var hp2 = document.getElementById('h-price2'); if (hp2) hp2.textContent = 'Only ' + disp + ' — any 3–100 books';
    var bp = document.getElementById('b-price'); if (bp) bp.textContent = disp;
    var hw = document.getElementById('how-price'); if (hw) hw.innerHTML = hw.innerHTML.replace(/£[0-9]+(?:\.[0-9]{2})?/, ' ' + disp + ' ');
  } catch (e) { }
}
document.addEventListener('DOMContentLoaded', () => { doSearch(1); renderTray(); loadConfig(); });