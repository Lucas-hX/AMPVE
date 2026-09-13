# Native Wi-Fi provisioning and credential storage

Candidate `0.1.10-improv-dev` implements Improv Serial and the browser Wi-Fi form for the P4 7B development profile. It reuses the official C++ SDK 1.2.7 at `8e87b560bd5dd7de296847538ea11edb70401d65` (Apache-2.0) and browser SDK 2.8.0. This is software-tested development work; physical UART/P4/C6 provisioning remains unvalidated.

## USB setup and authorization

Boot the AMPVE application, open **Wi-Fi** on the board, then select **Connect for Wi-Fi setup** in `/devices/add/`. Local touch or the existing five-second BOOT action authorizes five minutes of serial provisioning. Booting into the fallback AP alone does not authorize serial credential changes. No other board/headless profile is enabled by this integration; each needs its own reviewed physical setup control and hardware adapter.

UART0 uses 115200 baud on the existing pins. The service refuses an already-installed UART driver. Improv identification/current-state requests work without setup authorization, but Wi-Fi writes require the active local window and ready credential storage. Supported RPCs are device information, current state and Wi-Fi settings; network scanning is explicitly unsupported, so the browser offers manual SSID entry. Frame storage is bounded, incomplete frames expire, and payload lengths are checked before the pinned SDK parser. Serial-bound ESP logs escape control bytes; Improv packets share the stdout lock and include line boundaries.

Portal and serial configuration share a nonblocking transaction lease. A second request fails while one tests/saves a network; AP shutdown defers until the transaction exits. Both paths check the five-minute deadline before association and before storage. Serial success requires checked saving followed by actual station reconnection to the requested SSID within 60 seconds. Connection, storage uncertainty and expiry errors do not produce a success response. The protected local portal remains the fallback.

The browser closes its ROM reader before opening Improv and shares the same busy controls with audit/install actions. It checks the reported AMPVE/profile identity before enabling Wi-Fi submission; this is not cryptographic device identity or account ownership. It never follows device-provided URLs. Pairing remains a separate account operation on the same page. Wi-Fi passwords are cleared from the input before awaiting the serial operation; they are not sent to the server, browser storage or SDK logs. JS/SDK transient memory is not a secure-erasure guarantee.

`tools/browser/improv-build.js` applies exact-match build-time fixes to the pinned browser SDK: initialization rejection propagation, write failure propagation, writer-lock release and pending-RPC rejection on disconnect. Upstream files and license remain intact; changed integration points fail the build. The firmware review package includes the pinned C++ SDK source/license and its manifest entry.


## Checked persistence

The pinned Wi-Fi component delegates credential persistence to AMPVE's small NVS/cJSON adapter. A bounded, schema-versioned blob in `ampve_wifi/networks` contains the active list and the previous list together. It holds at most ten networks in each list and at most 16 KiB including the terminator. SSID/password byte lengths, channel values, duplicate names, schema structure and canonical encoding are checked. Credentials are never included in logs or sent to the AMPVE server by this adapter.

When no AMPVE record exists, the legacy `wifi` namespace is imported read-only. Missing first-use storage is valid; orphaned, malformed, wrong-type or unreadable records stop initialization. Legacy keys are never changed or erased by this adapter. An invalid AMPVE blob does not silently fall back to an empty or older list. The native startup guard refuses to confirm startup when the credential store is unavailable.

Every mutation checks NVS open, single-blob write and commit. The new active list is exposed in memory only after success. Failure restores the previous in-memory list, marks storage unavailable and blocks further mutations until restart. Reads return locked snapshots; add/remove/default/channel/clear operations serialize through the same mutex. This prevents concurrent channel updates and configuration writes from losing one another's in-memory changes.

A failed write or commit can be **uncertain**: the new complete record might already be persisted. The record contains the previous credentials as well as the candidate; the legacy namespace also remains intact. After restart, a valid persisted active list is loaded. The portal therefore says it could not confirm saving, rather than promising that flash is unchanged. This is not a claim of physical power-loss atomicity. The previous list is retained for audited local recovery, not exposed as an automatic remote restore operation. Removing/clearing the active list does not securely erase the previous snapshot or untouched legacy keys.

## Portal behavior

The protected portal still tests association before saving credentials. Wrong passwords, unavailable APs and bounded connection timeouts do not invoke credential storage. A rejected `esp_wifi_set_config()` result now returns failure instead of aborting. The existing two-attempt/23-second connection wait budget for this 2.4-GHz profile remains; actual driver-call latency is unvalidated.

