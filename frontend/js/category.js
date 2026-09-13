/* Babe's Bookstore — category page. */
function slugFromUrl() {
  var path = location.pathname.replace(/^\/categories\//, '').replace(/\/$/, '');
  return decodeURIComponent(path);
}
function titleFromSlug(s) {
  return s.split('-').map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1) }).join(' ');
}

var CATEGORY_DESCS = {
  'african-literature': 'A dedicated, curated canon of African-authored and African-diaspora writing — from Olaudah Equiano\'s pioneering narrative to Olive Schreiner and Sol T. Plaatje, and the great voices of the diaspora. Gathered from the public domain into one shelf.',
  'classics': 'The foundational works of Western literature — Homer, Dante, Austen, Tolstoy, Shakespeare and beyond. Cleaned, typeset, and ready for serious reading.',
  'science-fiction': 'From Verne and Wells to the golden-age pulp masters. Public-domain speculations on technology, society and the cosmos.',
  'poetry': 'Verse from every era — sonnets, epics, odes and free verse. Homer to Whitman, Sappho to Yeats.',
  'philosophy': 'The great thinkers from Plato to Nietzsche, in clean scholarly editions.',
  'history': 'Chronicles, memoirs and analyses spanning ancient civilisations to the early twentieth century.',
  'biography': 'Lives lived extraordinary and ordinary — autobiography, memoir and biography from the public domain.',
  'mystery-detective': 'The origins of detective fiction — Poe, Christie\'s early contemporaries, and the locked-room classics.',
  'fantasy': 'Myth, legend andchantment — from ancient epics to the genre\'s early architects.',
  'gothic-horror': 'Gothic mansions, creeping dread and the macabre — Shelley, Stoker, Poe and the whole dark tradition.',
  'romance': 'Love stories across the centuries — Austen, the Brontës, and the roots of the genre.',
  'adventure': 'Sea voyages, explorations and swashbuckling tales from the age of adventure.',
  'children-fairy-tales': 'Fables, fairy tales and children\'s classics — Andersen, Grimm, Carroll and beyond.',
  'drama': 'Plays and dramatic works from Sophocles to Shaw.',
  'non-fiction': 'Essays, science, travel writing and general non-fiction from the public domain.',
  'revolutionary': 'Writers banned, imprisoned, exiled or killed by their own states — Marx, Luxemburg, McKay, Goldman, Fanon, Sankara and the political canon that official systems declared dangerous. Each work is public-domain or openly licensed.'
};

//: Categories backed by a book *tag* (the ``category`` column is a subject
//: shelf; the political shelves live in tags).
var TAG_CATS = {
  'revolutionary': 'Revolutionary'
};

function descFor(slug) {
  return CATEGORY_DESCS[slug] || 'A curated collection of public-domain and openly-licensed books in this category.';
}

