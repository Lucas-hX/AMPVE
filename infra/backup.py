#!/usr/bin/env python3
"""Back up only AMPVE; keep seven days of private local database snapshots."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import subprocess

os.umask(0o077)
root = Path('/home/ampve/.local/state/ampve/backups')
root.mkdir(parents=True, exist_ok=True, mode=0o700)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
target = root / f'ampve-{stamp}.dump'
temporary = target.with_suffix('.partial')
try:
    subprocess.run(['pg_dump', '-h', '/run/postgresql-neurosis', '-p', '5433', '-U', 'ampve',
                    '-Fc', '-f', str(temporary), 'ampve'], check=True)
    subprocess.run(['pg_restore', '--list', str(temporary)], check=True, stdout=subprocess.DEVNULL)
    temporary.replace(target)
except Exception:
    temporary.unlink(missing_ok=True)
    raise
cutoff = datetime.now(timezone.utc) - timedelta(days=7)
for old in root.glob('ampve-*.dump'):
    if datetime.fromtimestamp(old.stat().st_mtime, timezone.utc) < cutoff:
        old.unlink()
print('AMPVE local backup completed; off-VPS backup is still required.')
