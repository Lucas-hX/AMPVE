# Platform foundation

Date: 2026-09-13
Architecture: [ADR 0001](../decisions/0001-platform-architecture.md)

## Scope

Implemented: English public landing, private workspace, email/password sign-in, POST logout, CSRF protection, secure database-backed sessions, own-name profile editing, password changes, Django administration, persisted Companion preview catalog, and truthful empty device/provider/setup pages. No public registration. Lucas is a normal user; administration is a separate account.

Not implemented: encrypted provider credential storage, connection tests, FastAPI/Pipecat sessions, real device enrollment, USB flashing, firmware, Companion activation, OTA, or camera. Buttons on preview pages navigate to explanatory content; no fake devices or successful integrations are created.

## Runtime

Debian 13.6 x86_64; Python 3.13.5; PostgreSQL 17.11 shared server. Exact Python packages are pinned in `requirements.txt`: Django 5.2.17, Gunicorn 23.0.0, WhiteNoise 6.12.0, psycopg 3.3.5 and django-axes 8.3.1 plus transitive dependencies. Browser tooling is separate in `requirements-dev.txt`.

Service: `ampve-platform.service`, running as `ampve`, two Gunicorn workers on `127.0.0.1:3000`. Static assets use WhiteNoise. Existing Cloudflare Tunnel supplies HTTPS for `ampve.com`. The origin trusts the secure-proxy header only because it is loopback-only; do not expose it publicly. Axes accepts Cloudflare's overwritten client-IP header only from a loopback peer. Local system users are part of the trusted VPS boundary.

PostgreSQL uses `/run/postgresql-neurosis`, port 5433. AMPVE has its own `ampve` database owned by login role `ampve` (no superuser/create-role/create-database privileges). A narrow `local ampve ampve peer` rule was added before the existing reject rule in `/etc/neurosis/pg_hba.conf` and reloaded without restarting PostgreSQL. Previous configuration: `/etc/neurosis/pg_hba.conf.pre-ampve`. NEUROSIS databases, credentials, and services remain separate.

The initial tunnel configuration contained the literal `${AMPVE_HOSTNAME}`. It was replaced with `ampve.com`; the prior file is `/home/ampve/.cloudflared/config.pre-platform.yml`. The existing AMPVE tunnel is now supervised by enabled `ampve-tunnel.service` so it starts on reboot. Its former PM2 entry is retained stopped; do not start both supervisors. The same tunnel ID, credential file and ingress configuration are reused. NEUROSIS tunnel supervision was not changed. The apex DNS A record still pointed to the registrar (192.64.119.39); it was changed to the AMPVE tunnel CNAME. Existing MX/TXT records were preserved, and the previous records were saved privately at `/home/ampve/.config/ampve/dns-before-platform.json`. Docker is not installed: this first deployment uses the existing systemd/Unix-socket environment, with Compose deferred as documented in the ADR.

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

Install the reviewed service file with `sudo install -m 644 infra/ampve-platform.service /etc/systemd/system/ampve-platform.service`, then `sudo systemctl daemon-reload` and `sudo systemctl enable --now ampve-platform`. Paths in this unit are specific to this VPS. After code updates, run migrations/checks/collectstatic, then `sudo systemctl restart ampve-platform`.

`/health/` checks HTTP process liveness only, not database readiness or AI availability. Use authenticated page checks for database-dependent behavior. Existing services can be checked with `systemctl is-active neurosis-api neurosis-postgresql neurosis-cloudflared`.

Production checks intentionally leave HSTS subdomain inclusion and preload disabled: AMPVE does not establish HTTPS policy for every subdomain. Root-domain HSTS is set to one hour. These two Django deployment warnings are documented, not suppressed. DEBUG is off; session and CSRF cookies require HTTPS.

Axes locks an account or source IP after five failed sign-ins for 15 minutes using persisted database records across workers. Use the maintained `axes_reset` management command if an administrator needs to clear a lockout. Public registration and email password recovery are intentionally unavailable; use the authenticated password form or the administrator's password reset interface.

## Backup and recovery

Existing NEUROSIS backup jobs must not be assumed to include AMPVE. Back up the dedicated database with `pg_dump -h /run/postgresql-neurosis -p 5433 -U ampve -Fc ampve` to private storage and separately protect `platform.json`. Database dumps contain account hashes/session data and must not enter Git or static storage. A daily `ampve-backup.timer` now runs at 04:20 UTC plus up to five minutes jitter, retaining seven days in `/home/ampve/.local/state/ampve/backups` with private permissions. The initial dump was successfully restored into a separate temporary database and verified to contain two accounts and the Companion catalog entry; that temporary database was then removed. Off-VPS backup and separate secret-key backup scheduling remain operational follow-ups.

To stop only this application: `sudo systemctl stop ampve-platform`. Preserve the database and private configuration when reverting application code. Do not roll back migrations blindly; review schema changes first. Restore tests must use a separate database. Never drop or restore over NEUROSIS as part of AMPVE recovery.

Expired Django sessions can be removed with `manage.py clearsessions`. Authentication metadata retention should be periodically pruned with the Axes cleanup commands; `ampve-maintenance.timer` runs daily at 04:40 UTC plus up to five minutes jitter, clearing expired sessions and Axes success/failure logs older than 30 days.

## Verification evidence

- 13 Django automated tests passed: access control, CSRF, session cookie flags, POST logout, normal/admin separation, profile ownership and privilege injection, password checks and session invalidation, redirect safety, persisted rate limiting, inactive accounts, email uniqueness, preview states and trusted-proxy IP handling.
- All production PostgreSQL migrations applied; no pending model changes.
- Local HTTP origin and public HTTPS return 200; existing NEUROSIS services remain active.
- Production deployment checks report only the two intentionally deferred HSTS policy warnings described above.
- Database backup restoration succeeded in an isolated temporary database.
- Application, tunnel, backup and maintenance units are enabled for boot; systemd unit verification passed. No VPS reboot was performed.
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

1. Encrypted user-owned provider connections and real Pipecat audio sessions with Gemini Live and OpenAI Realtime, using a development audio client first.
2. XiaoZhi adapter proof with Opus software fixtures, cancellation and per-user authorization.
3. Pinned firmware/toolchain and recovery preparation on the owner's local computer, then explicitly approved physical installation.
4. Enrollment, Companion settings/acknowledgement, real voice/face and tested OTA recovery.

This foundation alone does not satisfy the full provider-path or hardware MVP acceptance criteria.
