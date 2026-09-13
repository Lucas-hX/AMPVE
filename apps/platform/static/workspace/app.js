const toggle = document.querySelector('.menu-toggle');
const sidebar = document.querySelector('.sidebar');
const scrim = document.querySelector('.menu-scrim');
if (toggle && sidebar && scrim) {
  const mobile = window.matchMedia('(max-width: 800px)');
  const close = sidebar.querySelector('.menu-close');
  const setMenu = (open, restoreFocus = true) => {
    toggle.setAttribute('aria-expanded', String(open));
    sidebar.classList.toggle('open', open);
    sidebar.inert = mobile.matches && !open;
    scrim.hidden = !open;
    if (open) {
      sidebar.setAttribute('role', 'dialog');
      sidebar.setAttribute('aria-modal', 'true');
      close.focus();
    } else {
      sidebar.removeAttribute('role');
      sidebar.removeAttribute('aria-modal');
      if (restoreFocus) toggle.focus();
    }
  };
  toggle.addEventListener('click', () => setMenu(toggle.getAttribute('aria-expanded') !== 'true'));
  close.addEventListener('click', () => setMenu(false));
  scrim.addEventListener('click', () => setMenu(false));
  mobile.addEventListener('change', () => setMenu(false, false));
  document.addEventListener('keydown', (event) => {
    if (toggle.getAttribute('aria-expanded') !== 'true') return;
    if (event.key === 'Escape') setMenu(false);
    if (event.key === 'Tab') {
      const focusable = [...sidebar.querySelectorAll('a[href],button')];
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  setMenu(false, false);
}
