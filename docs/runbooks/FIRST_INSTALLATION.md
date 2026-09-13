# First Waveshare 7B installation handoff

Date: 2026-09-13. Target: the owner's Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, P4 revision 1.3, 32 MiB flash. **Preparation is not installation approval.** The device and its backups are on the owner's PC, not this VPS.

## What is complete

The browser implements audit, two private backups/import, shareable review metadata, signed-release checks, an app-first writer and recovery preparation. The native development candidate includes the local shell, protected Wi-Fi setup/Improv, pairing, management and OTA candidate code. Compilation and software fixtures do not validate physical startup, Wi-Fi, audio or rollback.

The platform, audio gateway and existing HTTPS/WSS tunnel run under PM2 with boot restoration. See [PLATFORM.md](PLATFORM.md). The owner reports successful frontend use and two `.bin` files plus a JSON on his PC. The owner subsequently supplied the browser shareable summary; its imported-backup metadata is reviewed below. Separate-storage confirmation remains pending.

## Owner-local evidence needed next

1. **Received:** the owner supplied `ampve-review-summary.json` from a verified import. Do not request this same summary again. Keep `.bin` files, original capture records, raw serial logs and private recovery files local. The next local output is the exact candidate comparison/recovery plan described in step 3.
2. Confirm a verified backup copy on separate storage and the board's programming-port/ROM access. The earlier successful stock boot after RESET is recorded; it is not a restoration test.
3. Download the selected current review ZIP after its identity is recorded below. Use the pinned local tools described in [BROWSER_INSTALLATION.md](BROWSER_INSTALLATION.md) to compare the exact candidate and generate a new private installation/recovery plan. Existing backups must remain byte-identical to the current unit at final preflight; a normal stock boot can change NVS/otadata and require fresh capture.
4. Review the exact stock bootloader's image/selection behavior and identify the C6 firmware against the pinned ESP-Hosted host. P4 flash metadata cannot establish the C6 firmware identity. A generated AMPVE bootloader is comparison material and is never substituted for the stock bootloader.

## Proposed writes and recovery

| Region | Proposed action | Evidence still required |
| --- | --- | --- |
| Empty stock `ota_1`, base `0xE00000`, capacity `0x3F0000` | Write the exact reviewed application, then read it back and verify its SHA-256 | Current backup proves the whole slot is empty; exact candidate size/hash and sector rounding |
| One 4 KiB sector at `0x10D000` or `0x10E000` | Write locally generated boot selection only after application verification | Actual original selection determines which sector and its exact bytes/hash |
| Stock bootloader/table/factory/`ota_0`, original data and shared assets | Preserve during installation | Full current-unit comparison and reviewed intervals |

The local planner extracts original bytes for the sectors touched by installation, plus original NVS (`0x3B000`, `0xD2000` bytes) and both otadata sectors (`0x10D000`, `0x2000` bytes) for reviewed recovery after runtime changes. Returning to stock may require restoring boot selection and changed NVS. Recovery is a separately reviewed write; automatic stock-bootloader rollback remains unproven. Do not use generic full-chip erase, upstream `idf.py flash`, or write generated bootloader/table/blank otadata files.

## Candidate and publication preparation

The earlier `0.1.10-improv-dev` reproduced artifact used testing trust and cannot be promoted. A real development signing key was generated privately under `/home/ampve/.config/ampve/publisher-development-01`; its public key was independently derived from the private key and compared. Public build trust uses sequence 1 and `testing_only=false`. The prepared registry is not the active platform registry. The private key must have a protected separate backup before operational publication; never put it in a review ZIP, browser or Git.

Builds use the same pinned source, IDF and dependencies in two separate previously compiled source/build directories, with newly compiled integration/trust objects. Retain `first-install-build-a.log` and `first-install-build-b.log` in the private external firmware cache. This is incremental reproduction on one VPS with shared toolchain/cache, not two new clean builds or cross-machine evidence. The previous clean baseline is documented in [FIRMWARE_REPRODUCIBILITY.md](FIRMWARE_REPRODUCIBILITY.md).

