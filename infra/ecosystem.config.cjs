// VPS paths contain no credentials; applications load their private JSON config.
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const common = {
  script: '/bin/sh',
  interpreter: 'none',
  exec_mode: 'fork',
  instances: 1,
  autorestart: true,
  restart_delay: 3000,
  min_uptime: 10000,
  max_restarts: 10,
  kill_timeout: 15000,
  env: {
    AMPVE_CONFIG: '/home/ampve/.config/ampve/platform.json',
    PYTHONUNBUFFERED: '1',
  },
};
const wrapper = path.join(__dirname, 'pm2-exec.sh');
module.exports = {
  apps: [
    {
      ...common,
      name: 'ampve-platform',
      cwd: path.join(root, 'apps/platform'),
      args: [wrapper, path.join(root, '.venv/bin/gunicorn'),
        'config.wsgi:application', '--bind', '127.0.0.1:3000',
        '--workers', '2', '--timeout', '30', '--max-requests', '1000',
        '--max-requests-jitter', '100', '--error-logfile', '-', '--capture-output'],
    },
    {
      ...common,
      name: 'ampve-audio',
      cwd: path.join(root, 'apps/audio'),
      env: {...common.env, NUMBA_CACHE_DIR: '/home/ampve/.cache/ampve-audio'},
      // PM2 polls memory; this restart threshold is not a cgroup hard limit.
      max_memory_restart: '1500M',
      args: [wrapper, path.join(root, '.venv-audio/bin/uvicorn'),
        'server:app', '--host', '127.0.0.1', '--port', '3001', '--workers', '1',
        '--ws', 'websockets', '--ws-max-size', '4096', '--ws-max-queue', '8',
        '--no-access-log', '--timeout-graceful-shutdown', '10'],
    },
    {
      ...common,
      name: 'ampve-tunnel',
      cwd: '/home/ampve',
      args: [wrapper, '/usr/local/bin/cloudflared', '--no-autoupdate', 'tunnel',
        '--config', '/home/ampve/.cloudflared/config.yml', 'run',
        '6d42089c-0f0c-409e-b829-91bcdf2272aa'],
    },
  ],
};
