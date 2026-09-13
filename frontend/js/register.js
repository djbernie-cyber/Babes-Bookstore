/* Babe's Bookstore — register page. */
async function register() {
  const err = document.getElementById('err'); err.classList.add('hidden');
  const name = document.getElementById('name').value.trim(), email = document.getElementById('email').value.trim(), password = document.getElementById('password').value, confirm = document.getElementById('confirm').value;
  if (!name || !email || !password) { err.textContent = 'Fill all fields.'; err.classList.remove('hidden'); return }
  if (password.length < 8) { err.textContent = 'Password must be 8+ characters.'; err.classList.remove('hidden'); return }
  if (password !== confirm) { err.textContent = 'Passwords do not match.'; err.classList.remove('hidden'); return }
  try {
    const r = await fetch('/api/v1/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, email, password }) });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail || 'Registration failed');
    localStorage.setItem('token', d.access_token || d.data?.access_token); localStorage.setItem('user', JSON.stringify(d.user));
    location.href = '/account';
  } catch (e) { err.textContent = e.message; err.classList.remove('hidden') }
}
document.getElementById('form').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); register() } });