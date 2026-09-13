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

        async function createBundle(e) {
            e.preventDefault();
            const bookIdsRaw = document.getElementById('bundle-book-ids').value.trim();
            const bookIds = bookIdsRaw ? bookIdsRaw.split(',').map(id => id.trim()).filter(id => id) : [];

            const body = {
                name: document.getElementById('bundle-name').value,
                slug: document.getElementById('bundle-slug').value,
                description: document.getElementById('bundle-description').value,
                price_cents: parseInt(document.getElementById('bundle-price').value, 10),
                category: document.getElementById('bundle-category').value || null,
                book_ids: bookIds,
            };

            try {
                const res = await fetch('/api/v1/bundles', {
                    method: 'POST',
                    headers: authHeaders(),
                    body: JSON.stringify(body)
                });
                if (!res.ok) throw new Error('Failed to create bundle');
                toggleCreateForm();
                document.getElementById('create-form').querySelector('form').reset();
                loadBundles();
            } catch (e) {
                alert('Failed to create bundle');
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
    