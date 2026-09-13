# Device inspection, pairing and management

Date: 2026-09-13. This delivery implements browser ROM inspection and the management server. The [native XiaoZhi shell](NATIVE_FIRMWARE.md) now implements enrollment/heartbeat as a development candidate. A verified installer, physical validation, XiaoZhi audio adapter and OTA remain pending. No physical board is reachable from this VPS. Tests use explicitly named software fixtures.

## What works now

- **My devices → Add a device:** select a local serial port with Web Serial. Browser permission is explicit; no network/USB scan runs on page load. USB VID/PID are local hints, not board identity.
- **Inspect ESP chip:** after a separate reset notice, the locally bundled esptool-js 0.6.1 synchronizes with the ROM, reads chip identity and P4 revision, attempts a reset, then releases the port. No stub, flash write/erase, bootloader/partition change or eFuse programming is requested. Results stay in the page, not browser storage or the server. Lucas confirmed ESP32-P4 v1.3 through this inspection; flash/layout/security and exact board model still need the local audit. Failure may require BOOT/RESET or power reconnection.
- Authenticated owners can claim an AMPVE pairing code, view their devices, rename/change desired volume/mute, inspect device-reported software/network state and revoke credentials. Administrators do not bypass owner checks on these routes.
- Device endpoints implement expiring pairing, credential exchange and authenticated heartbeat/configuration acknowledgement. Stock XiaoZhi does not call them yet. Selecting a port does not create a production device or prove manageability.
- Online requires a heartbeat within 90 seconds. Desired settings are pending until the device explicitly acknowledges their version. Device-reported metadata is not hardware attestation. Refresh pages to see new state.

## Distinct connections

| Connection | Meaning |
|---|---|
| USB serial | Local browser inspection and future approved installation; not permanent remote access |
| Wi-Fi | The enrolled firmware initiates outbound HTTPS to AMPVE; the PC can disconnect |
| Ethernet | Contract can record an Ethernet report; physical Ethernet support is not validated here |
| USB power only | Does not give the board a management connection |
| Raspberry Pi | Future Linux client/runtime; not auto-discoverable or supported by this board flow |

Web Serial cannot enumerate every device or scan the user's LAN. Exact board confirmation still needs its label and the original audit. Chip family alone cannot distinguish Waveshare 7B from every other P4 board. ESP Web Tools stays the installer choice, gated on a verified release; esptool-js is used now for inspection.

## Device contract v1

All routes use HTTPS at `https://ampve.com`, POST, JSON bodies up to 2048 bytes and no query-string secrets. Successful and failed responses use `Cache-Control: no-store` via Django's never-cache decorator. Firmware validates the TLS certificate and must never log proofs, credentials or complete response bodies. Browser cookies are ignored as device authentication. No provider keys or model prompts appear in this contract.

1. A locally initiated pairing action on firmware POSTs `/api/devices/v1/enroll/` with `{"protocol":1,"hardware_profile":"waveshare-esp32-p4-wifi6-touch-lcd-7b"}`. The server returns `enrollment_id`, a 12-character human `code`, a random 256-bit `bootstrap_proof`, `expires_in:600`, and `poll_interval:5`. Display only the human code locally. Pending pairing is not an owned/online device. Hardware profile is a client claim, not a factory certificate.
2. The signed-in owner enters that code and confirms physical access on `/devices/add/`. A transaction claims it once and creates an **Awaiting device** record. Codes/proofs are SHA-256 hashed in PostgreSQL. Codes expire after ten minutes. No MAC/serial number establishes ownership.
3. Before polling, firmware generates 32 random bytes with ESP-IDF's cryptographic RNG, base64url-encodes without padding (43 characters) and persists the resulting device credential locally. POST `/api/devices/v1/enroll/{enrollment_id}/exchange/` with `Authorization: Bearer BOOTSTRAP_PROOF_PLACEHOLDER` and `{"credential":"DEVICE_GENERATED_CREDENTIAL_PLACEHOLDER"}`. These placeholders are deliberately not accepted credentials. Before claim, the result is 202/pending. After claim it is 200/claimed with `device_id` and `heartbeat_interval:30`.
4. The server stores only the credential hash. Retry with the exact same proof/credential after a lost response is idempotent until pairing expiry. A different credential cannot replace the original. Revocation and an inactive owner block reissue. Lost local state or expired exchange requires a fresh physical pairing action; there is no identity recovery by MAC. Remove bootstrap material after successful exchange. Enrollment rows expire through the maintenance job.
5. Every 30 seconds POST `/api/devices/v1/{device_id}/heartbeat/` with the **device credential**, not bootstrap proof. Body: `{"protocol":1,"firmware_version":"ampve-development","chip_revision":"1.3","transport":"wifi","acknowledged_version":0}`. These metadata values are examples, not a shipped release. Reply contains desired `configuration` (`version`, `name`, `volume`, `microphone_muted`), polling interval, and currently `audio_available:false`, `ota_available:false`.
6. Apply a configuration snapshot locally and persist its revision only after successful application, then report that exact revision. Older-than-acknowledged and newer-than-desired acknowledgements are rejected. After local state loss, re-pair instead of fabricating an acknowledgement. Local stop/mute overrides remote preferences; settings cannot start a cloud audio session. Firmware must not interpret names or responses as executable code.
7. Revoke through the CSRF-protected dashboard. The server immediately rejects further heartbeat authentication and bootstrap reissue; this does not erase the device or stop local functions. A later audio adapter must check this same revocation state throughout a session.