A failed or uncertain save returns an explicit failure response. Delete/default operations report storage errors; their browser controls become usable again and display the failure. Password-widget clearing, same-origin/API-header checks, AP-interface restriction and the per-boot WPA2 secret remain in place. SmartConfig has not been enabled; its inherited credential log was removed and its save result is checked.

## Software checks and remaining acceptance

```bash
python3 firmware/tests/native/credential_run.py --work "$HOME/.cache/ampve-firmware/xiaozhi-ota"
python3 firmware/tests/native/wifi_connect_run.py --work "$HOME/.cache/ampve-firmware/xiaozhi-ota"
.venv/bin/python firmware/tests/browser_provisioning.py --component "$HOME/.cache/ampve-firmware/xiaozhi-ota/components/78__esp-wifi-connect"
```

The credential runner compiles the actual adapter and transformed SSID manager against the pinned cJSON implementation, with simulated NVS. It covers legacy import, malformed/bounded records, errors before/after a write, uncertain commits, retained credentials, frozen retries, list operations and concurrent callers. The connection runner compiles the actual transformed connection method against simulated driver/event calls. Both use ASan/UBSan. The Chromium fixture serves the actual patched portal with simulated responses; it does not connect to a board.

Physical UART/P4/C6 provisioning, same-SSID password replacement, wrong-password recovery, NVS power interruption, saved-network reconnection and Improv support remain unvalidated. Existing display/boot/OTA acceptance requirements also remain in [NATIVE_FIRMWARE.md](NATIVE_FIRMWARE.md) and [NATIVE_OTA.md](NATIVE_OTA.md). No production release or installation approval follows from these software checks.

Software evidence (2026-09-13): **23 credential-storage scenarios**, **eight connection scenarios**, the **Chromium portal fixture** and **31 firmware-tool tests** passed. The final enabled P4 revision-1.x fixture compiled without compiler warnings; adapter/SSID-manager/overlay sources matched repository inputs. App: **2,847,792 bytes**, SHA-256 `da101f7a027d24dfcc3e6d67cc4c07728711d060d68a0707f366a26173496292`, 31% slot space remaining. Private `firmware-wifi-storage-software-fixture` is traced to `49155d7`, testing-only/non-installable. This revision has no two-build reproduction claim. No hardware, selected public installer release, production key or service configuration changed.


Improv checks:

```bash
python3 firmware/tests/native/improv_run.py --sdk "$HOME/.cache/ampve-firmware/improv-sdk"
python3 firmware/tests/native/provisioning_run.py --work "$HOME/.cache/ampve-firmware/xiaozhi-ota"
npm test --prefix tools/browser
.venv/bin/python tests/browser/onboarding.py
```

The protocol runner compiles the actual native core and pinned SDK under ASan/UBSan, exercising authorization, malformed frames, checksum errors, resynchronization, connection/storage failures, expiry and bounded reconnect. The lease runner compiles the prepared AP transaction/shutdown methods with a simulated radio and concurrent callers. The browser tests run the patched official SDK against simulated serial streams, including unsupported firmware, failed writes and disconnects. Chromium tests the actual onboarding form, password clearing, shared busy controls, unchanged URL and absence of uploads. These are not physical interoperability evidence.

Before installation approval, validate the exact original bootloader/C6/recovery route and use a reviewed signed release. Then test USB provisioning, wrong passwords, an unavailable AP, expiry during association, disconnect during save, saved-network reboot, portal fallback, and retained credentials after failure. Measure UART task stack/headroom and responsiveness alongside the existing native acceptance checks. No production trust key or installer selection is changed by this candidate.

**Historical incremental build evidence, superseded by the [timestamp/reproduction correction](FIRMWARE_REPRODUCIBILITY.md):** software evidence for `0.1.10-improv-dev` (2026-09-13): **20 native Improv scenarios**, **nine provisioning lease/expiry scenarios**, **27 browser tests**, the rendered Chromium onboarding/portal fixtures, **31 firmware-tool tests**, and **72 Django tests (five existing skips)** passed. The final P4 fixture compiled without compiler warnings: **2,877,232 bytes**, SHA-256 `32a9688ebaee77f833dffb76d98aa4c971ddad0ce54289c6ae1c7bde381dccb7`, 30% slot space remaining. It uses public-only testing trust and is non-installable; this revision has no independent two-build reproduction claim.

Historical private review bundle `firmware-improv-software-fixture` (superseded; do not use as compiled-source evidence) records source `e66b2ba`, the exact generated inputs and pinned Improv component/license. Packaging confirmed `installable=false`; the selected public installer bundle is unchanged.
