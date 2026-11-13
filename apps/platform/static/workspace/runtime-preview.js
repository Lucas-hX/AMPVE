/* Isolated interaction concept: no hardware access, requests, audio, or storage. */
const shell = document.querySelector('.runtime-shell');
if (shell) {
  shell.querySelectorAll('[data-screen]').forEach(button => {
    button.addEventListener('click', () => {
      const target = button.dataset.screen;
      shell.querySelectorAll('[data-panel]').forEach(panel => {
        panel.hidden = panel.dataset.panel !== target;
        if (!panel.hidden) panel.querySelector('h2').focus({preventScroll:true});
      });
      shell.querySelectorAll('.runtime-nav [data-screen]').forEach(nav => {
        if (nav.dataset.screen === target) nav.setAttribute('aria-current','page');
        else nav.removeAttribute('aria-current');
      });
    });
  });
  shell.querySelector('#runtime-connect').addEventListener('click', () => {
    shell.querySelector('#runtime-network').textContent='Example Wi-Fi · demo';
    shell.querySelector('#runtime-wifi-result').textContent='Connection simulated. No network settings were changed.';
    shell.querySelector('.runtime-pair').hidden=false;
  });
}
