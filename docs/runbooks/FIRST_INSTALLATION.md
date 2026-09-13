# First Waveshare 7B installation handoff

Date: 2026-09-13. Target: the owner's Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, P4 revision 1.3, 32 MiB flash. **Preparation is not installation approval.** The device and its backups are on the owner's PC, not this VPS.

## What is complete

The browser implements audit, two private backups/import, shareable review metadata, signed-release checks, an app-first writer and recovery preparation. The native development candidate includes the local shell, protected Wi-Fi setup/Improv, pairing, management and OTA candidate code. Compilation and software fixtures do not validate physical startup, Wi-Fi, audio or rollback.

The platform, audio gateway and existing HTTPS/WSS tunnel run under PM2 with boot restoration. See [PLATFORM.md](PLATFORM.md). The owner reports successful frontend use and two `.bin` files plus a JSON on his PC. File presence alone does not establish which JSON was saved, matching hashes or a separate-storage copy.

## Owner-local evidence needed next

1. In **Continue with existing backups**, select the two complete backups and their `audit-private.json`; download **Download shareable review summary**. Inspect and share only `ampve-review-summary.json`. Keep `.bin` files, original capture records, raw serial logs and private recovery files local.
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

Exact candidate hashes and download verification will be recorded after packaging. No approval JSON with placeholder review evidence, signed release or active publication is created during this preparation. Follow [FIRMWARE_RELEASES.md](FIRMWARE_RELEASES.md) only after the exact bootloader/C6/recovery review passes, then present the exact local writes for owner approval.

## First physical acceptance

After the approved bounded writes, confirm actual startup, display/touch, offline navigation, bounded Wi-Fi setup/reconnect, pairing, authenticated online status and name/volume acknowledgement. Record failures in #12 and the corresponding lifecycle issue. Board voice, microphone capture, camera and physical OTA/rollback are separate milestones. A web response, downloaded file or heartbeat alone is not a passing hardware acceptance test.

Task status is tracked in #6: completed software tasks can close, while exact-unit review #7/#10, physical installation #12 and later hardware acceptance remain open.
