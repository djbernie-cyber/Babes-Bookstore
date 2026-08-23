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
})();
