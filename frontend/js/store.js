(function () {
  'use strict';
  var SYM = { GBP: '£', USD: '$', EUR: '€' };
  function sym(ccy){ var c=(ccy||'GBP').toUpperCase(); return SYM[c]||c+' '; }
  window.formatPrice=function(cents,ccy){ var a=(Number(cents)||0)/100; return sym(ccy)+a.toFixed(2); };
  window.currencySymbol=sym;

  function year(){ var n=document.querySelectorAll('[data-copyright-year]'); var y=new Date().getFullYear().toString(); n.forEach(function(e){ e.textContent=y; }); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',year); else year();

  function chrome(){
    var nav=document.querySelector('nav');
    if(nav&&!nav.dataset.enhanced){ nav.dataset.enhanced='1'; var f=function(){ nav.classList.toggle('scrolled', scrollY>8)}; addEventListener('scroll',f,{passive:true}); f(); }
    var els=document.querySelectorAll('section > div > div, .bundle-card, .book-card');
    if('IntersectionObserver' in window){
      var io=new IntersectionObserver(function(es){ es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('revealed'); io.unobserve(e.target); } }); },{threshold:.12, rootMargin:'0px 0px -40px 0px'});
      els.forEach(function(el,i){ if(el.classList.contains('reveal')||el.closest('nav')) return; el.classList.add('reveal'); el.style.transitionDelay=Math.min(i*45,270)+'ms'; io.observe(el); });
    } else els.forEach(function(e){ e.classList.add('revealed'); });
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',chrome); else chrome();

   function live(){
     fetch('/api/v1/books?page_size=1&_='+Date.now()).then(function(r){return r.json()}).then(function(d){
       var n=d&&d.total; if(typeof n!=='number') return;
       var fmt=n.toLocaleString();
       document.querySelectorAll('[data-live-books]').forEach(function(el){ el.textContent=fmt + (el.tagName==='P'&&el.classList.contains('font-serif')? '': (n===1?' book':' books')); });
       // hero count
       var h=document.getElementById('hero-live-count'); if(h) h.textContent=fmt+' books live';
       var pc=document.getElementById('progress-count'); if(pc) pc.textContent=fmt;
       var pp=document.getElementById('progress-pct'); if(pp) pp.textContent=(n/90000*100).toFixed(1)+'%';
       var pf=document.getElementById('progress-fill'); if(pf) pf.style.width=Math.min(100, n/90000*100).toFixed(1)+'%';
       // search placeholder
       document.querySelectorAll('input[placeholder*="62,000"]').forEach(function(i){ i.placeholder='Search '+fmt+' books…'; });
     }).catch(function(){});

     fetch('/api/v1/checkout/config?_='+Date.now()).then(function(r){return r.json()}).then(function(c){
      if(!c) return;
      var on=!!c.google_client_id;
      document.querySelectorAll('.google-btn').forEach(function(b){ b.style.display=on?'':'none'; });
      // if google off, show hint
      document.querySelectorAll('[data-google-hint]').forEach(function(h){ h.style.display=on?'none':''; });
      var el=document.querySelector('[data-live-payments]');
      if(el){
        var m=[]; if(c.stripe_publishable_key) { m.push('Card'); m.push('Apple Pay','Google Pay'); }
        if(c.paypal_client_id) m.push('PayPal'); if(c.square_application_id) m.push('Square');
        el.textContent=m.length? m.length+(m.length===1?' way to pay':' ways to pay') : 'Payments launching soon';
      }
    }).catch(function(){});
  }
  live();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(function() {});
  }

  // ─── Cookie consent (GDPR / CCPA) ─────────────────────────────────────────
  var CK_KEY = 'cookie-consent-v1';
  function cookieBanner(){
    if(document.getElementById('cookie-banner')) return;      // already injected
    var saved = localStorage.getItem(CK_KEY);                  // 'all' | 'necessary'
    if(saved) return;                                          // already decided
    var div = document.createElement('div');
    div.id = 'cookie-banner';
    div.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:9999;'+
      'background:#0b0b0c;color:#f5f5f4;padding:16px 20px;font-family:Inter,sans-serif;'+
      'font-size:14px;line-height:1.5;box-shadow:0 -6px 24px rgba(0,0,0,.18)';
    var wrap = document.createElement('div');
    wrap.style.cssText = 'max-width:1180px;margin:0 auto;display:flex;flex-wrap:wrap;'+
      'gap:12px;align-items:center;justify-content:space-between';
    var txt = document.createElement('p');
    txt.style.cssText = 'max-width:720px;margin:0;color:#d6d3d1';
    txt.innerHTML = 'We use essential cookies to keep your cart, purchases and sign-in secure, and optional'+
      ' analytics cookies to improve the site. You can change your choice anytime in our '+
      '<a href="/legal/cookie-policy.html" style="color:#fff;text-decoration:underline">Cookie Policy</a>.';
    var btns = document.createElement('div');
    btns.style.cssText = 'display:flex;gap:10px;flex-wrap:wrap';
    function mk(label, val, primary){
      var b=document.createElement('button');
      b.textContent=label; b.type='button';
      b.style.cssText = 'padding:8px 18px;border-radius:999px;font-size:13px;font-weight:600;cursor:pointer;'+
        (primary ? 'background:#fff;color:#0b0b0c;border:1px solid #fff'
                 : 'background:transparent;color:#e7e5e4;border:1px solid #57534e');
      b.onclick=function(){ try{ localStorage.setItem(CK_KEY, val); }catch(_){} div.remove(); };
      return b;
    }
    btns.appendChild(mk('Accept all', 'all', true));
    btns.appendChild(mk('Essential only', 'necessary', false));
    wrap.appendChild(txt); wrap.appendChild(btns); div.appendChild(wrap);
    document.body.appendChild(div);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',cookieBanner); else cookieBanner();
})();
