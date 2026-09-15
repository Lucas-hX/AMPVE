(() => {
  const jobs = [...document.querySelectorAll('.update-job[data-progress-url]')]
    .filter((job) => job.dataset.active === 'true');
  if (!jobs.length) return;

  const formatTime = (value) => new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(new Date(value)) + ' UTC';
  const formatBytes = (value) => {
    const amount = Number(value) || 0;
    return amount >= 1048576 ? (amount / 1048576).toFixed(1) + ' MB'
      : amount >= 1024 ? (amount / 1024).toFixed(1) + ' KB' : amount + ' B';
  };

  function renderEvents(list, events) {
    list.replaceChildren();
    for (const event of events) {
      const item = document.createElement('li');
      const time = document.createElement('time');
      time.dateTime = event.at;
      time.textContent = formatTime(event.at);
      item.append(time);
      const parts = [`#${event.sequence}`, event.state || 'Event'];
      if (event.source && event.source !== 'device') parts.push(`source: ${event.source}`);
      if (event.bytes_written) parts.push(formatBytes(event.bytes_written) + ' written');
      if (event.error_code) parts.push('error: ' + event.error_code);
      if (event.boot_confirmed && event.state === 'confirmed') parts.push('target startup confirmed');
      if (event.boot_confirmed && event.state === 'rolled_back') parts.push('previous image startup confirmed');
      item.append(document.createTextNode(' · ' + parts.join(' · ')));
      if (event.app_sha256) {
        const digest = document.createElement('code');
        digest.textContent = 'reported app SHA-256: ' + event.app_sha256;
        item.append(digest);
      }
      list.append(item);
    }
    if (!events.length) {
      const item = document.createElement('li');
      item.textContent = 'Waiting for the first device report.';
      list.append(item);
    }
  }

  async function refresh(job) {
    try {
      const response = await fetch(job.dataset.progressUrl, {
        credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' },
      });
      if (!response.ok) throw new Error('Progress unavailable');
      const data = await response.json();
      const summary = job.querySelector('.update-summary');
      const progress = job.querySelector('.update-progress');
      const note = job.querySelector('.update-refresh-note');
      summary.textContent = `${data.state_label} · ${formatBytes(data.bytes_written)} / ${formatBytes(data.app_size)} downloaded`;
      progress.max = data.app_size;
      progress.value = data.bytes_written;
      const contact = data.device_last_seen ? `Board contact: ${formatTime(data.device_last_seen)}.` : 'Board contact: none.';
      const ota = data.ota_last_poll_at ? `OTA check: ${formatTime(data.ota_last_poll_at)}.` : 'OTA check: none yet.';
      note.textContent = `Last server change: ${formatTime(data.last_report_at)}. ${contact} ${ota}`;
      if (data.state === 'queued' && !data.ota_last_poll_at) note.textContent += ' Waiting for the OTA client.';
      renderEvents(job.querySelector('.update-events'), data.events);
      if (!['queued', 'downloading', 'verifying', 'rebooting'].includes(data.state)) {
        job.dataset.active = 'false';
        note.textContent += ' Update finished; reload for recovery actions or a new release.';
      }
    } catch {
      job.querySelector('.update-refresh-note').textContent =
        'Live progress is temporarily unavailable. Reload this page to check the stored events.';
    }
  }

  const refreshActive = () => jobs.filter((job) => job.dataset.active === 'true').forEach(refresh);
  refreshActive();
  const timer = setInterval(() => {
    if (document.hidden) return;
    if (!jobs.some((job) => job.dataset.active === 'true')) { clearInterval(timer); return; }
    refreshActive();
  }, 3000);
})();
