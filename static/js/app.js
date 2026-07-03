function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar) sidebar.classList.toggle('open');
}

document.addEventListener('click', function (event) {
  const sidebar = document.getElementById('sidebar');
  const button = document.querySelector('.mobile-menu-btn');
  if (!sidebar || !button) return;
  if (window.innerWidth > 860) return;
  if (!sidebar.contains(event.target) && !button.contains(event.target)) {
    sidebar.classList.remove('open');
  }
});
