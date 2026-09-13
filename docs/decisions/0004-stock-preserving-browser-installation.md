# ADR 0004 — Stock-preserving ESP32-P4 browser installation

Date: 2026-09-13. Status: accepted development direction; exact first hardware write remains unapproved.

## Decision and evidence

Lucas authorized implementing a stock-preserving design, review artifacts and browser onboarding. His 2026-09-13 local handoff reports a printed Waveshare 7B, P4 revision 1.3, 32 MiB flash, disabled Secure Boot/download security/encryption, two independently read matching full backups, an MD5-verified partition table and an erased stock `ota_1`. He subsequently confirmed that the original application boots after the audit. A verified copy on separate storage is still awaiting confirmation.

Treat these as owner-supplied physical evidence, not VPS-observed hardware tests. The current implementation must freshly check the connected unit. The full backup SHA-256 reported by the owner is `da6a7276ef6198f1e83089acd94362f5b3a6d64246a0df35ba94bbaf8393d3a3`. No private flash, NVS, serial logs or device identifiers are committed or uploaded.

For this exact profile, retain the original partition map and bootloader. Build against `firmware/xiaozhi/partitions/7b-stock-v1.csv`; the generated partition binary is an offline comparison artifact, **never an installer write**. The owner supplied names/offsets/sizes; entry types/subtypes/flags must also match the generated binary locally before approval. A different table requires review, not an automatic migration.

Initial installation proposes `ota_1` at `0xE00000` (capacity `0x3F0000`). Keep factory at `0x110000`, stock XiaoZhi `ota_0` at `0xA10000`, assets, storage, NVS regions and the bootloader/table unchanged by the installer. Pad the app only to its final 4 KiB erase sector, entirely inside the empty slot. Verify its readback before updating one inactive `otadata` sector at `0x10D000` or `0x10E000`. Compute its sequence/state/CRC from the actual backup using ESP-IDF conventions; preserve the other selection sector. Do not use IDF's blank initial otadata or its generic factory flash target.

This is coexistence of bootable firmware images, not concurrent applications or an Android-style resident runtime. Only the selected app runs. AMPVE and Wi-Fi components can modify shared NVS after boot; preserving its installation bytes is not a promise to preserve its later state. The recovery plan includes original NVS and both otadata sectors as well as the touched OTA app sectors. Reverting NVS discards new Wi-Fi/AMPVE identity/settings.

## Browser implementation and reuse

Use pinned `esptool-js` 0.6.1 for ROM detection, RAM stub, serial transport and the flash writer. ESP Web Tools 10.4.0 is the reference for installer manifests and its maintained writer integration. A standard app-only reference manifest is generated for tooling; it is **not a complete first-install manifest**.

A narrow AMPVE wrapper is necessary: the generic ESP Web Tools dialog selects by chip family and reconnects independently of AMPVE's audit. It cannot enforce our exact revision/table/bootloader checks on the held connection or read back the application before changing dynamically generated otadata. Do not expose that generic install button. The wrapper retains ESP Web Tools' `keep` flash parameters, compressed per-file writes and `eraseAll: false` through the same pinned esptool-js implementation. No new firmware transport is introduced.

The pinned JS reader omits the final stub MD5 frame and repeatedly copies accumulated data. AMPVE's bounded read adapter follows Espressif's existing `READ_FLASH` command/framing and Python esptool 5.4.0 behavior: 4 KiB packets, acknowledgements, terminal MD5, 64 KiB bounded transfer buffers. `hash-wasm` 4.12.0 supplies MD5/SHA-256; pako 2.2.0 supplies the existing CRC32 implementation. Preserve dependency licenses. MD5 is a transfer/table integrity check, not publisher authentication.

Backups use File System Access on desktop Chrome/Edge, two full reads in separate connections, streamed local writes, and rehashing of both completed saved files. Progress includes measured bytes/rate/phase ETA; cancellation and disk failure cannot produce a completed audit. A 850.6-second owner-observed read informs expectations, not a guaranteed browser duration. Importing existing files rechecks bytes locally and labels the independent-capture claim as owner-supplied evidence. Reloading requires reselecting files; no backup/credential is stored in browser storage or sent to Django. A final full physical comparison is required before writing and can take another full-read duration.

## Publisher and owner gates

Authenticated Django endpoints serve only curated app/review files. A candidate always remains `installable: false`, even if someone edits its review manifest flag. Installation requires an Ed25519-signed release policy whose public key is independently configured outside the release directory. Both server and browser verify the signature; the browser additionally checks expiry, exact profile, artifact digest, bootloader/table fingerprints and documented compatibility/recovery references. No production signing key or approved release was created in this milestone.

The owner must separately save and rehash recovery files, confirm a separate private backup copy and ROM recovery access, then approve the displayed exact write regions. Keep the same serial connection from final full-flash comparison through writes/readback. Write the app first, verify it, then update and verify boot selection. After writes begin, cancellation is disabled; errors never trigger a generic erase or automatic restore. A successful write means written/read-back bytes, not successful startup, Wi-Fi or enrollment.

## Recovery and remaining limits

Stock bootloader forward compatibility is supported in principle by ESP-IDF; exact deployed bootloader testing still matters. Automatic rollback depends on that bootloader's configuration and a valid prior OTA image. Keeping a factory partition does not make it an OTA rollback target. Do not replace the bootloader just to claim rollback support, and do not claim a tested restore from valid backup hashes alone.

The C6 ESP-Hosted firmware is not contained in the P4 flash backup. Host component 2.12.13 remains pinned; its compatibility needs review. Espressif’s [ESP-Hosted troubleshooting guide](https://github.com/espressif/esp-hosted-mcu/blob/main/docs/troubleshooting.md#3-make-sure-hosted-code-is-in-sync-for-master-and-slave) recommends keeping host and coprocessor versions aligned and warns that different versions can be incompatible. A working stock Wi-Fi connection does not establish compatibility with our pinned host. No C6 flashing is included. Native UI/peripheral initialization, network provisioning, startup and recovery require owner-local physical tests after approved first installation. On-device voice and Wi-Fi OTA remain separate workstreams.

References reviewed: [ESP-IDF v6.1 bootloader compatibility](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32p4/api-guides/bootloader.html), [ESP-IDF OTA](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32p4/api-reference/system/ota.html), [ESP Web Tools](https://esphome.github.io/esp-web-tools/), [Espressif esptool-js](https://github.com/espressif/esptool-js). Exact installed library/ESP-IDF source was also inspected for the operations above.
