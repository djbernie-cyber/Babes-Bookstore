/* Babe's Bookstore — homepage. */
(function () {
  'use strict';
  function price(cents, ccy) { return (window.formatPrice ? formatPrice(cents, ccy) : ('£' + (cents / 100).toFixed(2))) }
  async function covers() {
    const grid = document.getElementById('cover-grid');
    if (!grid) return;
    try {
      const d = await api('/books?page_size=8&category=Classics');
      const items = d.items || [];
      if (!items.length) throw new Error('empty');
      grid.innerHTML = items.map(b => {
        const src = b.cover_path || b.cover_url;
        const cover = src && /^https?:\/\//.test(src)
          ? `<img src="${src}" alt="Cover of ${(b.title || '').replace(/[<>&"]/g, '')}" loading="lazy" class="w-full h-full object-cover">`
          : `<div class="w-full h-full bg-[#ece9e3] flex items-center justify-center text-[#8a8683] font-serif text-xl">${(b.title || '?').charAt(0)}</div>`;
        return `<a href="/books/${b.id}" class="block aspect-[3/4] bg-white border rounded-xl overflow-hidden hover:border-[#0b0b0c] transition" title="${(b.title || '').replace(/[<>&"]/g, '')}">${cover}</a>`;
      }).join('');
    } catch (e) {
      grid.innerHTML = '<p class="col-span-full py-6 text-center text-sm text-[#8a8683]">Covers are unavailable right now. <button id="covers-retry" class="underline">Try again</button></p>';
      const retry = document.getElementById('covers-retry');
      if (retry) retry.onclick = covers;
    }
  }
  async function featured() {
    const el = document.getElementById('featured-bundles');
    const controls = document.getElementById('featured-controls');
    try {
      const d = await api('/bundles?featured=true&page_size=100');
      let items = d.items || [];
      const d2 = await api('/bundles?page_size=100');
      const all = d2.items || [];
      const seen = new Set(items.map(b => b.slug));
      items = items.concat(all.filter(b => !seen.has(b.slug)));
      if (!items.length) { el.innerHTML = '<div class="col-span-full text-center py-12 border rounded-2xl bg-white"><p class="font-medium">No featured bundles</p></div>'; return }
      const PAGE = 6;
      const pages = [];
      for (let i = 0; i < items.length; i += PAGE) pages.push(items.slice(i, i + PAGE));
      let page = 0, timer = null;

      function card(b) {
        const n = Array.isArray(b.books) ? b.books.length : (b.book_count != null ? b.book_count : '?');
        // Use the bundle's OWN cover. Borrowing books[0].cover_path put an
        // unrelated member book's cover on the bundle, which is what made the
        // carousel look like the covers were shuffled onto the wrong bundles.
        const own = b.cover_image_path;
        const cover = own && /^https?:\/\//.test(own)
          ? `<img src="${own}" alt="" loading="lazy" class="w-full h-24 object-cover rounded-xl border">`
          : `<div class="w-full h-24 rounded-xl border border-[#ece9e3] bg-[#f6f4f0] flex items-center justify-center px-4">
               <span class="font-serif text-sm text-[#8a8683] text-center line-clamp-2">${(b.name || '').replace(/[<>&]/g, '')}</span>
             </div>`;
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
    } catch (e) {
      el.innerHTML = '<div class="col-span-full text-center py-10 border rounded-2xl bg-white"><p class="text-sm text-[#57534e]">Could not load bundles.</p><button id="bundles-retry" class="mt-3 text-sm underline">Try again</button></div>';
      const retry = document.getElementById('bundles-retry');
      if (retry) retry.onclick = featured;
    }
  }
  document.addEventListener('DOMContentLoaded', () => { covers(); featured(); });
})();