Limits: five starts per source IP per ten minutes, 60 starts globally per ten minutes, six claim attempts per account per minute, 20 retained device records per account, 150 authenticated exchange polls per enrollment per ten minutes and heartbeat no faster than five seconds. Expected cadence remains 30 seconds. Limits are durable fixed-window PostgreSQL counters, not a public-scale abuse service. Use backoff/jitter for 429 and outages. Invalid enrollment IDs do not create counters. Public registration is disabled. Tokens are capability credentials on a trusted private instance; no hardware attestation, cloning resistance or secure-element guarantee is claimed.

## Deployment and verification

Build browser assets before collectstatic:

```bash
npm ci --prefix tools/browser --ignore-scripts
npm run build --prefix tools/browser
node --test tools/browser/inspect.test.js
AMPVE_TESTING=1 .venv/bin/python apps/platform/manage.py test workspace --noinput
.venv/bin/python apps/platform/manage.py migrate --noinput
.venv/bin/python apps/platform/manage.py collectstatic --noinput
.venv/bin/python apps/platform/manage.py check --deploy
```

The platform's existing service, database and tunnel serve all device routes; no extra host agent, network port or runtime service was installed. Install the updated `infra/ampve-maintenance.service`, daemon-reload and restart the platform after migration. `cleanup_device_metadata` removes expired enrollments and rate buckets older than a day. Retained device records are not deleted by this cleanup. Back up before migrations.

Automated device tests cover single claiming, pending/expired exchange, hashed secrets, idempotent retry, credential replacement rejection, owner/admin isolation, CSRF, revocation, inactive users, stale presence, acknowledgement bounds, input limits and throttling. Browser chip tests substitute ROM/transport objects; they do not prove USB compatibility. Real hardware testing must happen on Lucas's computer.

## Next hardware milestone

Follow [the pinned XiaoZhi integration plan](../../firmware/xiaozhi/README.md). First collect the real chip inspection result and confirm the exact 7B unit against its private backup/audit. Then implement the embedded management task, pin the toolchain/component lock, and prepare reproducible firmware plus a curated ESP Web Tools manifest with exact write regions and recovery. Only then approve and perform the first flash. Validate display/touch/audio/Wi-Fi and the full pairing/heartbeat/settings/revocation loop with the physical board. Opus/Pipecat and OTA recovery follow; the browser voice preview remains independently usable.

## Delivery evidence

- 39 Django tests passed, including 13 new device tests; two bundled JavaScript ROM-inspection tests passed. The existing ten Pipecat fixture tests also passed after the prompt update.
- The production PostgreSQL migration applied after a backup. Two concurrent claims of one temporary pairing code admitted exactly one owner; the temporary device/enrollment was removed.
- `tests/browser/devices.py` exercised the actual public HTTPS pairing/exchange/heartbeat/settings/revocation flow with an explicitly labeled software client, checked layout at 390/768/1440 px and stubbed only browser port selection. It cleans up its temporary device. No physical chip inspection or provider call occurs in this test.
- The existing authenticated platform smoke test still passes with no JavaScript errors. New onboarding/device screens were visually reviewed. Services remained active; deployment checks retain only the two previously documented HSTS warnings.
- Physical P4 detection, firmware operation and revised prompt behavior against a live model are pending owner testing. The OpenAI conversation success was reported by Lucas before the prompt revision; Gemini remains pending.


Device-shell update (2026-09-13): Lucas reports a successful physical ROM inspection: ESP32-P4 v1.3 via USB 0x1a86:0x55d3. This validates chip inspection only. The runtime/UI/recovery design is recorded in [ADR 0003](../decisions/0003-device-runtime-and-recovery.md). A browser interface concept and bounded capability-report storage are implemented; native firmware and functional peripheral tests remain pending.

## Capability report extension and interface concept

The v1 heartbeat optionally accepts hardware_report without breaking existing clients. Its exact schema is enforced by workspace/hardware_reports.py:

- schema: integer 1.
- flash_bytes and psram_bytes: measured nonnegative byte counts (up to 1 GiB), or null for unknown.
- display: null or integer width/height (1–4096).
- capabilities: exactly display, touch, speaker, microphone and wifi, each using unknown/configured/initialized/passed/failed/unavailable.

Unknown fields (including credentials or arbitrary diagnostic strings) are rejected; the overall 2048-byte request cap remains. A complete report replaces the prior snapshot and timestamps it. Omitting the optional report preserves its previous snapshot and timestamp. These fields never alter ownership, credential validation, provider access or release eligibility.

The dashboard shows reported memory, display geometry and separate capability statuses. Unknown memory remains “Not reported”, not zero. The future native client must use SDK measurements, known-profile driver initialization and explicit functional tests as appropriate. A recognized audio codec alone cannot establish that a physical speaker produces sound.

The private /devices/interface-preview/ page is an interactive, English web design concept using the existing symbol avatar and Companion icon. All network/mute/speaker interactions are simulated locally; no API call, Wi-Fi password, microphone capture or real pairing is involved. It is linked from Add a device.

Delivery checks: 42 Django tests passed; public browser checks covered five concept screens at 390/768/1440 px without horizontal overflow or network requests during interactions. A separate temporary software-client test covered actual PostgreSQL storage and dashboard display of the optional hardware report. No firmware or physical peripheral was tested.
