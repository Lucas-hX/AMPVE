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
  shell.querySelector('#runtime-mute').addEventListener('click', event => {
    const button=event.currentTarget, muted=button.getAttribute('aria-pressed')!=='true';
    button.setAttribute('aria-pressed',String(muted));
    button.textContent=muted?'Microphone muted':'Unmuted · demo only';
  });
  shell.querySelector('#runtime-volume').addEventListener('input', event => {
    shell.querySelector('#runtime-volume-value').textContent=event.target.value+'%';
  });
  shell.querySelector('#runtime-sound').addEventListener('click', () => {
    shell.querySelector('#runtime-sound-result').textContent='On the board: play a quiet tone, then ask “Did you hear it?” This preview does not play audio or mark a test passed.';
  });
}
