# Native OTA client

Candidate `0.1.5-ota-recovery-dev` integrates the native update worker with the [persistent backend](FIRMWARE_DEPLOYMENTS.md). The code implements authenticated polling, signed-policy verification, app-only inactive-slot streaming, progress, durable report retries, local cancellation and confirmed startup/rollback outcomes. Physical Wi-Fi OTA and recovery remain **unvalidated** (#26–#27). No board has been flashed by this implementation work.

## Build trust and release gates

An ordinary build has no publisher keys and build sequence zero: OTA execution is disabled. Supply independently reviewed **public** build inputs through `AMPVE_NATIVE_TRUST=/private/native-build.json` when building a release candidate. This configuration is outside Git and is not downloaded from AMPVE's device API:

```json
{
  "schema": 1,
  "build_sequence": 1,
  "testing_only": false,
  "trust": {
    "schema": 1,
    "minimum_sequence": 1,
    "revoked_releases": [],
    "keys": {
      "publisher-2026": {
        "public_key": "PUBLIC_ED25519_HEX_PLACEHOLDER",
        "channels": ["development"],
        "purposes": ["initial-install", "ota"],
        "revoked": false
      }
    }
  }
}
```

The placeholder is deliberately invalid. Generate/manage production signing material separately under the owner's approved process; never place private keys in this input, firmware, repository or device API. The build embeds public trust and a sequence, and archives their canonical metadata/header and hashes. The publisher refuses sequence mismatches, missing/mutated trust, sequence-zero builds and `testing_only: true` builds. At least one active OTA publisher is required for an enabled release build. The existing release, reproduction and bootloader/C6/recovery review gates still apply.

Use `testing_only: true` for an enabled compilation fixture. The binary may link the actual client, but its review package is explicitly marked as a software build fixture and cannot be promoted by the publisher tool. This marker does not replace the browser's installation/approval gates. No production signing key has been generated in this work.

For key rotation, an image signed by an already trusted publisher can carry the next independently reviewed public key. Keep the appropriate bridge keys until the intended installed versions can validate the next release. Server withdrawal is rechecked at download and boot authorization; an embedded trust snapshot alone cannot provide immediate offline revocation.

## Verification and write boundaries

`ota_policy.cc` uses pinned [Espressif libsodium 1.0.22~1](https://components.espressif.com/components/espressif/libsodium/versions/1.0.22~1/readme), hash `d4066b373fc6d4c5196db42aeea7faef4ac7f3080af96c2b74e2476c08b78dc1`. It checks Ed25519, canonical bounded JSON, exact release identity, expiry, independent key scope/revocation, predecessor and sequence floor, profile/layout/revision/flash, current bootloader/table fingerprints and actual inactive-slot capacity. cJSON stays at its existing pin. `CONFIG_LIBSODIUM_USE_MBEDTLS_SHA=n` uses libsodium's own SHA implementation. Review bundles preserve libsodium ISC and ESP-IDF Apache-2.0 notices; upstream sources stay outside Git.

The runtime reuses the canonical Waveshare 7B profile: `ota_0` at `0xA10000`, `ota_1` at `0xE00000`, each `0x3F0000` bytes. The target must be a recognized inactive app partition. The app image is never written over the running app, factory app, bootloader, partition table, NVS or shared assets; eFuses are not changed. ESP-IDF performs bounded inactive-slot erase/write and OTA metadata selection; the existing NVS journal/sequence writes are separate management state.

Requests use fixed HTTPS AMPVE paths, the revocable device bearer credential and POST JSON. Response-supplied URLs and redirects are not followed. Downloads require the exact content length. The client buffers/validates the image header and application descriptor before beginning the inactive-slot operation, then streams 4 KiB buffers, checks the complete file hash, calls ESP-IDF image finalization and re-verifies the stored target. It checks native policy again, obtains backend boot authorization and checks expiry before selection. A failed or uncertain selection is distinguished from a confirmed rollback.

The running identity hashes the complete verified application file, including its appended image digest, without unused slot space. `esp_partition_get_sha256()` is not a substitute for this file hash. Initial identity is reported only after successful local startup diagnostics and a checked `esp_ota_mark_app_valid_cancel_rollback()` result.

## Progress, interruption and recovery

The worker runs only after local startup confirmation and a successful authenticated heartbeat. LVGL remains on its existing task; microphone capture stays disabled. On-device status shows the written percentage. Settings includes **Cancel firmware download**; cancellation aborts the current stream or prevents boot selection. Keep power connected while the outcome is unresolved. TLS operations can delay processing cancellation until their bounded read timeout returns.

The versioned NVS journal is at most 2 KiB in the `ampve_ota` namespace. It stores job/device/release identity, previous/target hashes, target slot/sequence, accepted progress, the exact pending report and a schema-2 marker committed only after verified boot selection. Schema-1 journals migrate conservatively without inventing this missing marker. Each report is committed before sending and its acknowledgement is committed before advancing. Progress reports occur at 256 KiB intervals plus the final fragment; one maximum-size image remains well below the backend's 128-report bound. Failed saves stop work; NVS errors never trigger an erase.

A lost response is retried verbatim. A definitive rejection uses the authenticated job-status endpoint to reconcile the accepted sequence and stop further writes/selection. An earlier accepted request does not turn an expired or withdrawn authorization into permission. Queued cancellation races are resolved by the server's device lock.

Interrupted downloads **do not resume partially written bytes**. The client aborts the stream and reports failure, or recovers the retained journal after reboot and reports interruption. The owner can queue a fresh eligible job to restart the full download. No automatic repeated flash loop is used. Network reports retry at the management worker's bounded cadence; offline silence remains pending on the backend.

After a selected image restarts, confirmed startup plus the exact target hash produces `confirmed`. Reporting `rolled_back` additionally requires a durable record that **this job** selected the target, the predecessor still selected for boot, and an aborted/invalid target state. An inactive slot's old failure flag alone is insufficient. If selection succeeds but its journal commit fails, the client retains the rebooting job and does not request a restart; a later healthy target can still confirm itself, while an ambiguous predecessor requires inspection. Unreadable/inconsistent boot metadata also stays unresolved. A definite rejection before selection in the current process reports failure directly, regardless of stale slot flags.

Older journals preserve their exact pending report during migration. They can confirm a healthy target but cannot manufacture proof of a new rollback. A verified predecessor with non-failure target metadata can report a failed attempt. Only confirmed outcomes advance the durable sequence floor. The compiled sequence also prevents the newly running image from requesting older releases while its outcome acknowledgement is pending. A changed/unrecognized journal or running image stops the client for local recovery.

Neither a timeout nor compilation proves physical safety. A first USB installation has no guaranteed previous AMPVE fallback app. Stock/C6 compatibility, compatible bootloader rollback behavior, power interruption, real transport loss, native display responsiveness and recovery must be tested with the exact approved artifacts and the owner's retained backups.

## Software checks

Run the normal isolated ESP-IDF build from [NATIVE_FIRMWARE.md](NATIVE_FIRMWARE.md). The enabled build fixture uses public-only temporary test trust, retains no private test signing key and is never selected by the public installer. To run the native host checks, compile the resolved libsodium sources outside their managed component:

```bash
AMPVE_OTA_WORK="$HOME/.cache/ampve-firmware/xiaozhi-ota"
AMPVE_SODIUM_HOST="$HOME/.cache/ampve-firmware/sodium-host"
mkdir -p "$AMPVE_SODIUM_HOST"
(cd "$AMPVE_SODIUM_HOST" && bash "$AMPVE_OTA_WORK/managed_components/espressif__libsodium/libsodium/configure" --disable-shared --enable-static --enable-minimal)
make -C "$AMPVE_SODIUM_HOST" -j2
"$HOME/.cache/ampve-firmware/tooling/bin/python" firmware/tests/native/run.py \
  --work "$AMPVE_OTA_WORK" --sodium-host "$AMPVE_SODIUM_HOST"
"$HOME/.cache/ampve-firmware/tooling/bin/python" -m unittest discover -s firmware/tests
AMPVE_TESTING=1 .venv/bin/python apps/platform/manage.py test workspace --noinput
.venv/bin/python tests/postgres/deployments.py
```

The native runner checks the dependency lock and compiles the actual policy/client/identity modules with AddressSanitizer and UndefinedBehaviorSanitizer. Policy tests use temporary signed fixtures. Client tests simulate the transport, server and hardware boundary, covering lost claim/progress/verify/reboot/outcome responses, network loss, cancellation, hash/selection/storage faults, process interruption, revoked authorization and unknown boot selection. Identity tests stub ESP-IDF partition/metadata calls. These prove software behavior at those boundaries, not actual flash/HTTP driver operation on the P4. The ESP-IDF build separately checks the native adapter's compilation/linking and image capacity.

## Earlier foundation evidence

PR #44's `0.1.3-ota-verify-dev` app was 2,768,208 bytes, SHA-256 `4af935c10210ea1dac5aa21b2e2172117a5856773fc2945857d4ac37cd7fb85e`, with 61 policy, nine streaming-identity and 26 firmware-tool cases passing. Its private non-installable review package was traced to source `0046077`. That result did not include the integrated client. Neither that build nor this integration inherits the earlier candidate's two-build reproduction evidence.

## Integrated client evidence — 2026-09-13

The enabled **software fixture** compiled and linked for ESP32-P4 revision 1.x with the pinned toolchain and no compiler warnings. App: **2,842,096 bytes**, SHA-256 `e886c4118cad39a7c132998c278c3d25c7a5564cace53b42c707a15b1dea72ae`; IDF's capacity check passed with 31% remaining in the smallest app slot. The private package `firmware-ota-client-software-fixture` is traced to source `170ac1d`, explicitly `testing_only: true` and `installable: false`. It is not a candidate for physical installation or production signing. No private fixture signing key was retained. The public browser review selection was unchanged.

Validation passed: **61 policy cases**, **nine streaming-identity cases**, **21 client scenarios**, **31 firmware-tool tests**, **67 Django tests** (five PostgreSQL-only cases skipped there) and **21 isolated PostgreSQL lifecycle/concurrency cases**. The backend status/boot-selection-failure support was restarted on the VPS; no database migration was needed, platform/audio/database remained active and public HTTPS health passed. The two existing HSTS subdomain/preload warnings remain. Adapter calls compiled against ESP-IDF, but actual device HTTP/flash faults and physical power interruption are still acceptance work. Build reproduction for this changed candidate is not yet demonstrated.
