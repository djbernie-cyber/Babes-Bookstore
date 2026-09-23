/* Babe's Bookstore — super-admin censorship review queue.
   Loads /api/v1/admin/banned-records, lets a super-admin verify or reject
   reader-flagged entries, and refreshes the count from the live catalog. */
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  var loading = document.getElementById('records-loading');
  var empty = document.getElementById('records-empty');
  var tableWrap = document.getElementById('records-table-wrap');
  var body = document.getElementById('records-body');
  var pendingOnly = document.getElementById('pending-only');

  function expired() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    location.href = '/login';
  }

  function toast(msg) {
    var t = document.createElement('div');
    t.textContent = msg;
    t.className = 'fixed bottom-6 right-6 bg-stone-900 text-white text-sm px-5 py-3 rounded-xl shadow-lg z-50';
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3500);
  }

  function recordRow(r) {
    var b = r.book || {};
    var tds =
      '<td class="px-5 py-4"><a href="/books/' + b.id + '" class="font-medium text-stone-900 hover:text-amber-700">' + esc(b.title) + '</a><p class="text-xs text-stone-500 mt-1">' + esc(b.author || '') + '</p></td>' +
      '<td class="px-5 py-4"><span class="inline-flex px-2 py-1 rounded-full bg-stone-100 text-xs font-medium">' + esc(r.country_code || '—') + ' · ' + esc(r.country_name || '') + '</span></td>' +
      '<td class="px-5 py-4"><span class="inline-flex px-2 py-1 rounded-full ' + (r.status === 'banned' ? 'bg-red-100 text-red-700' : r.status === 'restricted' ? 'bg-amber-100 text-amber-700' : 'bg-stone-100 text-stone-600') + ' text-xs font-medium">' + esc(r.status || '') + '</span></td>' +
      '<td class="px-5 py-4 max-w-[260px]"><p class="line-clamp-3 text-stone-600">' + esc(r.ban_reason || '—') + '</p></td>' +
      '<td class="px-5 py-4 text-xs text-stone-500">' + esc(r.proposed_by || 'seed') + '</td>' +
      '<td class="px-5 py-4">' + (r.source_url ? '<a href="' + esc(r.source_url) + '" target="_blank" rel="noopener" class="text-xs text-amber-700 hover:underline truncate block max-w-[140px]">' + esc(r.source_url.replace(/^https?:\/\//, '')) + '</a>' : '<span class="text-stone-400 text-xs">—</span>') + '</td>' +
      '<td class="px-5 py-4 whitespace-nowrap"><div class="flex gap-2">' +
        '<button data-act="verify" data-id="' + r.id + '" data-title="' + esc(b.title) + '" class="px-3 py-1.5 rounded-lg bg-amber-700 text-white text-xs font-medium hover:bg-amber-800">Verify</button>' +
        '<button data-act="reject" data-id="' + r.id + '" data-title="' + esc(b.title) + '" class="px-3 py-1.5 rounded-lg border border-stone-300 text-red-600 text-xs font-medium hover:bg-red-50">Reject</button>' +
      '</div></td>';
    return '<tr class="border-t border-stone-100 hover:bg-stone-50">' + tds + '</tr>';
  }

  async function load(showPending) {
    loading.classList.remove('hidden');
    empty.classList.add('hidden');
    tableWrap.classList.add('hidden');
    try {
      var res = await fetch('/api/v1/admin/banned-records?pending_only=' + (showPending ? 'true' : 'false'), { headers: authHeaders() });
      if (res.status === 401) { expired(); return; }
      if (res.status === 403) { document.getElementById('access-denied').classList.remove('hidden'); return; }
      if (!res.ok) throw new Error('Failed to load records');
      var data = await res.json();
      var items = data.items || [];
      loading.classList.add('hidden');
      if (!items.length) { empty.classList.remove('hidden'); return; }
      body.innerHTML = items.map(recordRow).join('');
      tableWrap.classList.remove('hidden');
    } catch (e) {
      loading.classList.add('hidden');
      toast(e.message || 'Failed to load records');
    }
  }

  async function act(id, action, title) {
    if (!window.confirm((action === 'verify' ? 'Verify' : 'Reject') + ' the ' + title + ' record?')) return;
    try {
      var res = await fetch('/api/v1/admin/banned-records/' + id + '/review', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
        body: JSON.stringify({ action: action }),
      });
      if (res.status === 401) { expired(); return; }
      if (!res.ok) throw new Error('Action failed');
      toast(action === 'verify' ? 'Record verified and published.' : 'Record rejected and removed.');
      load(pendingOnly.checked);
    } catch (e) {
      toast(e.message);
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (!localStorage.getItem('token')) {
      document.getElementById('access-denied').classList.remove('hidden');
      return;
    }
    document.getElementById('admin-content').classList.remove('hidden');
    load(pendingOnly.checked);
    pendingOnly.addEventListener('change', function () { load(pendingOnly.checked); });
    body.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-act]');
      if (btn) act(Number(btn.dataset.id), btn.dataset.act, btn.dataset.title);
    });
  });
})();