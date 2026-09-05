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
    return fetch('/api/v1' + path, init).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (data) {
        if (!r.ok) {
          var e = new Error((data && data.detail) || ('Request failed (' + r.status + ')'));
          e.status = r.status; e.body = data;
          throw e;
        }
        return data;
      });
    });
  };

  window.isSignedIn = function () { return !!localStorage.getItem('token'); };
})();