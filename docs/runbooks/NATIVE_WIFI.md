# Native Wi-Fi provisioning and credential storage

Candidate `0.1.9-wifi-storage-dev` hardens the existing protected local portal and prepares the persistence boundary needed by #18. **Improv Serial is not implemented yet.** The planned transport must reuse the [Improv Serial standard](https://www.improv-wifi.com/serial/) and [official C++ SDK](https://github.com/improv-wifi/sdk-cpp), with separate physical authorization, account ownership and setup timeout. Its protocol, UART/C6 adapter and browser integration still require implementation and validation.

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

Physical P4/C6 provisioning, same-SSID password replacement, wrong-password recovery, NVS power interruption, saved-network reconnection and Improv support remain unvalidated. Existing display/boot/OTA acceptance requirements also remain in [NATIVE_FIRMWARE.md](NATIVE_FIRMWARE.md) and [NATIVE_OTA.md](NATIVE_OTA.md). No production release or installation approval follows from these software checks.
