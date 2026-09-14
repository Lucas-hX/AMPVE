# Platform foundation

Current device milestone: the first 7B completed the signed nominal Wi-Fi OTA to `0.1.16-touch-ota-dev`; the owner confirms display, corrected touch and connectivity. Speaker output, restoration and interrupted-update rollback remain pending. The owner-authenticated semantic [visual console](VISUAL_CONSOLE.md) and compiled `0.1.17-visual-console-dev` client are implemented; physical console behavior remains pending.
Date: 2026-09-13
Architecture: [ADR 0001](../decisions/0001-platform-architecture.md) and [ADR 0002](../decisions/0002-provider-audio-and-xiaozhi.md)

## Scope

Implemented: English public landing, private workspace, email/password sign-in, POST logout, CSRF protection, secure database-backed sessions, own-name profile editing, password changes, Django administration, persisted Companion preview catalog, truthful empty device/setup pages, encrypted user-owned provider connections, and an experimental FastAPI/Pipecat browser voice preview. No public registration. Lucas is a normal user; administration is a separate account.

Current browser/native delivery: the stock-preserving native candidate, local browser audit/backups and a gated USB writer are implemented; see [BROWSER_INSTALLATION.md](BROWSER_INSTALLATION.md). No physical installation or approved firmware release exists yet. The persistent owner-authorized OTA backend is implemented; see [FIRMWARE_DEPLOYMENTS.md](FIRMWARE_DEPLOYMENTS.md). Not implemented/validated: the XiaoZhi audio adapter, Companion activation on hardware, physical OTA, or camera. The native OTA client is a compiled development candidate; see [NATIVE_OTA.md](NATIVE_OTA.md). The pairing/management server is implemented; physical enrollment is unvalidated. Lucas reports successful OpenAI key setup and browser voice; Gemini remains unvalidated. No fake production devices or successful integrations are created.

## Runtime

Debian 13.6 x86_64; Python 3.13.5; PostgreSQL 17.11 shared server. Exact Python packages are pinned in `requirements.txt`: Django 5.2.17, Gunicorn 23.0.0, WhiteNoise 6.12.0, psycopg 3.3.5 and django-axes 8.3.1 plus transitive dependencies. Browser tooling is separate in `requirements-dev.txt`.

PM2 7.0.4 (Node.js 20.19.2) supervises `ampve-platform`, running as `ampve`, with two Gunicorn workers on `127.0.0.1:3000`. Static assets use WhiteNoise. Existing Cloudflare Tunnel supplies HTTPS for `ampve.com`. The origin trusts the secure-proxy header only because it is loopback-only; do not expose it publicly. Axes accepts Cloudflare's overwritten client-IP header only from a loopback peer. Local system users are part of the trusted VPS boundary.

PostgreSQL uses `/run/postgresql-neurosis`, port 5433. AMPVE has its own `ampve` database owned by login role `ampve` (no superuser/create-role/create-database privileges). A narrow `local ampve ampve peer` rule was added before the existing reject rule in `/etc/neurosis/pg_hba.conf` and reloaded without restarting PostgreSQL. Previous configuration: `/etc/neurosis/pg_hba.conf.pre-ampve`. NEUROSIS databases, credentials, and services remain separate.

The initial tunnel configuration contained the literal `${AMPVE_HOSTNAME}`. It was replaced with `ampve.com`; the prior file is `/home/ampve/.cloudflared/config.pre-platform.yml`. At the owner's request, PM2 now supervises `ampve-tunnel` alongside `ampve-platform` and `ampve-audio`. The enabled `pm2-ampve.service` restores the saved process list on boot after PostgreSQL. The former individual systemd application/tunnel units are disabled and stopped; do not start both supervisors. The same tunnel ID, credential file and ingress configuration are reused. NEUROSIS tunnel supervision was not changed. The apex DNS A record still pointed to the registrar (192.64.119.39); it was changed to the AMPVE tunnel CNAME. Existing MX/TXT records were preserved, and the previous records were saved privately at `/home/ampve/.config/ampve/dns-before-platform.json`. Docker is not installed: this deployment uses PM2 with a systemd boot unit and the existing Unix-socket database, with Compose deferred as documented in the ADR.

## Private configuration and accounts

`/home/ampve/.config/ampve/platform.json` holds the random Django secret and optional database settings, mode 0600 inside a 0700 directory. `infra/platform.example.json` contains placeholders only.

