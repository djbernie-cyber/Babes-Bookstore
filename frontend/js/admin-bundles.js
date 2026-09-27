        const token = localStorage.getItem('token');
        const user = JSON.parse(localStorage.getItem('user') || '{}');

        if (!token || !user.is_admin) {
            document.getElementById('access-denied').classList.remove('hidden');
        } else {
            document.getElementById('admin-content').classList.remove('hidden');
            loadBundles();
        }

        function authHeaders() {
            return {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            };
        }

        function toggleCreateForm() {
            const form = document.getElementById('create-form');
            const btn = document.getElementById('new-bundle-btn');
            if (form.classList.contains('hidden')) {
                form.classList.remove('hidden');
                btn.classList.add('hidden');
            } else {
                form.classList.add('hidden');
                btn.classList.remove('hidden');
                // Hiding is also how you back out of an edit, so drop the
                // half-loaded bundle rather than leaving it in the form.
                resetForm();
            }
        }

        async function loadBundles() {
            const tbody = document.getElementById('bundles-tbody');
            const loading = document.getElementById('bundles-loading');
            tbody.innerHTML = '';
            loading.classList.remove('hidden');

            try {
                const res = await fetch('/api/v1/bundles', { headers: authHeaders() });
                if (!res.ok) throw new Error('Failed to load bundles');
                const data = await res.json();

                const bundles = data.items || data.bundles || data || [];
                loading.classList.add('hidden');

                if (bundles.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-10 text-center text-stone-500">No bundles found.</td></tr>';
                    return;
                }

                bundles.forEach(bundle => {
                    const tr = document.createElement('tr');
                    tr.className = 'hover:bg-stone-50 transition';
                    const bookCount = Array.isArray(bundle.books) ? bundle.books.length : 0;
                    const priceDisplay = formatPrice(bundle.price_cents, bundle.currency);
                    const activeDot = bundle.active ? '<span class="inline-block w-2 h-2 rounded-full bg-green-500 mr-1.5"></span>Active' : '<span class="inline-block w-2 h-2 rounded-full bg-stone-300 mr-1.5"></span>Inactive';
                    tr.innerHTML = `
                        <td class="px-4 py-3 font-medium text-stone-900">${escapeHtml(bundle.name || '')}</td>
                        <td class="px-4 py-3 text-stone-600">${bookCount}</td>
                        <td class="px-4 py-3 text-stone-600">${priceDisplay}</td>
                        <td class="px-4 py-3 text-sm text-stone-600">${activeDot}</td>
                        <td class="px-4 py-3">
                            <div class="flex gap-2">
                                ${bundle.slug ? `<a href="/bundles/${bundle.slug}" class="text-amber-600 hover:text-amber-800 text-xs font-medium">View</a>` : `<a href="/bundles/${bundle.id}" class="text-amber-600 hover:text-amber-800 text-xs font-medium">View</a>`}
                                <button data-action="editBundle" data-arg-1="${bundle.id}" class="text-xs font-medium text-stone-600 hover:text-stone-900" title="Edit this bundle's details and book list">Edit</button>
                                <button data-action="toggleBundle" data-arg-1="${bundle.id}" data-arg-2="${!bundle.active}" class="text-xs font-medium ${bundle.active ? 'text-red-600 hover:text-red-800' : 'text-green-600 hover:text-green-800'}">${bundle.active ? 'Deactivate' : 'Activate'}</button>
                                <button data-action="rebuildBundle" data-arg-1="${bundle.id}" class="text-xs font-medium text-blue-600 hover:text-blue-800" title="Regenerate the download ZIP from current contents">Rebuild ZIP</button>
                            </div>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            } catch (e) {
                loading.textContent = 'Error loading bundles.';
            }
        }

        /* Book picker.

           This form used to ask for raw numeric book IDs typed by hand from
           the Manage Books page, which made the least interesting decision in
           building a bundle -- which books are actually in it -- the most
           error-prone, and made editing an existing bundle's contents
           impossible. Search the catalogue, tick the books.

           #bundle-book-ids stays the field the form submits, so the request
           body is unchanged and create/edit share one code path. `editingId`
           is null for create and set for edit; the slug is intentionally not
           editable because BundleUpdate does not accept it. */
        const idsField = document.getElementById('bundle-book-ids');
        const searchInput = document.getElementById('bundle-book-search');
        const resultsList = document.getElementById('bundle-book-results');
        const pickedList = document.getElementById('bundle-book-picked');
        const emptyNote = document.getElementById('bundle-book-empty');
        const submitBtn = document.getElementById('bundle-submit');
        const order = [];              // book ids, in pick order
        const byId = new Map();       // id -> {id,title,author}
        const searchCache = new Map(); // id -> book, from the last search
        let editingId = null;

        function label(v, fallback) {
            return v == null || v === '' ? fallback : v;
        }

        function renderPicked() {
            const books = order.map((id) => byId.get(id)).filter(Boolean);
            idsField.value = books.map((b) => b.id).join(',');
            emptyNote.classList.toggle('hidden', books.length > 0);
            pickedList.innerHTML = books.map((b, i) => `
                <li class="flex items-center gap-3 px-3 py-2 text-sm">
                    <span class="w-5 shrink-0 text-xs text-stone-400 tabular-nums">${i + 1}</span>
                    <span class="flex-1 min-w-0">
                        <span class="block truncate font-medium text-stone-800">${escapeHtml(label(b.title, 'Untitled'))}</span>
                        <span class="block truncate text-xs text-stone-500">${escapeHtml(label(b.author, 'Unknown author'))}</span>
                    </span>
                    <button type="button" data-unpick="${b.id}" class="text-xs text-stone-500 hover:text-red-700 px-2 py-1" aria-label="Remove ${escapeHtml(label(b.title, 'book'))} from bundle">&times;</button>
                </li>`).join('');
        }

        function pick(b) {
            if (byId.has(b.id)) return;
            byId.set(b.id, b);
            order.push(b.id);
            renderPicked();
        }

        function unpick(id) {
            byId.delete(id);
            const i = order.indexOf(id);
            if (i > -1) order.splice(i, 1);
            renderPicked();
        }

        function clearPicked() {
            order.length = 0;
            byId.clear();
            renderPicked();
        }

        async function searchBooks(q) {
            const term = q.trim();
            if (term.length < 2) {
                resultsList.classList.add('hidden');
                resultsList.innerHTML = '';
                return;
            }
            resultsList.classList.remove('hidden');
            resultsList.innerHTML = '<li class="px-3 py-2 text-sm text-stone-500">Searching…</li>';
            try {
                const res = await fetch('/api/v1/books?search=' + encodeURIComponent(term) +
                                        '&page_size=12&status=approved', { headers: authHeaders() });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || ('HTTP ' + res.status));
                searchCache.clear();
                (data.items || []).forEach((b) => searchCache.set(b.id, b));
                const rows = (data.items || []).filter((b) => !byId.has(b.id));
                resultsList.innerHTML = rows.length ? rows.map((b) => `
                    <li class="flex items-center gap-3 px-3 py-2 text-sm hover:bg-stone-50">
                        <span class="flex-1 min-w-0">
                            <span class="block truncate font-medium text-stone-800">${escapeHtml(label(b.title, 'Untitled'))}</span>
                            <span class="block truncate text-xs text-stone-500">${escapeHtml(label(b.author, 'Unknown author'))}</span>
                        </span>
                        <button type="button" data-pick="${b.id}" class="shrink-0 text-xs font-medium text-amber-700 hover:text-amber-900 px-3 py-1 rounded-full border border-amber-200">Add</button>
                    </li>`).join('')
                    : '<li class="px-3 py-2 text-sm text-stone-500">Nothing in the catalogue matches that.</li>';
            } catch (e) {
                resultsList.innerHTML = '<li class="px-3 py-2 text-sm text-red-700">Search failed: ' + escapeHtml(e.message) + '</li>';
            }
        }

        let pickTimer = null;
        searchInput.addEventListener('input', () => {
            clearTimeout(pickTimer);
            pickTimer = setTimeout(() => searchBooks(searchInput.value), 220);
        });

        document.addEventListener('click', (e) => {
            const add = e.target.closest('[data-pick]');
            if (add) {
                const id = parseInt(add.dataset.pick, 10);
                const b = searchCache.get(id);
                if (b) pick(b);
                add.disabled = true;
                add.textContent = 'Added';
                return;
            }
            const rm = e.target.closest('[data-unpick]');
            if (rm) unpick(parseInt(rm.dataset.unpick, 10));
        });

        function setMode(id) {
            editingId = id;
            submitBtn.textContent = id == null ? 'Create Bundle' : 'Save Changes';
            document.getElementById('bundle-cancel').textContent = id == null ? 'Cancel' : 'Cancel Edit';
        }

        function resetForm() {
            document.getElementById('create-form').querySelector('form').reset();
            clearPicked();
            setMode(null);
        }

        async function editBundle(id) {
            try {
                const res = await fetch('/api/v1/bundles/' + id, { headers: authHeaders() });
                const b = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(b.detail || 'Failed to load bundle');
                resetForm();
                document.getElementById('bundle-name').value = b.name || '';
                document.getElementById('bundle-slug').value = b.slug || '';
                document.getElementById('bundle-description').value = b.description || '';
                document.getElementById('bundle-price').value = b.price_cents ?? '';
                document.getElementById('bundle-category').value = b.category || '';
                // Preserve the bundle's existing sort_order as the pick order.
                (b.books || []).forEach((bk) => pick({ id: bk.id, title: bk.title, author: bk.author }));
                setMode(id);
                if (document.getElementById('create-form').classList.contains('hidden')) toggleCreateForm();
                document.getElementById('create-form').scrollIntoView({ behavior: 'smooth', block: 'start' });
            } catch (e) {
                alert('Failed to open bundle for editing: ' + e.message);
            }
        }

        async function submitBundle(e) {
            e.preventDefault();
            const bookIds = order.slice();
            if (bookIds.length === 0) {
                alert('Pick at least one book.');
                return;
            }
            const payload = {
                name: document.getElementById('bundle-name').value,
                description: document.getElementById('bundle-description').value,
                price_cents: parseInt(document.getElementById('bundle-price').value, 10),
                category: document.getElementById('bundle-category').value || null,
                book_ids: bookIds,
            };
            const editing = editingId != null;
            // Slug is identity, and BundleUpdate has no slug field, so it is
            // only sent on create.
            if (!editing) payload.slug = document.getElementById('bundle-slug').value;

            try {
                const res = await fetch(editing ? '/api/v1/bundles/' + editingId : '/api/v1/bundles', {
                    method: editing ? 'PATCH' : 'POST',
                    headers: authHeaders(),
                    body: JSON.stringify(payload)
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || (editing ? 'Failed to save bundle' : 'Failed to create bundle'));
                resetForm();
                toggleCreateForm();
                loadBundles();
            } catch (err) {
                alert((editing ? 'Failed to save bundle: ' : 'Failed to create bundle: ') + err.message);
            }
        }

        async function toggleBundle(id, active) {
            try {
                await fetch(`/api/v1/bundles/${id}`, {
                    method: 'PATCH',
                    headers: authHeaders(),
                    body: JSON.stringify({ active })
                });
                loadBundles();
            } catch (e) {
                alert('Failed to update bundle');
            }
        }

        async function rebuildBundle(id) {
            if (!confirm('Rebuild this bundle\'s download ZIP from its current contents? (Uses cached files where available.)')) return;
            try {
                const res = await fetch(`/api/v1/admin/bundles/${id}/rebuild`, {
                    method: 'POST',
                    headers: authHeaders()
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Failed');
                alert('Rebuild queued · Task ID: ' + (data.task_id || '').substring(0, 12));
            } catch (e) {
                alert('Failed to queue rebuild: ' + e.message);
            }
        }

        async function randomiseBundles(btn) {
            if (!confirm('Re-pick the books inside every curated (system) bundle from the approved catalogue, then rebuild their download ZIPs? Custom bundles are untouched.')) return;
            const self = btn || this;
            const label = self.dataset.origLabel || 'Randomise System Bundles';
            self.dataset.origLabel = label;
            self.disabled = true;
            self.textContent = 'Randomising…';
            try {
                const res = await fetch('/api/v1/admin/bundles/randomise', {
                    method: 'POST',
                    headers: authHeaders()
                });
                const data = await res.json();
                if (!res.ok) {
                    if (res.status === 409) throw new Error(data.detail || 'Another randomisation is already running.');
                    throw new Error(data.detail || 'Failed');
                }
                alert('Randomisation queued · Task ID: ' + (data.task_id || '').substring(0, 12));
            } catch (e) {
                alert('Failed to queue randomisation: ' + e.message);
            } finally {
                self.disabled = false;
                self.textContent = label;
            }
        }

        function escapeHtml(str) {
            const div = document.createElement('div');
            div.appendChild(document.createTextNode(str));
            return div.innerHTML;
        }
    