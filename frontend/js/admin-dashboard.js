        const token = localStorage.getItem('token');
        const user = JSON.parse(localStorage.getItem('user') || '{}');

        if (!token) {
            document.getElementById('access-denied').classList.remove('hidden');
        } else {
            document.getElementById('admin-content').classList.remove('hidden');
            // Trust the token, not the cached user object: loadStats() validates
            // admin access server-side (401 = expired → clear session, 403 = not admin).
            loadStats();
        }

        function authHeaders() {
            return { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
        }

        function showAccessDenied() {
            document.getElementById('admin-content').classList.add('hidden');
            document.getElementById('access-denied').classList.remove('hidden');
        }

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.classList.remove('hidden');
            setTimeout(() => t.classList.add('hidden'), 4000);
        }

        async function loadStats() {
            try {
                const res = await fetch('/api/v1/admin/stats', { headers: authHeaders() });
                // The token may come from a cached session: re-validate against
                // the API rather than trusting localStorage. 401 = expired
                // token, 403 = signed in but not an admin.
                if (res.status === 401 || res.status === 403) {
                    if (res.status === 401) localStorage.removeItem('token');
                    localStorage.removeItem('user');
                    showAccessDenied();
                    return;
                }
                if (!res.ok) throw new Error('Failed to load stats');
                const data = await res.json();
                document.getElementById('stat-total').textContent = data.books?.total ?? '—';
                document.getElementById('stat-approved').textContent = data.books?.approved ?? '—';
                document.getElementById('stat-pending').textContent = data.books?.pending ?? '—';
                document.getElementById('stat-rejected').textContent = data.books?.rejected ?? '—';
                document.getElementById('stat-purchases').textContent = data.purchases?.total ?? '—';
                const rev = data.purchases?.revenue_cents;
                document.getElementById('stat-revenue').textContent = (rev != null && !isNaN(rev))
                    ? '£' + (rev / 100).toFixed(2)
                    : '—';
            } catch (e) {
                showToast('Error loading stats');
            }
        }

        async function adminPost(url, okMsg, failMsg) {
            const res = await fetch(url, { method: 'POST', headers: authHeaders() });
            if (!res.ok) {
                let detail = '';
                try { detail = (await res.json()).detail || ''; } catch (e) {}
                throw new Error((res.status === 401 || res.status === 403) ? 'Not authorised — sign in as admin'
                    : (typeof detail === 'string' ? detail : JSON.stringify(detail)));
            }
            const data = await res.json().catch(() => ({}));
            showToast((data.task_id ? okMsg + ' · Task: ' + data.task_id.substring(0, 8) : okMsg));
        }

        async function scrapeSource() {
            const source = document.getElementById('scrape-source').value;
            const limit = document.getElementById('scrape-limit').value;
            const startPage = document.getElementById('scrape-start-page').value;
            showToast(`Starting scrape of ${source}...`);
            try {
                await adminPost(`/api/v1/admin/scrape/source/${source}?limit=${limit}&start_page=${startPage}`,
                    `Scrape started: ${source} (limit=${limit}, start_page=${startPage})`, 'Failed to start scrape');
            } catch (e) {
                showToast(e.message || 'Failed to start scrape');
            }
        }

        async function scrapeAll() {
            showToast('Starting full scrape...');
            try {
                await adminPost('/api/v1/admin/scrape/all?limit_per_source=50', 'Full scrape initiated', 'Failed to start scrape');
            } catch (e) {
                showToast(e.message || 'Failed to start scrape');
            }
        }

        async function scrapePopular() {
            showToast('Scraping popular books...');
            try {
                await adminPost('/api/v1/admin/scrape/popular?limit_per_source=100', 'Popular scrape initiated', 'Failed to start scrape');
            } catch (e) {
                showToast(e.message || 'Failed to start scrape');
            }
        }

        async function reverifyAll() {
            showToast('Re-verifying licenses...');
            try {
                await adminPost('/api/v1/admin/verify/licenses', 'Re-verification initiated', 'Failed to start re-verification');
            } catch (e) {
                showToast(e.message || 'Failed to start re-verification');
            }
        }

        async function scrapeAfrican() {
            if (!confirm('Expands the African Literature shelf to the full set of Africa-themed Gutenberg works. Continue?')) return;
            showToast('Starting full African Literature harvest...');
            try {
                await adminPost('/api/v1/admin/scrape/african-full', 'African full harvest started', 'Failed to start African harvest');
            } catch (e) {
                showToast(e.message || 'Failed to start African harvest');
            }
        }

        async function scrapeFull() {
            if (!confirm('Kicks off the full Gutenberg (~74k) + African shelf + all other sources in parallel to drive the catalogue toward its honest ceiling. This takes a long time. Continue?')) return;
            showToast('Starting ~90k catalogue harvest...');
            try {
                await adminPost('/api/v1/admin/scrape/full', 'Full catalogue harvest started', 'Failed to start catalogue harvest');
            } catch (e) {
                showToast('Failed to start catalogue harvest');
            }
        }

        async function retagAfrican() {
            showToast('Tagging existing African books...');
            try {
                await adminPost('/api/v1/admin/retag/african-literature', 'Tagging started', 'Failed to start tagging');
            } catch (e) {
                showToast(e.message || 'Failed to start tagging');
            }
        }

        async function scrapeGutenbergFull() {
            if (!confirm('This harvests ~74,000 books and may take a long time. Continue?')) return;
            showToast('Starting full Gutenberg catalogue harvest...');
            try {
                await adminPost('/api/v1/admin/scrape/gutenberg-full', 'Gutenberg full harvest started', 'Failed to start Gutenberg harvest');
            } catch (e) {
                showToast('Failed to start Gutenberg harvest');
            }
        }
    