`/home/ampve/.config/ampve/demo-credentials.json` contains the owner-requested initial credentials for `lucas@ampve.com` and the separate `admin@ampve.com` account, mode 0600. It is outside Git and outside static paths. Do not print it to logs or copy it into the repository. Open it locally to obtain the password. Change passwords through Settings; the initial JSON is not automatically updated. No emails are sent to these addresses.

The bootstrap command refuses to overwrite existing accounts or credentials. Further accounts are created through `/admin/` or Django's `createsuperuser`. Email is normalized to lowercase and protected by a case-insensitive unique database constraint. Profile forms cannot alter email, role or another user's record.

## Setup and checks

From repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Prepare AMPVE_CONFIG outside Git from infra/platform.example.json.
# Prepare the dedicated database/role and peer rule before migration.
.venv/bin/python apps/platform/manage.py migrate --noinput
.venv/bin/python apps/platform/manage.py bootstrap_accounts
.venv/bin/python apps/platform/manage.py collectstatic --noinput
.venv/bin/python apps/platform/manage.py check --deploy
AMPVE_TESTING=1 .venv/bin/python apps/platform/manage.py test workspace --noinput
```

Automated tests use an isolated in-memory SQLite database; PostgreSQL migrations and a live authenticated smoke test must also pass on deployment. Never set `AMPVE_TESTING=1` in a public service.

The VPS process definitions are in `infra/ecosystem.config.cjs`; private JSON configuration remains outside Git. Django serves both the frontend and management API; `ampve-audio` is the separate voice backend. There is no separate frontend development server. After code updates, run migrations/checks/collectstatic, then `pm2 restart ampve-platform` (and `pm2 restart ampve-audio` when shared/audio code changes). Run PM2 as `ampve`, never with sudo.

For initial setup, stop/disable the three former individual systemd units, then run `pm2 start infra/ecosystem.config.cjs` and `pm2 save`. Install `infra/pm2-ampve.service` into `/etc/systemd/system/`, reload systemd, stop the standalone daemon with `pm2 kill`, then enable/start `pm2-ampve.service`. This daemon must contain only AMPVE processes because its stop action stops the entire list. Keep `~/.pm2` private (0700) and saved process dumps private (0600); never pass secret values through PM2 arguments or ecosystem environment settings. Use `pm2 ls` for status and `pm2 logs <name> --lines 50` locally for diagnosis; do not share unreviewed logs or dumps.

PM2 preserves loopback binds, worker counts and graceful shutdown settings. Its audio memory restart threshold is 1500 MB, polled rather than enforced as a hard cgroup limit. The former per-service filesystem sandbox and task limits are not provided by this PM2 configuration. Processes still run as the unprivileged `ampve` user with a private umask. Existing backup/maintenance timers and unrelated NEUROSIS services remain under systemd.

To restore the former supervisor, stop/disable `pm2-ampve`, then enable/start `ampve-platform`, `ampve-audio` and `ampve-tunnel`. Never run both sets simultaneously.

`/health/` checks HTTP process liveness only, not database readiness or AI availability. Use authenticated page checks for database-dependent behavior. Existing services can be checked with `systemctl is-active neurosis-api neurosis-postgresql neurosis-cloudflared`.

Production checks intentionally leave HSTS subdomain inclusion and preload disabled: AMPVE does not establish HTTPS policy for every subdomain. Root-domain HSTS is set to one hour. These two Django deployment warnings are documented, not suppressed. DEBUG is off; session and CSRF cookies require HTTPS.

Axes locks an account or source IP after five failed sign-ins for 15 minutes using persisted database records across workers. Use the maintained `axes_reset` management command if an administrator needs to clear a lockout. Public registration and email password recovery are intentionally unavailable; use the authenticated password form or the administrator's password reset interface.

## Backup and recovery

Existing NEUROSIS backup jobs must not be assumed to include AMPVE. Back up the dedicated database with `pg_dump -h /run/postgresql-neurosis -p 5433 -U ampve -Fc ampve` to private storage and separately protect `platform.json`. Database dumps contain account hashes/session data and must not enter Git or static storage. A daily `ampve-backup.timer` now runs at 04:20 UTC plus up to five minutes jitter, retaining seven days in `/home/ampve/.local/state/ampve/backups` with private permissions. The initial dump was successfully restored into a separate temporary database and verified to contain two accounts and the Companion catalog entry; that temporary database was then removed. Off-VPS backup and separate secret-key backup scheduling remain operational follow-ups.

To stop only this application: `pm2 stop ampve-platform`. Preserve the database and private configuration when reverting application code. Do not roll back migrations blindly; review schema changes first. Restore tests must use a separate database. Never drop or restore over NEUROSIS as part of AMPVE recovery.

Expired Django sessions can be removed with `manage.py clearsessions`. Authentication metadata retention should be periodically pruned with the Axes cleanup commands; `ampve-maintenance.timer` runs daily at 04:40 UTC plus up to five minutes jitter, clearing expired sessions and Axes success/failure logs older than 30 days.

## Verification evidence

- 26 Django automated tests passed (13 foundation tests plus 13 credential/authorization tests): access control, CSRF, session cookie flags, POST logout, normal/admin separation, profile ownership and privilege injection, password checks and session invalidation, redirect safety, persisted rate limiting, inactive accounts, email uniqueness, preview states and trusted-proxy IP handling.
- All production PostgreSQL migrations applied; no pending model changes.
- Local HTTP origin and public HTTPS return 200; existing NEUROSIS services remain active.
- Production deployment checks report only the two intentionally deferred HSTS policy warnings described above.
- Database backup restoration succeeded in an isolated temporary database.
- PM2 restores the application/audio/tunnel process list through enabled `pm2-ampve.service`; backup and maintenance timers remain enabled. Unit verification passed. No VPS reboot was performed.
- Dependency consistency and Git whitespace checks passed; private password/secret values were checked against every Git candidate file with no matches. Credential JSON permissions are 0600.
- Public HTTPS Chromium smoke tests passed: actual demo login, all workspace pages, profile save, logout, mobile menu with Escape, no horizontal overflow at 390/768/1440 px, and no JavaScript errors. Desktop and mobile screenshots were visually reviewed.
- Core text/action palette contrast was calculated against actual surface colors; keyboard focus and mobile drawer behavior were checked. This is not a full accessibility certification.
- Chromium/Playwright tooling and its OS libraries were installed for visual and browser verification; they are not application runtime requirements.

## Browser verification

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/playwright install chromium
# On a fresh host, install the OS libraries requested by Playwright.
.venv/bin/python tests/browser/smoke.py
```

