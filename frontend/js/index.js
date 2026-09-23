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
    const controls = document.getElementById('featured-controls');
    try {
      const r = await fetch('/api/v1/bundles?featured=true&page_size=100'); if (!r.ok) throw 0;
      const d = await r.json();
      let items = d.items || [];
      const r2 = await fetch('/api/v1/bundles?page_size=100');
      if (r2.ok) {
        const all = (await r2.json()).items || [];
        const seen = new Set(items.map(b => b.slug));
        items = items.concat(all.filter(b => !seen.has(b.slug)));
      }
      if (!items.length) { el.innerHTML = '<div class="col-span-full text-center py-12 border rounded-2xl bg-white"><p class="font-medium">No featured bundles</p></div>'; return }
      const PAGE = 6;
      const pages = [];
      for (let i = 0; i < items.length; i += PAGE) pages.push(items.slice(i, i + PAGE));
      let page = 0, timer = null;

      function card(b) {
        const n = Array.isArray(b.books) ? b.books.length : '?';
        const cover = b.books && b.books[0] && b.books[0].cover_path ? `<img src="${b.books[0].cover_path}" alt="${b.books[0].title || 'Bundle cover'}" class="w-full h-24 object-cover rounded-xl border">` : `<div class="w-full h-24 bg-[#ece9e3] rounded-xl"></div>`;
        return `<a href="/bundles/${b.slug}" class="group bg-white border rounded-2xl p-5 hover:border-[#0b0b0c] transition">
          ${cover}
          <h3 class="font-serif text-lg font-semibold leading-tight mt-4 group-hover:underline">${b.name}</h3>
          <p class="text-xs uppercase tracking-wide font-medium text-[#8a8683] mt-1">${b.category || ''} · ${n} works</p>
          <p class="text-sm leading-6 text-[#57534e] mt-2 line-clamp-2">${b.description || ''}</p>
          <p class="text-sm font-semibold mt-4">${price(b.price_cents, b.currency)} <span class="font-normal text-[#8a8683]">— view →</span></p>
        </a>`;
      }

      function render() {
        el.innerHTML = pages[page].map(card).join('');
        if (controls) {
          const dots = pages.map((_, i) =>
            `<button data-page="${i}" aria-label="Bundle set ${i + 1}" class="w-2 h-2 rounded-full transition ${i === page ? 'bg-[#0b0b0c]' : 'bg-[#d6d3cd] hover:bg-[#8a8683]'}"></button>`).join('');
          controls.innerHTML = `
            <button id="featured-prev" aria-label="Previous set" class="w-9 h-9 rounded-full border bg-white text-lg leading-none hover:border-[#0b0b0c] transition">‹</button>
            <div class="flex items-center gap-1.5 px-2">${dots}</div>
            <button id="featured-next" aria-label="Next set" class="w-9 h-9 rounded-full border bg-white text-lg leading-none hover:border-[#0b0b0c] transition">›</button>`;
          controls.querySelector('#featured-prev').onclick = () => { page = (page - 1 + pages.length) % pages.length; render(); restart(); };
          controls.querySelector('#featured-next').onclick = () => { page = (page + 1) % pages.length; render(); restart(); };
          controls.querySelectorAll('[data-page]').forEach(btn => {
            btn.onclick = () => { page = +btn.dataset.page; render(); restart(); };
          });
        }
      }
      function restart() { clearInterval(timer); timer = setInterval(() => { page = (page + 1) % pages.length; render(); }, 6000); }
      render();
      if (pages.length > 1) {
        restart();
        el.addEventListener('mouseenter', () => clearInterval(timer));
        el.addEventListener('mouseleave', restart);
      }
    } catch (e) { el.innerHTML = '<div class="col-span-full text-center py-10 border rounded-2xl bg-white"><p class="text-sm text-[#57534e]">Could not load bundles.</p></div>' }
  }
  document.addEventListener('DOMContentLoaded', () => { covers(); featured(); });
})();