/* Babe's Bookstore — banned works page. */
document.addEventListener('DOMContentLoaded', () => {
  const sections = document.querySelectorAll('details');
  sections.forEach(s => s.addEventListener('toggle', () => { const summary = s.querySelector('summary'); summary.classList.toggle('text-stone-200', s.open); }));
});