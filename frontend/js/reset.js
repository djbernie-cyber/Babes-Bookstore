/* Babe's Bookstore — password reset page logic.
   The page's CSP blocks inline scripts, so this lives as an external file.
   Handles both halves: requesting the reset email and setting a new
   password from the emailed link. */
(function () {
  'use strict';

  var token = new URLSearchParams(location.search).get('token');

  function resetView() {
    document.getElementById('email-view').classList.add('hidden');
    document.getElementById('reset-view').classList.remove('hidden');
  }

  window.addEventListener('DOMContentLoaded', function () {
    if (token) resetView();

    var forgot = document.getElementById('forgot-form');
    if (forgot) {
      forgot.addEventListener('submit', async function (e) {
        e.preventDefault();
        var msg = document.getElementById('forgot-msg');
        msg.classList.remove('hidden');
        msg.textContent = 'Sending…';
        try {
          var r = await fetch('/api/v1/auth/forgot-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: document.getElementById('email').value }),
          });
          if (!r.ok) throw new Error(r.status);
          document.getElementById('email-view').innerHTML =
            '<h1 class="font-serif text-3xl font-bold tracking-[-.02em]">Check your inbox</h1>' +
            '<p class="text-sm text-stone-600 mt-2 leading-6">If that address has an account, a reset link is on its way. The link expires in 30 minutes.</p>' +
            '<a href="/login" class="inline-block mt-6 text-sm font-medium underline">Back to login</a>';
        } catch (err) {
          msg.textContent = 'Something went wrong sending that. Please try again.';
        }
      });
    }

    var reset = document.getElementById('reset-form');
    if (reset) {
      reset.addEventListener('submit', async function (e) {
        e.preventDefault();
        var msg = document.getElementById('reset-msg');
        msg.classList.remove('hidden');
        msg.textContent = 'Saving…';
        try {
          var r = await fetch('/api/v1/auth/reset-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: token, password: document.getElementById('pw').value }),
          });
          if (!r.ok) throw new Error(r.status);
          var d = await r.json();
          localStorage.setItem('token', d.access_token);
          localStorage.setItem('user', JSON.stringify(d.user || {}));
          location.href = '/account';
        } catch (err) {
          msg.textContent = 'That link is invalid or has expired. Please request a new one.';
        }
      });
    }
  });
})();