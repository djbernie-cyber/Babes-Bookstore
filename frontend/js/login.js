/* Babe's Bookstore — login page. */
async function login() {
  const err = document.getElementById('err'); err.classList.add('hidden');
  const email = document.getElementById('email').value.trim(), password = document.getElementById('password').value;
  if (!email || !password) { err.textContent = 'Enter email and password.'; err.classList.remove('hidden'); return }
  try {
    const r = await fetch('/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail || 'Login failed');
    localStorage.setItem('token', d.access_token || d.data?.access_token); localStorage.setItem('user', JSON.stringify(d.user));
    location.href = d.user?.is_admin ? '/admin' : '/account';
  } catch (e) { err.textContent = e.message; err.classList.remove('hidden') }
}
document.getElementById('form').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); login() } });