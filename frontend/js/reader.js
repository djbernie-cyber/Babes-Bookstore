function bookId(){
  var p=location.pathname.split('/').filter(Boolean);
  // /read/{id} -> last is id ; /books/{id}/read -> second-to-last is id
  if(p[p.length-1]==='read' && p.length>=3) return p[p.length-2];
  return p[p.length-1];
}
function reportProgress(id){
  var t=token(); if(!t) return;
  var max=(document.body.scrollHeight||1)-(window.innerHeight||1);
  if(max<=0) return;
  var p=Math.max(0, Math.min(0.98, (scrollY||0)/max));
  fetch('/api/v1/library/progress/'+encodeURIComponent(id),{
    method:'PUT', headers:{'Authorization':'Bearer '+t,'Content-Type':'application/json'},
    body:JSON.stringify({percent:Math.round(p*100)/100, position:'para-'+Math.round(p*1000)})
  }).catch(function(){});
}
var _reporting=false;
addEventListener('scroll',function(){
  if(_reporting) return; _reporting=true;
  setTimeout(function(){ _reporting=false; reportProgress(bookId()); },1200);
},{passive:true});function setPrefs(){
  var s=localStorage.getItem('reader-size')||'m', t=localStorage.getItem('reader-theme')||'sepia';
  document.documentElement.setAttribute('data-size',s);
  document.documentElement.setAttribute('data-theme',t);
  document.querySelectorAll('.fs-btn button').forEach(function(b){ b.classList.toggle('active', b.dataset.size===s) });
  document.getElementById('theme').value=t;
}
function token(){ return localStorage.getItem('token'); }
function saveAccountPrefs(){
  var t=token(); if(!t) return;
  var s=localStorage.getItem('reader-size')||'m', th=localStorage.getItem('reader-theme')||'sepia';
  fetch('/api/v1/library/prefs',{method:'PUT',headers:{'Authorization':'Bearer '+t,'Content-Type':'application/json'},
    body:JSON.stringify({theme:th,reader_font_size:s})}).catch(function(){});
}
function loadAccountPrefs(){
  var t=token(); if(!t){ setPrefs(); return; }
  fetch('/api/v1/library/prefs',{headers:{'Authorization':'Bearer '+t}}).then(function(r){
    if(!r.ok) throw 0; return r.json();
  }).then(function(p){
    if(p && p.theme) localStorage.setItem('reader-theme', p.theme);
    if(p && p.reader_font_size) localStorage.setItem('reader-size', p.reader_font_size);
    setPrefs();
  }).catch(function(){ setPrefs(); });
}
function tidy(html){
  // render as paragraphs in a fixed font-size container, stripping inline frames but keeping <p>
  var doc=new DOMParser().parseFromString(html,'text/html');
  var body=doc.body||doc;
  var paras=[];
  body.querySelectorAll('p').forEach(function(p){ paras.push(p.textContent) });
  if(!paras.length) paras=[body.textContent];
  return paras.map(function(t){ return t.replace(/^\s+|\s+$/g,'') }).filter(Boolean);
}
async function load(){
  var id=bookId();
  var loading=document.getElementById('loading'), err=document.getElementById('err'), content=document.getElementById('content');
  try{
    // Fetch meta first: we gate suppressed works before pulling any text.
    var meta={title:'',author:''};
    try{ var m=await (await fetch('/api/v1/books/'+id)).json(); meta=m; }catch(e){}
    document.documentElement.title=(meta.title||'Read')+" — Babe's Bookstore";
    var suppressed=(meta.tags||[]).some(function(t){ return /suppress|banned/i.test(t) });
    if(suppressed && !localStorage.getItem('bb-spp-'+id)){
      var gate=document.getElementById('suppressed-gate');
      loading.style.display='none'; gate.style.display='block';
      document.getElementById('suppressed-acknowledge').addEventListener('click',function(){
        localStorage.setItem('bb-spp-'+id,'1');
        gate.style.display='none'; load();
      },{once:true});
      return;
    }
    var r=await fetch('/api/v1/books/'+id+'/text');
    if(!r.ok) throw new Error((await r.json().catch(()=>({}))).detail||('HTTP '+r.status));
    var html=await r.text();
    document.getElementById('book-title').textContent=(meta.title||'') + (meta.author? ' — '+meta.author : '');
    paras=tidy(html);
    if(!paras.length) paras=['No extractable text.'];
    rendered=0;
    document.getElementById('text-body').innerHTML='';
    loading.style.display='none'; content.style.display='block';
    renderChunk(); renderChunk();
    // back-to-top visibility
    addEventListener('scroll',function(){ document.getElementById('btt').style.display=scrollY>600?'block':'none'; },{passive:true});
    // turn the manual loader into an automatic one once the reader settles
    scoreMore();
  }catch(e){ loading.style.display='none'; err.style.display='block'; err.textContent='Could not load the text: '+e.message+'  —  try downloading the book instead.'; }
}
var paras=[], rendered=0, CHUNK=120, _busy=false;
function renderChunk(){
  var next=paras.slice(rendered, rendered+CHUNK);
  if(!next.length){ _busy=false; document.getElementById('more').style.display='none'; return; }
  rendered+=next.length;
  var p=document.createElement('div');
  p.textContent=next.join('\n\n');
  document.getElementById('text-body').appendChild(p);
  _busy=false;
  if(rendered>=paras.length) document.getElementById('more').style.display='none';
}
function loadMore(){ document.getElementById('more').style.display='inline-flex'; renderChunk(); }
function scoreMore(){
  addEventListener('scroll',function(){
    if(_busy||document.getElementById('more').style.display==='none') return;
    _busy=true;
    requestAnimationFrame(function(){
      var more=document.getElementById('more');
      if(more.getBoundingClientRect().top < window.innerHeight+500) renderChunk();
      else _busy=false;
    });
  },{passive:true});
}
document.querySelectorAll('.fs-btn button').forEach(function(b){ b.addEventListener('click',function(){ localStorage.setItem('reader-size',b.dataset.size); setPrefs(); saveAccountPrefs(); }); });
document.getElementById('theme').addEventListener('change',function(){ localStorage.setItem('reader-theme',this.value); setPrefs(); saveAccountPrefs(); });
loadAccountPrefs(); load();
