/* Babe's Bookstore — homepage. */
(function () {
  'use strict';
  function price(cents, ccy) { return (window.formatPrice ? formatPrice(cents, ccy) : ('£' + (cents / 100).toFixed(2))) }
  async function covers() {
    try {
      const r = await fetch('/api/v1/books?page_size=8&category=Classics'); if (!r.ok) throw 0;
      const d = await r.json(); const items = d.items || [];
      const grid = document.getElementById('cover-grid');
      if (!grid) return;
      grid.innerHTML = items.map(b => {
        const cover = b.cover_path && /^https?:\/\//.test(b.cover_path) ? `<img src="${b.cover_path}" alt="${b.title || 'Book cover'}" class="w-full h-full object-cover">` : `<div class="w-full h-full bg-[#ece9e3] flex items-center justify-center text-[#8a8683] font-serif text-xl">${(b.title || '?').charAt(0)}</div>`;
        return `<a href="/books/${b.id}" class="block aspect-[3/4] bg-white border rounded-xl overflow-hidden hover:border-[#0b0b0c] transition">${cover}</a>`;
      }).join('');
    } catch { }
  }
  async function featured() {
    const el = document.getElementById('featured-bundles');
    try {
      const r = await fetch('/api/v1/bundles?featured=true&page_size=6'); if (!r.ok) throw 0;
      const d = await r.json(); const items = d.items || [];
      if (!items.length) { el.innerHTML = '<div class="col-span-full text-center py-12 border rounded-2xl bg-white"><p class="font-medium">No featured bundles</p></div>'; return }
      el.innerHTML = items.map(b => {
        const n = Array.isArray(b.books) ? b.books.length : '?';
        const cover = b.books && b.books[0] && b.books[0].cover_path ? `<img src="${b.books[0].cover_path}" alt="${b.books[0].title || 'Bundle cover'}" class="w-full h-24 object-cover rounded-xl border">` : `<div class="w-full h-24 bg-[#ece9e3] rounded-xl"></div>`;
        return `<a href="/bundles/${b.slug}" class="group bg-white border rounded-2xl p-5 hover:border-[#0b0b0c] transition">
          ${cover}
          <h3 class="font-serif text-lg font-semibold leading-tight mt-4 group-hover:underline">${b.name}</h3>
          <p class="text-xs uppercase tracking-wide font-medium text-[#8a8683] mt-1">${b.category || ''} · ${n} works</p>
          <p class="text-sm leading-6 text-[#57534e] mt-2 line-clamp-2">${b.description || ''}</p>
          <p class="text-sm font-semibold mt-4">${price(b.price_cents, b.currency)} <span class="font-normal text-[#8a8683]">— view →</span></p>
        </a>`;
      }).join('');
    } catch (e) { el.innerHTML = '<div class="col-span-full text-center py-10 border rounded-2xl bg-white"><p class="text-sm text-[#57534e]">Could not load bundles.</p></div>' }
  }
  document.addEventListener('DOMContentLoaded', () => { covers(); featured(); });
})();