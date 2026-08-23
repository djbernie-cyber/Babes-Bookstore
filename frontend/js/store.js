(function () {
    'use strict';

    var CURRENCY_SYMBOLS = { GBP: '\u00A3', USD: '$', EUR: '\u20AC' };

    function currencySymbol(currency) {
        var code = (currency || 'GBP').toUpperCase();
        return CURRENCY_SYMBOLS[code] || code + ' ';
    }

    window.formatPrice = function (cents, currency) {
        var amount = (Number(cents) || 0) / 100;
        return currencySymbol(currency) + amount.toFixed(2);
    };

    window.currencySymbol = currencySymbol;

    function setCopyrightYears() {
        var nodes = document.querySelectorAll('[data-copyright-year]');
        var year = new Date().getFullYear().toString();
        nodes.forEach(function (n) { n.textContent = year; });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setCopyrightYears);
    } else {
        setCopyrightYears();
    }

    function enhanceChrome() {
        var nav = document.querySelector('nav');
        if (nav && !nav.dataset.enhanced) {
            nav.dataset.enhanced = '1';
            var onScroll = function () {
                nav.classList.toggle('scrolled', window.scrollY > 8);
            };
            window.addEventListener('scroll', onScroll, { passive: true });
            onScroll();
        }

        var revealables = document.querySelectorAll(
            'section > div > div, .bundle-card, .book-card'
        );
        if ('IntersectionObserver' in window) {
            revealables.forEach(function (el, i) {
                if (el.classList.contains('reveal') || el.closest('nav')) return;
                el.classList.add('reveal');
                el.style.transitionDelay = Math.min(i * 45, 270) + 'ms';
                observer.observe(el);
            });
        } else {
            revealables.forEach(function (el) { el.classList.add('revealed'); });
        }
    }

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add('revealed');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', enhanceChrome);
    } else {
        enhanceChrome();
    }

    // Honest, live marketing numbers — never hardcode a claim the
    // catalogue can't back up. Pulled from the public API.
    function refreshLiveStats() {
        fetch('/api/v1/books?page_size=1').then(function (r) { return r.json(); })
            .then(function (d) {
                var n = d && d.total;
                var el = document.querySelector('[data-live-books]');
                if (el && typeof n === 'number') {
                    el.textContent = n.toLocaleString() + (n === 1 ? ' book' : ' books');
                }
            }).catch(function () {});

        fetch('/api/v1/checkout/config').then(function (r) { return r.json(); })
            .then(function (cfg) {
                if (!cfg) return;
                // Google sign-in only works once OAuth is configured.
                var googleOn = !!cfg.google_client_id;
                document.querySelectorAll('.google-btn').forEach(function (b) {
                    b.style.display = googleOn ? '' : 'none';
                });
                var payEl = document.querySelector('[data-live-payments]');
                if (payEl) {
                    var methods = [];
                    if (cfg.stripe_publishable_key) { methods.push('Card'); methods.push('Apple Pay', 'Google Pay'); }
                    if (cfg.paypal_client_id) methods.push('PayPal');
                    if (cfg.square_application_id) methods.push('Square');
                    payEl.textContent = methods.length ? methods.length + (methods.length === 1 ? ' way to pay' : ' ways to pay') : 'Payments launching soon';
                }
            }).catch(function () {});
    }
    refreshLiveStats();
})();
