        const token = localStorage.getItem('token');
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        let currentPage = 1;
        let totalPages = 1;

        if (!token || !user.is_admin) {
            document.getElementById('access-denied').classList.remove('hidden');
        } else {
            document.getElementById('admin-content').classList.remove('hidden');
            loadPurchases(1);
        }

        function authHeaders() {
            return { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
        }

        async function loadPurchases(page) {
            currentPage = page;
            const tbody = document.getElementById('purchases-tbody');
            const loading = document.getElementById('purchases-loading');
            tbody.innerHTML = '';
            loading.classList.remove('hidden');

            const status = document.getElementById('status-filter').value;
            let url = `/api/v1/admin/purchases?page=${page}&page_size=50`;
            if (status) url += `&status=${status}`;

            try {
                const res = await fetch(url, { headers: authHeaders() });
                if (res.status === 403) {
                    loading.textContent = 'Your session expired. Please log in again.';
                    return;
                }
                if (!res.ok) throw new Error('Failed to load purchases');
                const data = await res.json();
                const purchases = data.items || [];
                totalPages = Math.ceil((data.total || 0) / 50) || 1;
                loading.classList.add('hidden');

                if (purchases.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" class="px-4 py-10 text-center text-stone-500">No purchases found.</td></tr>';
                    document.getElementById('pagination').innerHTML = '';
                    return;
                }

                tbody.innerHTML = purchases.map(p => `
                    <tr class="hover:bg-stone-50">
                        <td class="px-4 py-3 text-stone-600">${p.id}</td>
                        <td class="px-4 py-3 font-medium text-stone-900">${escapeHtml(p.bundle_name || 'Bundle #' + p.bundle_id)}</td>
                        <td class="px-4 py-3 text-stone-600">${escapeHtml(p.customer_email || '')}</td>
                        <td class="px-4 py-3 text-stone-600">£${(p.amount_cents / 100).toFixed(2)}</td>
                        <td class="px-4 py-3"><span class="px-2 py-1 rounded-full text-xs font-medium ${statusBadge(p.status)}">${escapeHtml(p.status)}</span></td>
                        <td class="px-4 py-3 text-stone-600">${escapeHtml(p.payment_provider || '')}</td>
                        <td class="px-4 py-3 text-stone-600">${p.download_count}/${p.max_downloads}</td>
                        <td class="px-4 py-3 text-stone-600">${new Date(p.created_at).toLocaleDateString()}</td>
                    </tr>
                `).join('');
                renderPagination();
            } catch (e) {
                loading.textContent = 'Error loading purchases.';
            }
        }

        function statusBadge(status) {
            const colors = {
                completed: 'bg-green-100 text-green-800',
                paid: 'bg-blue-100 text-blue-800',
                pending: 'bg-amber-100 text-amber-800',
                failed: 'bg-red-100 text-red-800',
            };
            return colors[status] || 'bg-stone-100 text-stone-800';
        }

        function renderPagination() {
            const container = document.getElementById('pagination');
            container.innerHTML = '';
            if (totalPages <= 1) return;
            if (currentPage > 1) {
                const prev = document.createElement('button');
                prev.textContent = '← Prev';
                prev.className = 'px-3 py-1.5 text-sm border border-stone-300 rounded-lg hover:bg-stone-100 transition';
                prev.onclick = () => loadPurchases(currentPage - 1);
                container.appendChild(prev);
            }
            const info = document.createElement('span');
            info.textContent = `Page ${currentPage} of ${totalPages}`;
            info.className = 'px-3 py-1.5 text-sm text-stone-600';
            container.appendChild(info);
            if (currentPage < totalPages) {
                const next = document.createElement('button');
                next.textContent = 'Next →';
                next.className = 'px-3 py-1.5 text-sm border border-stone-300 rounded-lg hover:bg-stone-100 transition';
                next.onclick = () => loadPurchases(currentPage + 1);
                container.appendChild(next);
            }
        }

        function escapeHtml(str) {
            const div = document.createElement('div');
            div.appendChild(document.createTextNode(str));
            return div.innerHTML;
        }
    