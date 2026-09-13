function logout(){ localStorage.removeItem('token'); localStorage.removeItem('user'); location.href='/login' }
function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
const $=id=>document.getElementById(id);
function coverHtml(b, h){
  const ok=b&&b.cover_url&&/^https?:\/\//.test(b.cover_url);
  return ok?`<img src="${b.cover_url}" alt="${esc(b.title)}" loading="lazy" class="w-full ${h} object-cover rounded-xl border">`
    :`<div class="w-full ${h} bg-[#ece9e3] rounded-xl grid place-items-center text-[#8a8683] font-serif text-3xl">${esc((b.title||'?').charAt(0).toUpperCase())}</div>`;
}
function stars(n){ let s=''; for(let i=1;i<=5;i++) s+= i<=Math.round(n||0)?'★':'☆'; return `<span class="text-amber-500">${s}</span>`; }
function bookLink(b){ return `/read/${b.id}`; }

/* ── State ─────────────────────────────────────────────────────────── */
let LIB={ shelves:[], activeShelfId:null, prefTheme:'sepia', prefSize:'m' };

async function init(){
  const t=localStorage.getItem('token'), s=localStorage.getItem('user');
  if(!t||!s){ $('logged-out').classList.remove('hidden'); return }
  let u; try{ u=JSON.parse(s) }catch(er){ logout(); return }
  $('logged-in').classList.remove('hidden');
  $('uname').textContent=u.name||u.email||'User';
  $('uemail').textContent=u.email||'';
  $('avatar').textContent=(u.name||u.email||'U').charAt(0).toUpperCase();
  if(u.is_admin) $('badge-admin').classList.remove('hidden');
  await Promise.all([loadPrefs(), loadSummary(), loadShelves(), loadContinue(), loadReviews()]);
}

async function loadPrefs(){
  try{
    const p=await api('/library/prefs');
    $('pref-theme').value=p.theme||'sepia';
    $('pref-size').value=p.reader_font_size||'m';
    LIB.prefTheme=p.theme||'sepia'; LIB.prefSize=p.reader_font_size||'m';
  }catch(e){}
}

document.addEventListener('DOMContentLoaded',function(){
  $('pref-theme').addEventListener('change',savePrefs);
  $('pref-size').addEventListener('change',savePrefs);
  $('shelf-new').addEventListener('submit',async function(ev){
    ev.preventDefault(); const n=$('shelf-name').value.trim(); if(!n) return;
    try{ await api('/library',{method:'POST',body:{name:n}}); $('shelf-name').value=''; await Promise.all([loadShelves(),loadSummary()]); }
    catch(err){ alert(err.message) }
  });
  $('shelf-rename').addEventListener('click',function(){ const s=LIB.shelves.find(x=>x.id===LIB.activeShelfId); if(!s) return; const n=prompt('Rename shelf to:',s.name); if(n&&n.trim()) renameShelf(s.id,n.trim()); });
  $('shelf-delete').addEventListener('click',async function(){ const s=LIB.shelves.find(x=>x.id===LIB.activeShelfId); if(!s||s.is_default){ alert('The default shelf cannot be deleted.'); return } if(!confirm('Delete the "'+s.name+'" shelf? Books stay in the catalogue — this only removes the shelf.')) return; try{ await api('/library/'+s.id,{method:'DELETE'}); await loadShelves(); }catch(err){ alert(err.message) } });
});

async function savePrefs(){
  const theme=$('pref-theme').value, size=$('pref-size').value;
  LIB.prefTheme=theme; LIB.prefSize=size;
  document.documentElement.setAttribute('data-theme',theme);
  try{ localStorage.setItem('site-theme',theme); localStorage.setItem('reader-size',size); }catch(e){}
  try{
    await api('/library/prefs',{method:'PUT',body:{theme,reader_font_size:size}});
    const st=$('pref-status'); st.classList.remove('hidden'); setTimeout(()=>st.classList.add('hidden'),2200);
  }catch(err){ console.error(err) }
}

async function loadSummary(){
  try{
    const d=await api('/library/summary');
    $('stat-saved').textContent=(d.total_saved||0).toLocaleString();
    $('stat-reading').textContent=(d.in_progress||0).toLocaleString();
    $('stat-shelves').textContent=(d.shelves||[]).length.toLocaleString();
    $('shelf-count').textContent=(d.shelves||[]).length+' shelf'+(d.shelves&&d.shelves.length!==1?'s':'');
  }catch(e){}
}

async function loadShelves(){
  try{
    const d=await api('/library');
    LIB.shelves=d.items||[];
    assignSummaryShelves();
    const el=$('shelves'); el.innerHTML=LIB.shelves.map(s=>`
      <button data-sid="${s.id}" class="shelf-tab w-full flex items-center justify-between gap-2 text-left px-3 py-2.5 rounded-xl border text-sm font-medium hover:bg-stone-50">
        <span class="truncate">${s.is_default?'♡ ':''}${esc(s.name)}</span><span class="text-xs font-semibold text-stone-400">${s.book_count||0}</span>
      </button>`).join('');
    el.querySelectorAll('.shelf-tab').forEach(b=>b.addEventListener('click',()=>openShelf(Number(b.dataset.sid))));
    if(!LIB.shelves.some(x=>x.id===LIB.activeShelfId)){ const def=LIB.shelves.find(x=>x.is_default)||LIB.shelves[0]; LIB.activeShelfId=def?def.id:null; }
    openShelf(LIB.activeShelfId);
  }catch(err){}
}

async function assignSummaryShelves(){
  /* summary carries authoritative per-shelf counts; fold into LIB.shelves */
  try{
    const d=await api('/library/summary');
    const counts={}; (d.shelves||[]).forEach(s=>counts[s.id]=s.book_count);
    LIB.shelves.forEach(s=>{ if(counts[s.id]!=null) s.book_count=counts[s.id]; });
  }catch(e){}
}

