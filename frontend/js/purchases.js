/* Babe's Bookstore — purchases & wishlist page. */
function logout() { localStorage.removeItem('token'); localStorage.removeItem('user'); location.href = '/login' }
function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function firstName(u) {
  const raw = (u.name || (u.email || '').split('@')[0] || 'Reader').trim().split(/\s+/)[0] || 'Reader';
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}
function check() {
  const t = localStorage.getItem('token'), s = localStorage.getItem('user');
  if (!t || !s) { document.getElementById('logged-out').classList.remove('hidden'); return }
  let u; try { u = JSON.parse(s) } catch (e) { localStorage.clear(); document.getElementById('logged-out').classList.remove('hidden'); return }
  document.getElementById('logged-in').classList.remove('hidden');
  document.getElementById('uname').textContent = u.name || u.email || 'User';
  document.getElementById('uemail').textContent = u.email || '';
  document.getElementById('avatar').textContent = (u.name || u.email || 'U').charAt(0).toUpperCase();
  document.getElementById('jones-name').textContent = firstName(u);
  if (u.is_admin) document.getElementById('badge-admin').classList.remove('hidden');
  load(t);
  loadWishlist(t);
}
async function loadWishlist(token) {
  try {
    const r = await fetch('/api/v1/wishlist', { headers: { 'Authorization': 'Bearer ' + token } }); if (!r.ok) throw new Error();
    const d = await r.json(); const items = d.items || [];
    const empty = document.getElementById('wishlist-empty'), list = document.getElementById('wishlist-list');
    if (!items.length) { empty.classList.remove('hidden'); return }
    empty.classList.add('hidden'); list.classList.remove('hidden');
    list.innerHTML = items.map(b => {
      const cover = b.cover_url && /^https?:\/\//.test(b.cover_url) ? `<img src="${b.cover_url}" alt="${b.title || 'Book cover'}" class="w-full h-28 object-cover rounded-xl border">` : `<div class="w-full h-28 bg-[#ece9e3] rounded-xl grid place-items-center text-[#8a8683] font-serif text-3xl">${(b.title || '?').charAt(0)}</div>`;
      return `<a href="/books/${b.id}" class="block bg-white border rounded-2xl p-3 hover:border-[#0b0b0c] transition"><div class="text-right"><button data-action="unwish" data-arg-1="${b.id}" data-prevent data-remove-closest="a" class="text-stone-400 hover:text-red-600 text-xs font-semibold">♡ remove</button></div>${cover}<h3 class="font-serif font-semibold leading-tight mt-2">${esc(b.title)}</h3><p class="text-xs text-stone-500 mt-0.5">${esc(b.author)}</p></a>`;
    }).join('');
  } catch (e) { console.error(e) }
}
async function unwish(id) {
  const t = localStorage.getItem('token');
  try { await fetch(`/api/v1/wishlist/${id}`, { method: 'DELETE', headers: { 'Authorization': 'Bearer ' + t } }); } catch (e) { }
}
async function loadVault(apiToken) {
  try {
    const r = await fetch('/api/v1/library/summary', { headers: { 'Authorization': 'Bearer ' + apiToken } }); if (!r.ok) return;
    const d = await r.json();
    const sv = document.getElementById('vault-saved'); if (sv) sv.textContent = (d.total_saved || 0).toLocaleString();
    const vb = document.getElementById('vault-bundles'); if (vb) vb.textContent = (d.bundle_count || 0).toLocaleString();
  } catch (e) { }
}
async function load(token) {
  loadVault(token);
  try {
    const r = await fetch('/api/v1/purchases', { headers: { 'Authorization': 'Bearer ' + token } }); if (!r.ok) throw new Error();
    const arr = await r.json(); if (!Array.isArray(arr) || !arr.length) return;
    document.getElementById('empty').classList.add('hidden'); const el = document.getElementById('list'); el.classList.remove('hidden');
    el.innerHTML = arr.map(p => {
      const d = p.created_at ? new Date(p.created_at).toLocaleDateString() : '';
      const st = p.status || 'completed'; const cls = st === 'completed' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : st === 'failed' ? 'bg-red-50 text-red-700 border-red-200' : 'bg-amber-50 text-amber-700 border-amber-200';
      const dl = p.download_available ? `<button data-action="dl" data-args='${encodeURIComponent(JSON.stringify([p.id, p.download_token || '']))}' class="mt-3 w-full py-2.5 rounded-full bg-stone-900 text-white text-sm font-medium">Download</button>` : '';
      return `<div class="bg-white rounded-2xl border p-5"><h3 class="font-serif font-bold leading-tight">${esc(p.bundle_name) || 'Bundle'}</h3><div class="flex items-center justify-between mt-1"><p class="text-sm text-stone-500">${d}</p><span class="text-xs font-medium px-2 py-1 rounded-full border ${cls}">${esc(st)}</span></div><p class="text-sm font-semibold mt-2">${formatPrice(p.amount_cents, p.currency)}</p>${dl}</div>`;
    }).join('');
  } catch (e) { console.error(e) }
}
async function dl(id, tok) {
  const t = localStorage.getItem('token');
  try {
    const r = await fetch(`/api/v1/purchases/${id}/download?token=${encodeURIComponent(tok || '')}`, { headers: { 'Authorization': 'Bearer ' + t } });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail || 'Not available'); if (d.url) location.href = d.url;
  } catch (e) { alert(e.message) }
}
document.addEventListener('DOMContentLoaded', check);