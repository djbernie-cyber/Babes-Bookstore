/* Babe's Bookstore — bundle detail page. */
const ORBS = ["📚", "🌙", "💌", "🧭", "🧚", "⚗️", "🏛️", "🎭", "🦇", "🗝️", "🌊", "✒️"];
function orb(s) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return ORBS[h % ORBS.length] }
let bundle = null;
function slug() { const p = location.pathname.split('/').filter(Boolean); return p[p.length - 1] }
async function load() {
  const s = slug(); if (!s) return showErr();
  try { const r = await fetch(`/api/v1/bundles/${encodeURIComponent(s)}`); if (!r.ok) throw new Error(); bundle = await r.json(); render(bundle) } catch (e) { showErr() }
}
function render(b) {
  document.getElementById('loading').classList.add('hidden'); document.getElementById('content').classList.remove('hidden');
  document.getElementById('name').textContent = b.name; document.title = b.name + " — Babe's Bookstore";
  document.getElementById('orb').textContent = orb(b.slug || b.name);
  document.getElementById('cat').textContent = b.category || ""; document.getElementById('desc').textContent = b.description || "";
  document.getElementById('price').textContent = formatPrice(b.price_cents, b.currency);
  const books = b.books || []; document.getElementById('count').textContent = books.length + " books"; document.getElementById('book-count').textContent = `(${books.length})`;
  const el = document.getElementById('books');
  if (!books.length) el.innerHTML = '<div class="bg-white rounded-2xl border p-6 text-center text-stone-500">Book list coming soon.</div>';
  else el.innerHTML = books.map((bk, i) => `<a href="/books/${bk.id}" class="flex gap-4 bg-white rounded-2xl border p-4 hover:shadow-sm hover:border-stone-300 transition"><span class="w-8 h-8 rounded-full bg-stone-900 text-white grid place-items-center text-sm font-bold shrink-0">${i + 1}</span><div class="min-w-0"><p class="font-semibold leading-tight">${bk.title}</p><p class="text-sm text-stone-500">${bk.author || ''}</p></div><span class="ml-auto text-stone-400">→</span></a>`).join('');
  try { const u = JSON.parse(localStorage.getItem('user') || 'null'); if (u && u.is_admin) { document.getElementById('free-section').classList.remove('hidden'); document.getElementById('paid').classList.add('hidden') } } catch (e) { }
}
function showErr() { document.getElementById('loading').classList.add('hidden'); document.getElementById('error').classList.remove('hidden') }
async function freeDownload() {
  const token = localStorage.getItem('token'), user = JSON.parse(localStorage.getItem('user') || 'null');
  if (!token || !user) { alert('Please login'); location.href = '/login'; return }
  const r = await fetch('/api/v1/checkout/free', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token }, body: JSON.stringify({ bundle_slug: slug(), email: user.email }) });
  const d = await r.json(); if (!r.ok) return alert(d.detail || 'Failed'); alert('Free download started!'); if (d.checkout_url) location.href = d.checkout_url;
}
async function pay(provider) {
  const email = prompt('Email to receive download links:'); if (!email || !email.includes('@')) return alert('Valid email required');
  let phone = null;
  if (provider === 'mpesa') {
    phone = prompt('M-Pesa phone (2547XXXXXXXX):'); if (!phone) return;
    phone = phone.replace(/\s|-/g, '');
    if (phone.startsWith('0')) phone = '254' + phone.slice(1);
    if (phone.startsWith('7') && phone.length === 9) phone = '254' + phone;
    if (!phone.startsWith('254') || phone.length !== 12) return alert('Invalid phone — use 2547XXXXXXXX');
  }
  const btn = this && this.closest ? this.closest('button') : null;
  if (!btn) return;
  const orig = btn.innerHTML; btn.innerHTML = 'Processing…'; btn.disabled = true;
  try {
    const body = { bundle_slug: slug(), email }; if (phone) body.phone = phone;
    const r = await fetch(`/api/v1/checkout/${provider}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail || 'Checkout failed');
    if (provider === 'mpesa') {
      alert('M-Pesa STK push sent to ' + phone + ' — check your phone, enter PIN, then check /account for download once paid. Funds settle directly to the configured shortcode.');
    }
    if (d.checkout_url || d.url) location.href = d.checkout_url || d.url; else { alert('Checkout created — check email/phone'); btn.innerHTML = orig; btn.disabled = false }
  } catch (e) { alert(e.message); btn.innerHTML = orig; btn.disabled = false }
}
async function loadMpesaConfig() {
  try {
    const r = await fetch('/api/v1/checkout/config?_=' + Date.now()); if (!r.ok) return;
    const c = await r.json();
    if (c.mpesa_enabled) {
      document.getElementById('mpesa-btn').classList.remove('hidden');
      document.getElementById('mpesa-hint').classList.remove('hidden');
    }
  } catch (e) { }
}
document.addEventListener('DOMContentLoaded', () => { load(); loadMpesaConfig(); });