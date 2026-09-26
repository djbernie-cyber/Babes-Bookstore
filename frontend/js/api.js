/* Shared API helper for the storefront.
   Talks to /api/v1/* (proxied to Fly.io by _redirects) with the JWT when
   signed in. Usage:
     api('/books/1342')                    -> json
     api('/library/create', {method:'POST', body:{name:'...'}})
   Throws an Error whose .status is the HTTP status and .body the parsed
   JSON payload on non-2xx responses. */
(function () {
  'use strict';

  window.authHeaders = function () {
    var t = localStorage.getItem('token');
    return t ? { 'Authorization': 'Bearer ' + t } : {};
  };

  function describe(data, status) {
    var detail = data && data.detail;
    if (detail && typeof detail === 'object') {
      // 410 withdrawn payloads carry {code, reason}; Error(object) would
      // stringify to "[object Object]".
      detail = detail.reason || detail.message || detail.code;
    }
    if (Array.isArray(detail)) {
      detail = detail.map(function (d) {
        return d && typeof d === 'object' ? (d.msg || JSON.stringify(d)) : d;
      }).join('; ');
    }
    return detail || ('Request failed (' + status + ')');
  }

  window.api = function (path, opts) {
    opts = opts || {};
    var headers = {};
    if (opts.body && typeof opts.body !== 'string') {
      headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    headers = Object.assign(headers, opts.body ? headers : {}, window.authHeaders());
    var init = { method: opts.method || 'GET', headers: headers };
    if (opts.body !== undefined) init.body = opts.body;

    // Without a deadline a request that never settles leaves its spinner up
    // forever, so an outage looks like a page that is still thinking rather
    // than a page that is broken.
    var controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    if (controller) init.signal = controller.signal;
    var timer = setTimeout(function () { if (controller) controller.abort(); }, opts.timeout || 15000);

    return fetch('/api/v1' + path, init).then(function (r) {
      return r.text().then(function (raw) {
        var data = null;
        try { data = raw ? JSON.parse(raw) : null; } catch (e) { data = null; }
        if (!r.ok) {
          var err = new Error(describe(data, r.status));
          err.status = r.status; err.body = data;
          throw err;
        }
        return data;
      });
    }).catch(function (err) {
      if (err && err.status) throw err;            // already a real API error
      var e2 = new Error(
        err && err.name === 'AbortError'
          ? 'The server took too long to respond. Please try again.'
          : 'Could not reach the server. Please check your connection and try again.'
      );
      e2.status = 0;
      throw e2;
    }).finally(function () { clearTimeout(timer); });
  };

  window.isSignedIn = function () { return !!localStorage.getItem('token'); };
})();