function coverHtml(b) {
  if (b.cover_path && /^https?:\/\//.test(b.cover_path)) {
    return '<img src="' + b.cover_path + '" alt="' + String(b.title).replace(/"/g, '&quot;') + '" class="w-full h-56 object-cover bg-[#f6f1e7]" loading="lazy">';
  }
  var letter = String(b.title || '?').charAt(0).toUpperCase();
  return '<div class="w-full h-56 bg-[#f6f1e7] border-b flex flex-col items-center justify-center p-4"><span class="font-serif text-5xl text-[#0b0b0c]">' + letter + '</span><span class="text-[11px] tracking-wide uppercase font-medium text-[#8a8683] mt-2 text-center line-clamp-2">' + b.title + '</span></div>';
}
function card(b) {
  return '<div class="book-card group overflow-hidden flex flex-col">' +
    '<a href="/books/' + b.id + '" class="block">' + coverHtml(b) + '</a>' +
    '<div class="p-4 flex-1 flex flex-col">' +
    '<a href="/books/' + b.id + '" class="font-serif font-semibold leading-tight line-clamp-2 hover:underline">' + b.title + '</a>' +
    '<p class="text-sm text-[#57534e] mt-1">' + (b.author || 'Unknown author') + '</p>' +
    '<div class="flex flex-wrap gap-1.5 mt-2">' + (b.category ? '<span class="text-[11px] px-2 py-1 rounded-full bg-white border text-[#57534e]">' + b.category + '</span>' : '') + (b.publication_year ? '<span class="text-xs text-[#8a8683]">' + b.publication_year + '</span>' : '') + '</div>' +
    '<div class="mt-3 flex gap-2">' +
    '<a href="/api/v1/books/' + b.id + '/download" class="flex-1 text-center text-xs font-semibold px-3 py-2 rounded-full bg-[#0b0b0c] text-white hover:bg-black">Free download</a>' +
    '<a href="/books/' + b.id + '" class="text-xs font-medium px-3 py-2 rounded-full border bg-white hover:bg-[#fcfaf7]">Preview</a>' +
    '</div>' +
    '</div>' +
    '</div>';
}

var curPage = 1;
var slug = slugFromUrl();
var catName = titleFromSlug(slug);
var realName = catName;

document.getElementById('cat-title').textContent = catName;
document.getElementById('cat-eyebrow').textContent = 'Category';
document.title = catName + ' — Babe\'s Bookstore';
document.getElementById('cat-desc').textContent = descFor(slug);

async function resolveCategory() {
  try {
    var r = await fetch('/api/v1/categories'); if (!r.ok) return;
    var d = await r.json();
    var hit = (d || []).find(function (c) { return c.slug === slug; });
    if (hit && hit.name) { realName = hit.name; }
  } catch (e) { }
}

async function load(page) {
  if (page) curPage = page;
  var loading = document.getElementById('loading'), err = document.getElementById('error'), res = document.getElementById('results'), empty = document.getElementById('empty'), meta = document.getElementById('meta'), pag = document.getElementById('pagination');
  loading.classList.remove('hidden'); err.classList.add('hidden'); res.innerHTML = ''; empty.classList.add('hidden'); meta.classList.add('hidden'); pag.innerHTML = '';
  var params = new URLSearchParams(); if (TAG_CATS[slug]) params.set('tag', TAG_CATS[slug]); else params.set('category', realName); params.set('page', curPage); params.set('page_size', '24');
  try {
    var r = await fetch('/api/v1/books?' + params.toString()); if (!r.ok) throw new Error(r.status);
    var d = await r.json(); var items = d.items || []; var total = d.total || 0;
    loading.classList.add('hidden');
    if (!items.length) { empty.classList.remove('hidden'); return }
    meta.textContent = items.length + ' of ' + total.toLocaleString() + ' titles shown'; meta.classList.remove('hidden');
    res.innerHTML = items.map(card).join('');
    var tp = Math.ceil(total / 24);
    if (tp > 1) { var h = ''; h += '<button data-action="load" data-arg-1="' + (curPage - 1) + '" ' + (curPage <= 1 ? 'disabled' : '') + ' class="px-4 py-2 rounded-full border bg-white text-sm ' + (curPage <= 1 ? 'opacity-40' : '') + '">Previous</button>';
      for (var i = Math.max(1, curPage - 2); i <= Math.min(tp, curPage + 2); i++) h += '<button data-action="load" data-arg-1="' + i + '" class="w-10 h-10 rounded-full text-sm ' + (i === curPage ? 'bg-stone-900 text-white' : 'border bg-white') + '">' + i + '</button>';
      if (curPage + 2 < tp) h += '<span class="text-stone-400">…</span><button data-action="load" data-arg-1="' + tp + '" class="w-10 h-10 rounded-full border bg-white text-sm">' + tp + '</button>';
      h += '<button data-action="load" data-arg-1="' + (curPage + 1) + '" ' + (curPage >= tp ? 'disabled' : '') + ' class="px-4 py-2 rounded-full border bg-white text-sm ' + (curPage >= tp ? 'opacity-40' : '') + '">Next</button>'; pag.innerHTML = h;
    }
  } catch (e) { loading.classList.add('hidden'); err.textContent = 'Could not load: ' + e.message; err.classList.remove('hidden') }
}
document.addEventListener('DOMContentLoaded', function () { resolveCategory().then(function () { load(1); }); });