This smoke test reads the private demo JSON, signs in to the running private instance, saves the demo profile name, and writes ignored screenshots under `.browser-tests/`. Override `AMPVE_BASE_URL` and `AMPVE_DEMO_CREDENTIALS` to target a different authorized demo instance. Do not use it with an unrelated real user account.

## Next milestones

1. Validate the implemented browser preview with actual Gemini Live and OpenAI Realtime API accounts: three turns, interruption, mute/stop and revocation. Lucas reports successful OpenAI browser voice; Gemini and a systematic regression of interruption/revocation remain pending.
2. Pin and implement the selected XiaoZhi adapter with Opus software fixtures, cancellation and per-user authorization; do not compare alternative firmware.
3. Pinned firmware/toolchain and recovery preparation on the owner's local computer, then explicitly approved physical installation.
4. Enrollment, Companion settings/acknowledgement, real voice/face and tested OTA recovery.

This foundation alone does not satisfy the full provider-path or hardware MVP acceptance criteria.

## Provider connections and audio operations

The audio environment is separate: `.venv-audio`, locked by `apps/audio/requirements.txt` (Pipecat 1.10.0, FastAPI 0.141.1, Uvicorn 0.52.4). It includes the Django dependencies because the gateway imports the same ORM/authorization code. Platform encryption uses cryptography 46.0.7. Keep shared dependency versions aligned when updating either lock.

`ampve-audio` runs one Uvicorn worker on `127.0.0.1:3001`, with a PM2 memory restart threshold of 1500 MB. The existing tunnel routes `/audio/.*` for `ampve.com` to that port before the Django catch-all on port 3000. The prior tunnel configuration is saved privately at `/home/ampve/.cloudflared/config.pre-audio.yml`. The audio gateway refuses unapproved origins and unauthenticated tickets. Do not expose either origin port directly or add multiple workers: the concurrency cap is process-local.

Encryption configuration: `/home/ampve/.config/ampve/provider-encryption.json`, mode 0600, contains `{"keys": ["FERNET_KEY_PLACEHOLDER"]}` with an actual generated random Fernet key on the VPS. It is deliberately outside the repository and database. Protect an independent copy: database backups alone cannot recover provider keys. The existing database backup timer does not back up this secret. `platform.json` may override `provider_key_file`, `gemini_live_model`, or `openai_realtime_model`; never put provider API keys there.

