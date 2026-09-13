        const token = localStorage.getItem('token');
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        let currentPage = 1;
        let totalPages = 1;

        if (!token || !user.is_admin) {
            document.getElementById('access-denied').classList.remove('hidden');
        } else {
            document.getElementById('admin-content').classList.remove('hidden');
            loadBooks(1);
            loadPendingCount();
        }

        function authHeaders() {
            return {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            };
        }

        async function loadPendingCount() {
            try {
                const res = await fetch('/api/v1/admin/stats', { headers: authHeaders() });
                if (!res.ok) return;
                const stats = await res.json();
                const pending = stats.books?.pending || 0;
                document.getElementById('pending-count').textContent = pending;
                document.getElementById('review-banner').classList.toggle('hidden', pending === 0);
            } catch (e) { /* banner is non-essential */ }
        }

        function showPending() {
            document.getElementById('status-filter').value = 'pending';
            loadBooks(1);
        }

        async function loadBooks(page) {
            currentPage = page;
            const tbody = document.getElementById('books-tbody');
            const loading = document.getElementById('books-loading');
            tbody.innerHTML = '';
            loading.textContent = 'Loading...';
            loading.classList.remove('hidden');

            const status = document.getElementById('status-filter').value;
            const source = document.getElementById('source-filter').value;
            const search = document.getElementById('search-input')?.value.trim() || '';

            let url = `/api/v1/books?page=${page}&page_size=20&approved_only=false`;
            if (status) url += `&status=${status}`;
            if (source) url += `&source=${source}`;
            if (search) url += `&search=${encodeURIComponent(search)}`;

            try {
                const res = await fetch(url, { headers: authHeaders() });
                if (res.status === 403) {
                    loading.textContent = 'Your session expired. Please log in again.';
                    return;
                }
                if (!res.ok) throw new Error('Failed to load books');
                const data = await res.json();

                const books = data.items || data.books || data || [];
                totalPages = data.total_pages || Math.ceil((data.total || books.length) / 20) || 1;

                loading.classList.add('hidden');

                if (books.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="6" class="px-4 py-10 text-center text-stone-500">
                        ${status === 'pending'
                            ? '🎉 Nothing waiting for review. Run a scrape from the Dashboard to bring in more books.'
                            : 'No books match these filters.'}
                    </td></tr>`;
                    document.getElementById('pagination').innerHTML = '';
                    return;
                }

                books.forEach(book => {
                    const tr = document.createElement('tr');
                    tr.className = 'hover:bg-stone-50 transition';
                    const statusColor = book.status === 'approved' ? 'bg-green-100 text-green-800' :
                                        book.status === 'rejected' ? 'bg-red-100 text-red-800' :
                                        'bg-amber-100 text-amber-800';
                    const licence = escapeHtml(book.license_type || 'unknown');
                    const licenceLink = book.license_url
                        ? `<a href="${escapeHtml(book.license_url)}" target="_blank" rel="noopener" class="text-amber-700 hover:text-amber-900 underline" title="Check before approving">${licence} ↗</a>`
                        : licence;
                    const sourceLink = book.source_url
                        ? `<a href="${escapeHtml(book.source_url)}" target="_blank" rel="noopener" class="hover:text-amber-700 underline" title="View at source">${escapeHtml(book.source || '')} ↗</a>`
                        : escapeHtml(book.source || '');
                    tr.innerHTML = `
                        <td class="px-4 py-3 font-medium text-stone-900 max-w-[200px] truncate">${escapeHtml(book.title || '')}</td>
                        <td class="px-4 py-3 text-stone-600 max-w-[150px] truncate">${escapeHtml(book.author || '')}</td>
                        <td class="px-4 py-3 text-stone-600 text-xs">${sourceLink}</td>
                        <td class="px-4 py-3 text-stone-600 text-xs max-w-[140px] truncate">${licenceLink}</td>
                        <td class="px-4 py-3"><span class="px-2 py-1 rounded-full text-xs font-medium ${statusColor}">${escapeHtml(book.status || '')}</span></td>
                        <td class="px-4 py-3">
                            <div class="flex gap-2">
                                ${book.status !== 'approved' ? `<button data-action="approveBook" data-arg-1="${book.id}" class="text-green-600 hover:text-green-800 text-xs font-medium">Approve</button>` : ''}
                                ${book.status !== 'rejected' ? `<button data-action="rejectBook" data-arg-1="${book.id}" class="text-red-600 hover:text-red-800 text-xs font-medium">Reject</button>` : ''}
                                ${book.slug ? `<a href="/books/${book.slug}" class="text-amber-600 hover:text-amber-800 text-xs font-medium">View</a>` : `<a href="/books/${book.id}" class="text-amber-600 hover:text-amber-800 text-xs font-medium">View</a>`}
                            </div>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });

                renderPagination();
            } catch (e) {
                loading.textContent = 'Error loading books.';
            }
        }

        function renderPagination() {
            const container = document.getElementById('pagination');
            container.innerHTML = '';
            if (totalPages <= 1) return;

            if (currentPage > 1) {
                const prev = document.createElement('button');
                prev.textContent = '← Prev';
                prev.className = 'px-3 py-1.5 text-sm border border-stone-300 rounded-lg hover:bg-stone-100 transition';
                prev.onclick = () => loadBooks(currentPage - 1);
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
                next.onclick = () => loadBooks(currentPage + 1);
                container.appendChild(next);
            }
        }

        async function approveBook(id) {
            try {
                const res = await fetch(`/api/v1/books/${id}/approve`, { method: 'POST', headers: authHeaders() });
                if (!res.ok) throw new Error();
                loadBooks(currentPage);
                loadPendingCount();
            } catch (e) {
                alert('Failed to approve book');
            }
        }

        async function rejectBook(id) {
            if (!confirm('Reject this book? It will be hidden from the catalogue and from bundle building.')) return;
            try {
                const res = await fetch(`/api/v1/books/${id}/reject`, { method: 'POST', headers: authHeaders() });
                if (!res.ok) throw new Error();
                loadBooks(currentPage);
                loadPendingCount();
            } catch (e) {
                alert('Failed to reject book');
            }
        }

        async function approveAllPending() {
            const pending = parseInt(document.getElementById('pending-count').textContent, 10) || 0;
            if (pending === 0) return;
            if (!confirm(`Approve all ${pending} pending book(s)? Each will be marked approved and licence-verified.`)) return;
            const btn = document.getElementById('approve-all-btn');
            btn.disabled = true;
            btn.textContent = 'Approving…';
            try {
                const res = await fetch('/api/v1/admin/books/approve-all', { method: 'POST', headers: authHeaders() });
                if (!res.ok) throw new Error();
                const data = await res.json();
                loadBooks(currentPage);
                loadPendingCount();
                const notice = document.createElement('div');
                notice.className = 'mb-6 bg-green-50 border border-green-200 text-green-800 rounded-xl px-5 py-4';
                notice.textContent = `Approved ${data.affected} book(s).`;
                const banner = document.getElementById('review-banner');
                banner.parentNode.insertBefore(notice, banner.nextSibling);
                setTimeout(() => notice.remove(), 5000);
            } catch (e) {
                alert('Failed to approve all pending books');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Approve all pending';
            }
        }

        function escapeHtml(str) {
            const div = document.createElement('div');
            div.appendChild(document.createTextNode(str));
            return div.innerHTML;
        }
    