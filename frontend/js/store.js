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
})();