async function openShelf(id){
  if(!id) return;
  LIB.activeShelfId=id;
  document.querySelectorAll('.shelf-tab').forEach(b=>{
    const on=Number(b.dataset.sid)===id;
    b.classList.toggle('bg-stone-900',on); b.classList.toggle('text-white',on);
    b.classList.toggle('bg-white',!on);
  });
  const s=LIB.shelves.find(x=>x.id===id); if(!s) return;
  $('shelf-title').textContent=(s.is_default?'♡ ':'')+s.name;
  $('shelf-rename').classList.toggle('hidden',s.is_default);
  $('shelf-delete').classList.toggle('hidden',s.is_default);
  try{
    const d=await api('/library/'+id+'/books?page_size=60');
    const items=d.items||[];
    const empty=$('shelf-books-empty'), box=$('shelf-books');
    if(!items.length){ empty.classList.remove('hidden'); box.classList.add('hidden'); box.innerHTML=''; return }
    empty.classList.add('hidden'); box.classList.remove('hidden');
    box.innerHTML=items.map(b=>`
      <div class="bg-stone-50 border rounded-2xl p-3">
        <a href="${bookLink(b)}">${coverHtml(b,'h-32')}</a>
        <a href="${bookLink(b)}" class="block mt-2 font-serif font-semibold leading-tight hover:underline">${esc(b.title)}</a>
        <p class="text-xs text-stone-500 mt-0.5 truncate">${esc(b.author)}</p>
        <div class="mt-3 flex gap-2">
          <a href="${bookLink(b)}" class="flex-1 text-center px-3 py-2 rounded-full bg-stone-900 text-white text-xs font-semibold">Read</a>
          <button data-rm="${b.id}" class="px-3 py-2 rounded-full border text-xs font-semibold text-stone-500 hover:text-red-600 hover:border-red-200">Remove</button>
        </div>
      </div>`).join('');
    box.querySelectorAll('[data-rm]').forEach(btn=>btn.addEventListener('click',()=>removeFromShelf(id,Number(btn.dataset.rm))));
  }catch(err){ console.error(err) }
}

async function removeFromShelf(shelfId,bookId){
  try{
    await api(`/library/${shelfId}/books/${bookId}`,{method:'DELETE'});
    await openShelf(shelfId); await loadSummary();
  }catch(err){ alert(err.message) }
}

async function renameShelf(id,name){
  try{ await api('/library/'+id,{method:'PATCH',body:{name}}); await loadShelves(); await loadSummary(); }catch(err){ alert(err.message) }
}

async function loadContinue(){
  try{
    const d=await api('/library/continue-reading?page_size=12');
    const items=d.items||[];
    const empty=$('continue-empty'), list=$('continue-list');
    if(!items.length){ empty.classList.remove('hidden'); return }
    empty.classList.add('hidden'); list.classList.remove('hidden');
    list.innerHTML=items.map(x=>{
      const pct=Math.round((x.percent||0)*100);
      return `<a href="/read/${x.id}" class="block bg-white border rounded-2xl p-4 hover:border-[#0b0b0c] transition">
        <div class="flex gap-3">
          ${x.cover_url&&/^https?:\/\//.test(x.cover_url)?`<img src="${x.cover_url}" class="w-16 h-24 object-cover rounded-lg border shrink-0">`:`<div class="w-16 h-24 bg-[#ece9e3] rounded-lg grid place-items-center text-[#8a8683] font-serif text-2xl shrink-0">${esc((x.title||'?').charAt(0))}</div>`}
          <div class="min-w-0 flex-1"><h3 class="font-serif font-semibold leading-tight">${esc(x.title)}</h3><p class="text-xs text-stone-500 mt-0.5 truncate">${esc(x.author)}</p>
            <div class="mt-2 h-1.5 bg-stone-200 rounded-full overflow-hidden"><div class="h-full bg-stone-900 rounded-full" style="width:${pct}%"></div></div>
            <p class="text-xs font-semibold mt-1">${pct}% · ${x.percent_label||''}</p></div></div>
      </a>`;
    }).join('');
  }catch(e){}
}

async function loadReviews(){
  try{
    const d=await api('/library/my-reviews');
    const items=d.items||[];
    const empty=$('rev-empty'), list=$('rev-list');
    if(!items.length){ empty.classList.remove('hidden'); return }
    empty.classList.add('hidden'); list.classList.remove('hidden');
    list.innerHTML=items.map(r=>`
      <div class="border rounded-2xl p-4">
        <div class="flex items-start justify-between gap-2">
          ${stars(r.rating)}<button data-del="${r.book&&r.book.id}" class="text-xs font-semibold text-stone-400 hover:text-red-600">Delete</button>
        </div>
        ${r.title?`<p class="font-semibold text-sm mt-1">${esc(r.title)}</p>`:''}
        ${r.body?`<p class="text-sm text-stone-500 mt-1 line-clamp-2">${esc(r.body)}</p>`:''}
        <a href="${bookLink(r.book)}" class="block mt-2 text-xs font-medium underline">${esc(r.book&&r.book.title)}</a>
      </div>`).join('');
    $('stat-reviews').textContent=d.total.toLocaleString();
    list.querySelectorAll('[data-del]').forEach(btn=>btn.addEventListener('click',async function(){
      try{ await api('/books/'+btn.dataset.del+'/reviews/mine',{method:'DELETE'}); loadReviews(); }catch(err){ alert(err.message) }
    }));
  }catch(e){}
}

document.addEventListener('DOMContentLoaded', init);
