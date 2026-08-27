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
})();
