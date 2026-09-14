(() => {
  const root = document.querySelector('[data-console]');
  if (!root) return;
  const $ = selector => root.querySelector(selector);
  const $$ = selector => [...root.querySelectorAll(selector)];
  const csrf = document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1] || '';
  const templates = {
    state: root.dataset.stateTemplate,
    command: root.dataset.commandTemplate,
    stop: root.dataset.stopTemplate,
  };
  let session = null;
  let sequence = 0;
  let timer = null;
  let activePage = 'home';
  let lastRevision = -1;
  let lastAcknowledgement = null;
  let lastInputSource = 'activity';
  let acknowledgementTimer = null;

  function url(kind) { return templates[kind].replace('{session}', session); }
  function icon(node, name) {
    const use = node?.querySelector('use');
    if (!use) return;
    use.setAttribute('href', use.getAttribute('href').replace(/#icon-[\w-]+$/, `#icon-${name}`));
  }
  function hud(kind, label, state, iconName) {
    const card = $(`[data-hud="${kind}"]`);
    const value = $(`[data-hud-${kind}]`);
    if (!card || !value) return;
    value.textContent = label;
    card.dataset.state = state;
    if (iconName) icon(card, iconName);
  }
  function remoteLabel(label) { $('[data-remote-label]').textContent = label; }
  function error(message = '') {
    const node = $('[data-console-error]');
    node.textContent = message;
    node.hidden = !message;
  }
  function setStatus(label, connected = false) {
    $('[data-console-status]').textContent = label;
    $('[data-signal]').classList.toggle('is-live', connected);
  }
  function showPage(page) {
    if (!['home', 'wifi', 'device', 'settings', 'companion'].includes(page)) return;
    activePage = page;
    $$('[data-page]').forEach(node => { node.hidden = node.dataset.page !== page; });
    $$('[data-console-target]').forEach(node => node.classList.toggle('is-current', node.dataset.consoleTarget === page));
  }
  function apply(payload) {
    if (payload.screen.revision < lastRevision) {
      hud('channel', 'Stale device revision', 'attention', 'attention');
      remoteLabel('Waiting for a current device state');
      return;
    }
    lastRevision = payload.screen.revision;
    showPage(payload.screen.page);
    $('[data-device-name]').textContent = payload.device.name;
    $('[data-device-connection]').textContent = payload.device.connection;
    $('[data-firmware]').textContent = payload.device.firmware_version;
    $('[data-display-mode]').textContent = payload.screen.display_mode === 'physical' ? 'Physical display mirror' : 'Virtual display';
    $('[data-channel-label]').textContent = payload.device_connected ? 'Device connected' : 'Waiting for device';
    remoteLabel(payload.screen.remote_allowed ?
      (payload.device_connected ? 'Remote control visible on device' : 'Remote session ready · device has not joined') :
      'Remote input stopped locally');
    const deviceIcon = payload.device.connection === 'Online' ? 'wifi' :
      (payload.device.connection === 'Offline' ? 'offline' : 'attention');
    hud('device', payload.device.connection, payload.device.connection.toLowerCase().replaceAll(' ', '-'), deviceIcon);
    hud('channel', payload.screen.remote_allowed ?
      (payload.device_connected ? 'Device connected' : 'Reconnecting') : 'Stopped locally',
      payload.screen.remote_allowed ? (payload.device_connected ? 'live' : 'reconnecting') : 'attention',
      payload.screen.remote_allowed ? 'console' : 'local-control');
    hud('session', 'Active · 10 min', 'live', 'session');
    setStatus(payload.device_connected ? 'Live device channel' : 'Authenticated · waiting for device', payload.device_connected);
    if (payload.last_command?.id) {
      $('[data-last-input]').textContent = `${payload.last_command.result} · ${payload.last_command.id.slice(0, 8)}`;
      if (payload.last_command.id !== lastAcknowledgement) {
        lastAcknowledgement = payload.last_command.id;
        const applied = payload.last_command.result === 'applied';
        const source = ['mouse', 'touch', 'keyboard'].includes(lastInputSource) ? lastInputSource : 'activity';
        hud('input', `${payload.last_command.result} · ${source}`, applied ? 'acknowledged' : 'rejected',
          applied ? source : 'attention');
        const card = $('[data-hud="input"]');
        window.clearTimeout(acknowledgementTimer);
        card.classList.toggle('is-acknowledged', applied);
        acknowledgementTimer = window.setTimeout(() => card.classList.remove('is-acknowledged'), 700);
      }
    }
  }
  async function request(endpoint, options = {}) {
    const response = await fetch(endpoint, {
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
      ...options,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || (response.status === 410 ? 'Console session ended.' : 'Console request failed.'));
    return payload;
  }
  async function poll() {
    if (!session) return;
    try {
      const payload = await request(url('state'));
      apply(payload);
      timer = window.setTimeout(poll, 800);
    } catch (reason) {
      error(reason.message);
      endUI('Session ended');
    }
  }
  async function start() {
    error();
    $('[data-start-console]').disabled = true;
    try {
      const payload = await request(root.dataset.start, {method: 'POST', body: JSON.stringify({protocol: 1})});
      session = payload.session_id;
      sequence = 0;
      lastRevision = -1;
      lastAcknowledgement = null;
      $('[data-session-label]').textContent = `Active · ${session.slice(0, 8)}`;
      hud('session', 'Starting', 'reconnecting', 'session');
      hud('channel', 'Waiting for device', 'reconnecting', 'console');
      $('[data-start-console]').hidden = true;
      $('[data-stop-console]').hidden = false;
      apply({...payload, device_connected: false});
      $('.console-frame').focus();
      poll();
    } catch (reason) {
      error(reason.message);
      $('[data-start-console]').disabled = false;
    }
  }
  function endUI(label) {
    window.clearTimeout(timer);
    session = null;
    $('[data-session-label]').textContent = label;
    $('[data-channel-label]').textContent = 'Stopped';
    $('[data-start-console]').hidden = false;
    $('[data-start-console]').disabled = false;
    $('[data-stop-console]').hidden = true;
    remoteLabel('Remote console is stopped');
    hud('channel', 'Stopped', 'stopped', 'console');
    hud('session', label, 'stopped', 'session');
    if ($('[data-hud="input"]').dataset.state === 'pending') hud('input', 'Not acknowledged', 'attention', 'attention');
    setStatus('Session stopped');
  }
  async function stop() {
    if (!session) return;
    const stopUrl = url('stop');
    window.clearTimeout(timer);
    try { await request(stopUrl, {method: 'POST', body: JSON.stringify({protocol: 1})}); }
    catch (reason) { error(reason.message); }
    endUI('Stopped');
  }
  function coordinates(event, node) {
    const frame = $('.console-frame').getBoundingClientRect();
    const box = node.getBoundingClientRect();
    const clientX = Number.isFinite(event.clientX) && event.clientX ? event.clientX : box.left + box.width / 2;
    const clientY = Number.isFinite(event.clientY) && event.clientY ? event.clientY : box.top + box.height / 2;
    return {
      x: Math.max(0, Math.min(1023, Math.round((clientX - frame.left) * 1024 / frame.width))),
      y: Math.max(0, Math.min(599, Math.round((clientY - frame.top) * 600 / frame.height))),
    };
  }
  async function send(target, source, point) {
    if (!session) { error('Start a private session before sending input.'); return; }
    error();
    try {
      const payload = {protocol: 1, client_sequence: ++sequence, kind: 'activate', input_source: source, target};
      if (source !== 'keyboard') Object.assign(payload, point);
      await request(url('command'), {method: 'POST', body: JSON.stringify(payload)});
      lastInputSource = source;
      $('[data-last-input]').textContent = `Queued · ${target}`;
      hud('input', `Pending · ${source}`, 'pending', source);
    } catch (reason) {
      error(reason.message);
      hud('input', `Rejected · ${source}`, 'rejected', 'attention');
    }
  }

  $('[data-start-console]').addEventListener('click', start);
  $('[data-stop-console]').addEventListener('click', stop);
  $$('[data-console-target]').forEach(node => node.addEventListener('click', event => {
    const source = event.detail === 0 ? 'keyboard' : (event.pointerType === 'touch' ? 'touch' : 'mouse');
    const target = node.dataset.consoleTarget;
    if (['home', 'wifi', 'device', 'settings', 'companion'].includes(target)) showPage(target);
    send(target, source, coordinates(event, node));
  }));
  $('.console-frame').addEventListener('keydown', event => {
    const target = {h: 'home', w: 'wifi', d: 'device', s: 'settings', c: 'companion'}[event.key.toLowerCase()];
    if (target) { event.preventDefault(); showPage(target); send(target, 'keyboard'); }
    if (event.key === 'Escape') { event.preventDefault(); stop(); }
  });
})();
