/* Babe's Bookstore — book detail page. */
const grads = ['from-amber-400 to-orange-500', 'from-rose-400 to-pink-500', 'from-emerald-400 to-teal-500', 'from-blue-400 to-indigo-500', 'from-violet-400 to-purple-500'];
function g(id) { return grads[Math.abs(id) % grads.length] }
function badge(t, c) { return `<span class="px-3 py-1 rounded-full text-xs font-medium border ${c}">${t}</span>` }
async function load() {
  const id = location.pathname.split('/').filter(Boolean).pop();
  const loading = document.getElementById('loading'), err = document.getElementById('err'), box = document.getElementById('book');
  try {
    const r = await fetch(`/api/v1/books/${encodeURIComponent(id)}`); if (!r.ok) throw new Error();
    const b = await r.json(); loading.classList.add('hidden'); box.classList.remove('hidden');
    document.title = b.title + " — Babe's Bookstore";
    const cover = document.getElementById('cover');
    if (b.cover_path && /^https?:\/\//.test(b.cover_path)) cover.innerHTML = `<img src="${b.cover_path}" alt="${b.title || 'Book cover'}" class="w-full h-full object-cover">`;
    else cover.innerHTML = `<div class="w-full min-h-[380px] bg-gradient-to-br ${g(b.id)} flex items-center justify-center"><span class="text-white text-7xl font-serif font-bold opacity-80">${(b.title || '?').charAt(0)}</span></div>`;
    document.getElementById('title').textContent = b.title; document.getElementById('author').textContent = b.author ? `by ${b.author}` : '';
    let m = ""; if (b.license_type) m += badge(b.license_type, 'bg-emerald-50 text-emerald-800 border-emerald-200'); if (b.category) m += badge(b.category, 'bg-white text-stone-700 border-stone-200'); if (b.publication_year) m += `<span class="text-sm text-stone-500">${b.publication_year}</span>`; if (b.language) m += `<span class="text-sm text-stone-400">${b.language}</span>`;
    document.getElementById('meta').innerHTML = m;
    document.getElementById('desc').innerHTML = b.description ? `<p class="whitespace-pre-wrap">${esc(b.description)}</p>` : '<p class="italic text-stone-400">No description.</p>';
    let s = ""; if (b.source_url) s += `<p>Sourced from <a href="${b.source_url}" target="_blank" rel="noopener" class="underline">${b.source_url}</a></p>`; if (b.source) s += `<p class="text-stone-400 mt-1">${b.source}${b.source_id ? ' · #' + b.source_id : ''}</p>`; document.getElementById('source').innerHTML = s || '<span class="italic">Source not listed.</span>';
    document.getElementById('download').href = `/api/v1/books/${b.id}/download`;
    const readBtn = document.getElementById('read-online'), readCard = document.getElementById('read-card-btn');
    if (readBtn) readBtn.href = `/read/${b.id}`;
    if (readCard) readCard.href = `/read/${b.id}`;
  } catch (e) { loading.classList.add('hidden'); err.classList.remove('hidden') }
}

const BID = location.pathname.split('/').filter(Boolean).pop();
const token = localStorage.getItem('token');
function authHeaders() { return token ? { 'Authorization': 'Bearer ' + token } : {} }

function stars(r) { let s = ''; for (let i = 1; i <= 5; i++) s += i <= Math.round(r || 0) ? '★' : '☆'; return `<span class="text-amber-500">${s}</span>`; }
function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

/* ── Wishlist ──────────────────────────────────────────────────────── */
let _wishlisted = false;

async function loadWishlist() {
  const card = document.getElementById('wishlist-card'); if (!card) return;
  card.classList.remove('hidden');
  if (!token) {
    card.innerHTML = '<p class="text-xs font-semibold uppercase tracking-wide text-[#8a8683]">Wishlist</p><p class="text-sm text-[#57534e] mt-1"><a href="/login" class="underline">Log in</a> to save books for later.</p>';
    return;
  }
  try { const r = await fetch(`/api/v1/wishlist/status/${BID}`, { headers: authHeaders() }); if (r.ok) _wishlisted = !!(await r.json()).wishlisted; } catch (e) { }
  _renderWishlist();
}

function _renderWishlist() {
  const card = document.getElementById('wishlist-card'); if (!card) return;
  card.innerHTML = `<p class="text-xs font-semibold uppercase tracking-wide text-[#8a8683]">Wishlist</p><button id="wl-toggle" class="w-full py-3 rounded-full border text-sm font-semibold ${_wishlisted ? 'bg-[#0b0b0c] text-white' : 'bg-white hover:bg-[#fcfaf7]'}">${_wishlisted ? '♥ Wishlisted' : '♡ Save to wishlist'}</button>`;
  document.getElementById('wl-toggle').addEventListener('click', _toggleWishlist);
}

async function _toggleWishlist() {
  const btn = document.getElementById('wl-toggle'); if (!btn) return;
  btn.disabled = true;
  try {
    const r = await fetch(`/api/v1/wishlist/${BID}`, { method: _wishlisted ? 'DELETE' : 'POST', headers: authHeaders() });
    if (r.ok) { _wishlisted = !_wishlisted; _renderWishlist(); }
  } catch (e) { }
  if (btn) btn.disabled = false;
}

/* ── Reviews ───────────────────────────────────────────────────────── */
let _hasMyReview = false;

async function loadReviews() {
  const section = document.getElementById('reviews-section'); if (!section) return;
  section.classList.remove('hidden');
  const auth = document.getElementById('review-auth'), anon = document.getElementById('review-anon');
  if (token) { auth.classList.remove('hidden'); anon.classList.add('hidden'); } else { anon.classList.remove('hidden'); }

  let data = { items: [], summary: { count: 0, average: null } };
  try { const r = await fetch(`/api/v1/books/${BID}/reviews`); if (r.ok) data = await r.json(); } catch (e) { }
  document.getElementById('rating-summary').innerHTML =
    data.summary.count ? `${stars(data.summary.average)} <span class="text-sm text-stone-500">${Number(data.summary.average).toFixed(1)} · ${data.summary.count} review${data.summary.count === 1 ? '' : 's'}</span>` : '<span class="text-sm text-stone-400">No reviews yet — be the first.</span>';

  const list = document.getElementById('reviews-list');
  if (!data.items.length) { list.innerHTML = '<p class="text-sm italic text-stone-400">No reviews yet.</p>'; }
  else {
    list.innerHTML = data.items.map(rv => `
      <div class="border rounded-2xl p-4 bg-white">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">${stars(rv.rating)}<span class="font-semibold text-sm">${esc(rv.user_name) || 'Reader'}</span></div>
          <span class="text-xs text-stone-400">${rv.created_at ? new Date(rv.created_at).toLocaleDateString() : ''}</span>
        </div>
        ${rv.title ? `<p class="font-medium text-sm mt-1">${esc(rv.title)}</p>` : ''}
        ${rv.body ? `<p class="text-sm text-stone-600 mt-1 whitespace-pre-wrap">${esc(rv.body)}</p>` : ''}
      </div>`).join('');
  }

  const del = document.getElementById('rev-delete');
  if (token) {
    try {
      del.classList.remove('hidden');
    } catch (e) { }
  }
}

function _bindReviewForm() {
  const sub = document.getElementById('rev-submit');
  const del = document.getElementById('rev-delete');
  if (sub) sub.addEventListener('click', _submitReview);
  if (del) del.addEventListener('click', _deleteReview);
}

async function _submitReview() {
  const ratingEl = document.getElementById('rev-rating');
  const titleEl = document.getElementById('rev-title');
  const bodyEl = document.getElementById('rev-body');
  const msg = document.getElementById('rev-msg');
  const rating = parseInt(ratingEl.value, 10);
  if (rating < 1 || rating > 5) { msg.textContent = 'Rating must be 1–5.'; msg.className = 'text-sm mt-2 text-red-600'; return; }
  const body = bodyEl.value.trim();
  const title = titleEl.value.trim();
  const r = await fetch(`/api/v1/books/${BID}/reviews`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ rating, title, body })
  });
  if (r.ok) {
    msg.textContent = 'Review posted. Thank you!'; msg.className = 'text-sm mt-2 text-emerald-600';
    ratingEl.value = '5'; titleEl.value = ''; bodyEl.value = '';
    loadReviews();
  } else {
    const e = await r.json().catch(() => ({}));
    msg.textContent = e.detail || 'Could not post review.'; msg.className = 'text-sm mt-2 text-red-600';
  }
}

async function _deleteReview() {
  const msg = document.getElementById('rev-msg');
  const r = await fetch(`/api/v1/books/${BID}/reviews/mine`, { method: 'DELETE', headers: authHeaders() });
  if (r.ok) { msg.textContent = 'Review deleted.'; msg.className = 'text-sm mt-2 text-stone-600'; loadReviews(); }
  else { msg.textContent = 'No review to delete.'; msg.className = 'text-sm mt-2 text-stone-500'; }
}

document.addEventListener('DOMContentLoaded', function () {
  load(); loadWishlist(); loadReviews(); _bindReviewForm();
});