Rotation: securely prepend a newly generated Fernet key to the private key ring while retaining the old keys, then run `manage.py rotate_provider_keys`. The transaction re-encrypts current rows using the first key. Keep old keys securely available for any retained database backups; remove them from the active ring only after current rows are rotated and backup recovery is planned. Restart audio after rotation as an operational check. Do not print the key ring or use shell arguments containing keys. A restore test must use a separate database and the matching private key ring.

After preparing the private encryption file and virtual environments:

```bash
python3 -m venv .venv-audio
.venv-audio/bin/pip install -r apps/audio/requirements.txt
.venv/bin/python apps/platform/manage.py migrate --noinput
.venv/bin/python apps/platform/manage.py collectstatic --noinput
AMPVE_TESTING=1 .venv/bin/python apps/platform/manage.py test workspace --noinput
AMPVE_TESTING=1 .venv-audio/bin/python -m unittest discover -s apps/audio -p 'test_*.py' -v
mkdir -p /home/ampve/.cache/ampve-audio
sudo install -m 644 infra/ampve-maintenance.service /etc/systemd/system/ampve-maintenance.service
sudo systemctl daemon-reload
pm2 startOrRestart infra/ecosystem.config.cjs --only ampve-platform,ampve-audio
pm2 save
# Review/adapt infra/cloudflared.example.yml in the existing tunnel config.
cloudflared tunnel ingress validate
pm2 restart ampve-tunnel
```

Ten fixture-only audio tests verify grant rejection/origins, readiness, connection limits, revocation, disconnect cleanup, actual Pipecat transport PCM flow, frame validation/rate limits, both provider constructors and sanitized errors. They replace external provider calls and persistence; Django tests separately exercise persistence/ownership. They are not evidence of upstream service access or physical-device compatibility.

`manage.py cleanup_audio_metadata` removes expired grants older than one day and session metadata older than 30 days; the existing maintenance unit now includes it. Audio service startup marks unfinished sessions as ended after a restart. Public `/health/` remains platform liveness only; use the browser workflow to test audio functionality.

### What Lucas can test now

1. Sign in at `https://ampve.com` using the existing private demo credentials.
2. Open Connections, choose a provider and save its API key. Saving is local and does not contact the provider. Refresh and confirm only a mask is shown; replacement resets validation, and deletion removes the key.
3. Consent to API quota usage and select **Test connection**. This opens a short upstream realtime session and reports configuration acceptance or a sanitized failure. A consumer subscription is not API credit, and a successful check does not prove audio quality.
4. Select **Try voice preview**, use desktop Chrome/Edge with headphones, consent, then start. Test at least three turns, interruption, mute/unmute and stop. Repeat for the second provider. Sessions are capped at five minutes.
5. While voice runs, replace/delete the connection in another tab or sign out. Verify the microphone/session stops promptly. Report the displayed result and provider/model, never the API key.

`tests/browser/connections.py` is a private-demo smoke test: it saves/replaces/deletes an explicitly named synthetic connection, checks actual public WSS rejection, then intercepts only its own browser socket to exercise microphone PCM/mute/stop with a fixture. It never contacts a provider or leaves a fixture connection behind. Do not interpret its simulated readiness as provider success.

### Additional delivery evidence (2026-09-13)

- The new PostgreSQL migration was applied after a successful pre-change database backup. Two concurrent real PostgreSQL consumers of the same temporary fixture ticket admitted exactly one session; temporary records were removed without contacting a provider.
- Both virtual environments passed dependency consistency checks. The audio service is active with zero automatic restarts at verification; existing NEUROSIS services remain active.
- Public HTTPS browser tests passed connection creation/replacement/deletion, hidden key output and layout at 390/768/1440 px. Actual public WSS rejected an invalid grant. A browser-only socket fixture verified microphone worklet PCM capture, mute and stop. No provider connection success was simulated in persistent records.
- The original authenticated platform smoke test still passed, with no JavaScript errors. New views were visually inspected. Production checks retain only the two previously documented HSTS warnings.


Validation update (2026-09-13): Lucas reports successful OpenAI API-key setup and a real browser voice conversation. Gemini and physical hardware remain unvalidated. The revised Companion instructions discourage prompt disclosure; this is behavioral guidance, not a security guarantee. Provider keys remain outside model context and the model has no device-management tools.