Prepared review: `/home/ampve/.local/state/ampve/firmware-first-install-review-02`, source `4dd730cc33fb50fec88f49d2f2479535eea17f55`, version `0.1.10-improv-dev`, sequence 1, `testing_only=false`, `installable=false`. Both builds finished successfully and all four packaged artifacts matched. The first packaging attempt lacked the external IDF-tools environment path and left an unselected incomplete `review-01` directory; the successful fresh `review-02` used the recorded toolchain environment.

- Application: **2,877,344 bytes**, SHA-256 `b142b31b9c16ff200e7fd24ca392b711616db63042cfd09751d35399c0569b49`.
- Review ZIP: **1,883,537 bytes**, SHA-256 `1b66c254dc4f4c5d79c7af0b368850f6776acd291491f020a928ba443931d2e1`.
- The platform now selects this unsigned review bundle. The prior private platform configuration is retained locally. Authenticated app/ZIP downloads are checked against these hashes; anonymous access and installation remain blocked.
- Validation: 43 firmware-tool tests, 28 Node tests and 28 Django firmware/deployment tests passed. The production configuration check passed. No physical board operation or provider request was performed. No approval JSON with placeholder review evidence, signed release or active publication is created during this preparation. Follow [FIRMWARE_RELEASES.md](FIRMWARE_RELEASES.md) only after the exact bootloader/C6/recovery review passes, then present the exact local writes for owner approval.

## First physical acceptance

After the approved bounded writes, confirm actual startup, display/touch, offline navigation, bounded Wi-Fi setup/reconnect, pairing, authenticated online status and name/volume acknowledgement. Record failures in #12 and the corresponding lifecycle issue. Board voice, microphone capture, camera and physical OTA/rollback are separate milestones. A web response, downloaded file or heartbeat alone is not a passing hardware acceptance test.

Task status is tracked in #6: completed software tasks can close, while exact-unit review #7/#10, physical installation #12 and later hardware acceptance remain open.

## Received owner summary — 2026-09-13

Source: owner-pasted `ampve-browser-review-summary`, schema 1, `imported-capture-record`. It reports two matching rehashed 33,554,432-byte backup files and an independent capture record. It explicitly reports `current_physical_state_verified=false` and `installable=false`. This is owner-provided metadata, not a VPS read of the backups or device.

- Backup SHA-256: `da6a7276ef6198f1e83089acd94362f5b3a6d64246a0df35ba94bbaf8393d3a3`, matching the earlier owner audit fingerprint recorded in #7.
- Table sector SHA-256: `11f4ad270441f47870b3f2202b6f65730682ee1bdc6406aaf726a7a540b8939b`; table offset `0x8000`, MD5 verified by the browser.
- Stock bootloader region SHA-256: `4292a0266be4741a53d224ececf62c1e2ca95d09b9e92081e2f3e78f9c5cd051`; offset `0x2000`, image size 24,160 bytes. The bootloader, factory and ota_0 report P4 chip ID 18, revision fields 1–199, valid internal checksums and appended digests. These checks do not establish the stock bootloader's source/configuration or rollback behavior.
- All nine reported type/subtype/offset/size/flags tuples were compared with the actual selected candidate manifest and match exactly. The owner summary reports ota_1 fully erased. Rehashing the server-side candidate confirms the app identity recorded above.
- The app fits the 4,128,768-byte slot with 1,251,424 bytes spare. Its sector-rounded proposed span is 2,879,488 bytes (`0x2BF000`), from `0xE00000` to `0x10BF000` exclusive. This arithmetic does not authorize writes.

The browser summary intentionally omits current otadata records and stock application descriptor strings; it cannot determine which boot-selection sector to change or identify the C6 firmware. Generate the local `review-summary.json` and private recovery files against the exact selected ZIP; retain sensitive descriptor/log data locally. The engineering review still needs stock firmware provenance/boot behavior and C6 identity, separate-storage confirmation, and the final current-unit comparison. No hardware task closes solely from this imported summary.
