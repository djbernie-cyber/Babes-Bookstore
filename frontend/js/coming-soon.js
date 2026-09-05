/* Babe's Bookstore — Coming Soon enhancements
 * Shared helper for surfacing services that aren't fully integrated yet.
 * Drop a <div data-coming-soon="service-key"> anywhere; the helper injects a
 * consistent banner. Also exposes window.comingSoon() for programmatic use.
 */
(function () {
  'use strict';

  var SERVICES = {
    subscriptions: {
      title: 'Membership & subscriptions',
      copy: 'A membership tier for unlimited access is in development. For now it is one price, yours forever.',
      to: '/bundles'
    }
  };

  function bannerHtml(key, opts) {
    var s = SERVICES[key] || { title: key, copy: '', to: '/' };
    var title = (opts && opts.title) || s.title;
    var copy = (opts && opts.copy) || s.copy;
    var to = (opts && opts.to) || s.to;
    return '' +
      '<div class="coming-soon" role="status">' +
        '<span class="coming-soon-badge">Coming soon</span>' +
        '<span class="coming-soon-body">' +
          '<span class="coming-soon-title">' + title + '</span>' +
          '<span class="coming-soon-copy">' + copy + '</span>' +
        '</span>' +
        '<a class="coming-soon-link" href="' + to + '">Browse now</a>' +
      '</div>';
  }

  window.comingSoon = function (key, opts, host) {
    var el = host || document.body;
    var div = document.createElement('div');
    div.innerHTML = bannerHtml(key, opts);
    el.appendChild(div.firstChild);
    return div.firstChild;
  };

  function enhance() {
    var nodes = document.querySelectorAll('[data-coming-soon]');
    Array.prototype.forEach.call(nodes, function (el) {
      if (el.dataset.comingSoonDone) return;
      el.dataset.comingSoonDone = '1';
      var key = el.getAttribute('data-coming-soon');
      el.innerHTML = bannerHtml(key, {});
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhance);
  } else {
    enhance();
  }
})();
