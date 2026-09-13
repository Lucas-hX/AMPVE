# Firmware deployment backend

The Django/PostgreSQL backend persists owner-requested app updates and device-reported outcomes. The native OTA client is implemented as a development candidate; physical download, boot confirmation and rollback tests remain pending (#26–#27). See [NATIVE_OTA.md](NATIVE_OTA.md). No production signed release is currently imported. Software fixtures are not hardware evidence.

## Release and identity prerequisites

Follow [FIRMWARE_RELEASES.md](FIRMWARE_RELEASES.md) for independent publisher trust and the signed schema-2 policy. Import reviewed packages from private immutable storage outside Git:

```sh
.venv/bin/python apps/platform/manage.py register_firmware_release --directory /private/reviewed-release
.venv/bin/python apps/platform/manage.py revoke_firmware_release RELEASE_ID
```

Import does not queue a deployment. Release identity is the canonical policy hash; a compatibility scope/channel/sequence cannot be reused. Withdrawal retains history. Requests, download and boot-selection authorization revalidate current signature/trust, expiry, hashes and hardware compatibility. The target must explicitly permit the confirmed predecessor hash and have a higher sequence. Only the canonical Waveshare 7B profile is currently supported.

After a matching schema-2 heartbeat, the authenticated device must report its initial installed app hash, confirmed boot and matching firmware version. The hash must match an imported trusted initial-install release. This is a device report, not hardware attestation. Subsequent firmware changes must complete their authorized deployment.

## Owner workflow

The device page links to Firmware updates. Only its owner can select an eligible release, queue an update, view history or cancel it. An administrator does not bypass ownership. Browser writes require login and CSRF. Each submitted UUID request key identifies one immutable request, including after cancellation. The device row lock and database constraint permit at most one active deployment.

An offline device stays queued until it reconnects. Cancellation is allowed only before download starts; cancellation and the device claim serialize on the same lock. Device revocation stops future authenticated operations, cancels queued jobs and flags started jobs as uncertain. It cannot stop bytes already delivered or physically undo a selected boot partition.

## Device protocol v1

All endpoints below require POST, application/json and the revocable device bearer credential. Browser cookies do not authenticate them. Payloads are bounded to 2 KiB; requests are limited to 180 per ten minutes per device. Never place credentials in URLs. All paths start with `/api/devices/v1/<device UUID>/`:

| Suffix | Request / response |
| --- | --- |
| `firmware/identity/` | `{protocol: 1, app_sha256: HASH, boot_confirmed: true}` establishes the initial baseline. |
| `updates/poll/` | Same request; returns `deployment: null` or the current job, report sequence, bytes, previous hash and authorization information. A rebooting target can poll without advancing the confirmed baseline. |
| `updates/<job UUID>/report/` | Exact fields: `release_id`, integer `sequence`, `state`, integer `bytes_written`, running `app_sha256`, boolean `boot_confirmed`, `error_code`. Returns the accepted state. |
| `updates/<job UUID>/status/` | `{release_id: HASH}` returns the retained state/sequence, including terminal jobs, to reconcile rejected or lost authorization responses. |
| `updates/<job UUID>/artifact/` | `{release_id: HASH}` downloads only the claimed job's currently authorized app. No arbitrary URL, redirect or filesystem path is accepted. |

The examples describe JSON fields; replace HASH with a 64-character lowercase SHA-256 string. Poll includes the signed envelope only while authorization remains valid. `download_allowed` is true only after an accepted downloading claim. The client must independently verify the publisher, policy, profile, predecessor, sequence, image hash and inactive-slot capacity before selecting the next boot image. Server authorization alone cannot implement those checks.

The normal sequence is queued → downloading → verifying → rebooting → confirmed. Queued/downloading/verifying may report failed; rebooting may report rolled_back or a bounded boot-selection failure with the confirmed predecessor. Unclaimed failures must report zero written bytes. Begin downloading at zero bytes; subsequent same-state progress must strictly increase by at least 64 KiB, except the final fragment. Verifying and later states require the complete app size. Reports are numbered 1–128 without gaps; exact latest-report replay is idempotent. Persist the job and report locally before sending so a lost response can be retried. Replayed downloading/rebooting authorization is rechecked, not treated as perpetual permission.

Before rebooting, the running hash remains the predecessor. Confirmed requires the expected target hash and confirmed startup. Rolled_back requires the predecessor hash and confirmed startup. Only confirmed advances the server baseline; silence never does. Outcomes can still be recorded after release approval expires or is withdrawn, provided device authentication remains valid. This preserves reported physical truth. Failure reasons are bounded: network, hash_mismatch, image_rejected, storage, approval_unavailable boot_failed or local_cancelled; other states use an empty string. Free-form device logs are not accepted.

## Reconciliation and recovery

Install `infra/ampve-firmware-maintenance.service` and `.timer` in systemd and enable the timer. Every five minutes, with jitter, it checks up to 200 active jobs, rotating by last check. Queued requests expire at the earlier of release expiry and seven days; invalid trust or owner/device revocation also cancels queued work. Started jobs without progress for 15 minutes or with expired approval are marked as needing attention. They remain active until an authenticated outcome; a timeout or VPS restart does not manufacture success, failure or rollback. Historical rows/events are retained for idempotency and audit; each job's device event count is bounded. Database backup is required before migrations.

Run reconciliation manually with `manage.py reconcile_firmware_deployments`. After a VPS restart it reads persistent state without starting downloads. An unresolved started job requires local board inspection and its private recovery files. Do not delete it to force another update while the physical outcome is unknown.

## Software validation

```sh
AMPVE_TESTING=1 .venv/bin/python apps/platform/manage.py test workspace --noinput
.venv/bin/python tests/postgres/deployments.py
```

The PostgreSQL runner creates a temporary cluster with peer authentication and a private Unix socket, no TCP listener, and removes it afterward. It tests concurrent identical/conflicting requests, cancel/claim races, confirmation replay and fresh-process reconciliation. It never changes the deployed database or its roles. Lifecycle tests use temporary signed synthetic app fixtures. Physical Wi-Fi OTA, power interruption and rollback remain separate acceptance gates.

VPS validation (2026-09-13): migration 0006 applied after the private database backup completed; the reconciliation timer is enabled and its first invocation succeeded. The platform and audio services stayed available, and public HTTPS health passed. The Django suite passed 65 tests with five PostgreSQL-only cases skipped; the isolated PostgreSQL run passed all 19 lifecycle/concurrency cases. A temporary browser device fixture exercised the new empty-state update page at 390, 768 and 1440 pixels and was removed. No production release, deployment or publisher key was created. Deployment checks retain the two existing HSTS subdomain/preload warnings.

## Native verification foundation

See [NATIVE_OTA.md](NATIVE_OTA.md) for the `0.1.3-ota-verify-dev` candidate: native signed-policy verification, complete-image hashing and checked startup identity reports. The integrated download/write client follows in `0.1.4-ota-client-dev`; physical OTA/rollback remain pending.
