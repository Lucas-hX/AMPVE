# First Waveshare 7B installation handoff

## USB-assisted commissioning update — 2026-09-13

[ADR 0005](../decisions/0005-usb-assisted-commissioning.md) supersedes the mandatory pre-install C6 check **only for an explicitly signed USB-assisted initial-install release**. The platform prepares the same exact stock-preserving write/recovery plan, then checks the installed core over USB before network provisioning. A failed C6 version query remains a diagnostic finding, not proof of incompatibility or a mandatory gate for this mode. Core confirmation, Wi-Fi initialization, actual network operation, pairing and physical recovery are separate evidence. The browser now exposes explicit original-backup restoration with fresh full-flash comparison; it is not yet physically validated. Other releases retain their existing gates.

## Prepared USB-assisted development release

Source `ffa9eb782e7f5998410473c16e4cff02c09c5e3a`, version `0.1.11-usb-setup-dev`, sequence 1. [Engineering review](USB_COMMISSIONING_REVIEW.md) permits the bounded first-install trial with C6/network/peripheral acceptance deferred; it does not claim physical success. Exact local current-unit comparison and browser install consent remain mandatory.

- Candidate: `/home/ampve/.local/state/ampve/firmware-usb-commissioning-review-01`.
- Signed release: `/home/ampve/.local/state/ampve/firmware-usb-initial-release-01`; ID `53a37434e30b88b7d14da9cd3762e0082a93b7ebc84bbaa1898cee72181265c9`, initial-install only, expires `2026-09-27T15:51:59Z`.
- Application: 2,879,840 bytes, SHA-256 `9431969a70d060db94f92a11873ce5200d597a6df199ceeed90c80de2deae33e`.
- Review ZIP: 1,885,673 bytes, SHA-256 `e795b7e36f0c16f0703bfe634dea6a3a3ffa96829453ae0440b7d51ae311075e`.
- Sector-rounded app span: `0x2C0000` bytes, `[0xE00000, 0x10C0000)`. The selected inactive otadata sector is still computed from the actual original backup; it cannot be selected from the sanitized summary alone.
- Four packaged artifacts matched across `xiaozhi-ota` and `xiaozhi-improv-clean`; each compiled in its own CMake workspace on the same VPS/toolchain/cache. Logs: `usb-commissioning-final.log` and `usb-commissioning-comparison.log` in the external firmware cache. This is not cross-machine reproduction.
- Validation passed: 44 firmware-tool Python tests, 42 Node tests, 8 Django firmware/diagnostic tests, 22 compiled Improv/USB scenarios with ASan/UBSan, and Chromium rendered onboarding fixtures at three widths. Publication verification passed against the separately prepared public registry.

The paragraphs below retain earlier candidate/diagnostic history; their unsigned-release state is superseded by this signed USB-assisted trial. No physical write was performed from the VPS. Keep native startup, original startup after restoration, real Wi-Fi/pairing and OTA acceptance open.


Date: 2026-09-13. Target: the owner's Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, P4 revision 1.3, 32 MiB flash. **Preparation is not installation approval.** The device and its backups are on the owner's PC, not this VPS.

## What is complete

The browser implements audit, two private backups/import, shareable review metadata, signed-release checks, an app-first writer and recovery preparation. The native development candidate includes the local shell, protected Wi-Fi setup/Improv, pairing, management and OTA candidate code. Compilation and software fixtures do not validate physical startup, Wi-Fi, audio or rollback.

The platform, audio gateway and existing HTTPS/WSS tunnel run under PM2 with boot restoration. See [PLATFORM.md](PLATFORM.md). The owner reports successful frontend use and two `.bin` files plus a JSON on his PC. The owner subsequently supplied the browser shareable summary; its imported-backup metadata is reviewed below. The owner also confirms a backup copy on another disk. This is owner-provided confirmation, not a VPS inspection of that disk.

## Owner-local evidence needed next

1. **Received:** the owner supplied `ampve-review-summary.json` from a verified import. Do not request this same summary again. Keep `.bin` files, original capture records, raw serial logs and private recovery files local. The next local output is the exact candidate comparison/recovery plan described in step 3.
2. **Received:** the owner confirms the separate-disk backup copy. Recheck the board's programming-port/ROM access at final installation. The earlier successful stock boot after RESET is recorded; it is not a restoration test.
3. Click **Check available installation** in the browser. It downloads and checks the selected application, compares the imported backup fingerprints and derives exact app/boot-selection regions. Click **Save return-to-original files**. During this initial engineering review only, optional **Technical details and support** provides **Download installation support summary** (`ampve-plan-review-summary.json`). Ordinary onboarding does not require JSON sharing. No local terminal or Python is required. An unsigned plan cannot install; after approval, prepare again against the signed release. Existing backups must remain byte-identical to the current unit at final preflight; a normal stock boot can change NVS/otadata and require fresh capture.
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

The browser summary intentionally omits current otadata records and stock application descriptor strings; it cannot determine which boot-selection sector to change or identify the C6 firmware. Generate the local `review-summary.json` and private recovery files against the exact selected ZIP; retain sensitive descriptor/log data locally. The engineering review still needs stock firmware provenance/boot behavior and C6 identity, plus the final current-unit comparison. Separate storage is now owner-confirmed. No hardware task closes solely from this imported summary.

## Automatic vendor-base recognition — 2026-09-13

The official [Waveshare factory artifact](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-7B/blob/9fcd49a8c927a00f5583c22d568b3448addbe51c/firmware/ESP32-P4-WIFI6-Touch-LCD-7B-FactoryOnly.bin) was downloaded outside Git at pinned vendor commit `9fcd49a8c927a00f5583c22d568b3448addbe51c`. It is 33,488,896 bytes with SHA-256 `3a60bb19b90f04914ac1173d9a63df19eeb3626662c72d7d631028aded00c6df`, matching the vendor README. Its bootloader region and table sector hashes exactly match the owner's reported `4292a026…` and `11f4ad27…` fingerprints above. All nine partition entries match. This removes unknown provenance for those exact regions without requesting additional owner data.

`firmware/profiles/stock-baselines.json` records this source and exact regions. `firmware/tools/verify_stock_source.py` rechecks the downloaded public artifact and bounded regions offline. Browser recognition requires matching locally verified backups, table checks and a valid matching bootloader image. Recognition grants no install permission and rejects changed fingerprints/layout. No private dump or vendor binary is committed.

The public bootloader contains version string `v5.5.1-875-g64726df15e-dirty`; the supplied app descriptors identify factory Brookesia and XiaoZhi 2.1.0. These strings do not reproduce the bootloader build or verify rollback behavior. The [vendor source notes](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-7B/blob/9fcd49a8c927a00f5583c22d568b3448addbe51c/firmware/README.md) explicitly separate the immutable binary from maintained source and warn that host/C6 matching and runtime validation are separate from compilation. The maintained Brookesia manifest uses ESP-Hosted 1.4.*, whereas AMPVE pins 2.12.13; this is not proof of the actual C6 version or of incompatibility, but it cannot establish compatibility either.

Remaining engineering work belongs to AMPVE: establish a bounded way to identify/check the installed C6 before enabling the release and establish exact stock boot-selection/recovery behavior. The P4 ROM connection and known P4 flash hashes alone cannot observe C6 flash. Generic ESP32 discovery cannot select arbitrary board pin/peripheral firmware. Add independently tested profiles/releases; do not treat a successful chip probe or public vendor fingerprint as universal installation approval.

The automated 7B diagnostic and recovery comparison are now documented in [C6_DIAGNOSTIC_RECOVERY.md](C6_DIAGNOSTIC_RECOVERY.md). Candidate preparation runs automatically after backup verification; its button is a retry. C6 version observation, actual Wi-Fi operation, return from RAM diagnostics and physical restoration are separate evidence. No signed installation approval follows from the read-only checks alone.

## USB-assisted deployment verification

PR #67 merged as `f258acd79ec4582fd4f6e71fb73f95a484db67bf`. The private platform configuration now selects the signed `firmware-usb-initial-release-01` and the independently prepared development trust registry; its previous configuration was retained privately before the atomic update. Only `ampve-platform` was restarted after static collection. Platform, audio and tunnel remained online under PM2.

Live authenticated Chromium verification on `https://ampve.com` passed: anonymous firmware access redirected to login; the exact signed initial-install policy verified with browser Ed25519; the app returned HTTP 200 and rehashed to the recorded 2,879,840-byte artifact; startup/recovery controls were present without JavaScript errors. Installation was correctly disabled before local board/backup preparation. No physical write or provider request was performed. Django deployment checks reported only the existing optional HSTS subdomain/preload warnings; no related security setting was changed.

The C6 query no longer gates this signed USB mode. First on-board USB confirmation and physical restoration remain pending in #12, and the exact local install consent remains a browser gate in #10/#17.

## First owner attempt: black screen after power cycle

The owner reports that onboarding appeared to finish writing, but the screen remained black after manually switching power off/on, and a new installation was blocked. No exact write result or live USB startup summary has been received yet. Record this as a failed/unconfirmed first startup, not successful native installation or proof of a display-only fault. The owner sees only the ON/OFF switch on the accessible assembly.

A repeated initial installation must still reject changed flash. Recovery now has a visible entry point, prepares its original-backup plan after file import without requiring an existing serial reader, and requests the USB port when restoration starts. Full-flash comparison and exact original regions are unchanged. A failed/cancelled port selection retains the prepared recovery route. A live comparison showing expected installation changes directs the user to startup diagnostics/restoration instead of another initial write.

Startup checking releases any previous ROM reader, opens its sole application UART reader and requests normal reset through the observed USB-UART bridge. Failed checks expose only bounded fixed boot-observation categories, byte count, timeout/open state and the last nonce-validated runtime status; raw UART text and private identifiers are discarded. These categories are observations, not a verified root cause. Firmware bytes and signing policy are unchanged pending actual device evidence.

[Waveshare's hardware diagram](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-7B#hardware-description) distinguishes the ON/OFF switch, USB TO UART port and small RESET/BOOT buttons. Their accessibility must not be assumed for the owner's assembly. Try the programming bridge's automatic reconnection first; do not require disassembly, pin shorting or generic erasure as onboarding advice.

Reset investigation found a concrete software defect: the installed and upstream [esptool-js v0.6.1 HardReset](https://github.com/espressif/esptool-js/blob/v0.6.1/src/reset.ts) only releases RTS; it does not assert EN first. AMPVE now uses that library's supported CustomReset with the fixed sequence `D0|R1|W100|R0|W100|D0` on its 7B USB-UART path. Installation/restoration completion and explicit startup retry use a complete EN pulse with BOOT released. This can explain remaining in the ROM stub, but is not proof of the owner's post-power-cycle root cause.

The explicit startup retry opens its sole reader before pulsing reset, is restricted to the observed CH343 USB ID 1a86:55d3, and retries a read-only status request with one nonce during the observation window. This captures early fixed boot-error categories and tolerates a request sent before the app UART starts. It performs no firmware writes. Tests exercise the actual pinned ESPLoader/CustomReset signal sequence, reader ownership, lost-request retry and sanitized failure output.

## Owner USB panic evidence

The next owner-provided summary reports serial opened, 65,595 received bytes, `memory_initialization` and `panic`, no validated runtime status and no timeout. The 64 KiB processing limit stopped the old capture. This establishes incoming UART data and classified error messages; it does not identify the running image, prove defective PSRAM or establish the exact allocation failure. The generic memory category also matches `Failed to allocate`.

The browser now retains fixed subcategories for PSRAM identification/init, SHA alignment allocation, Hosted allocation, assertions and panic reasons; at most eight instruction PC values from explicit abort/MEPC/ESP_ERROR_CHECK lines; and at most four bounded ELF hash prefixes. The expected app hash is still expected identity, not observed runtime identity. ELF prefixes allow matching a later panic to the archived ELF before interpreting addresses. No stack dump, other register values, raw paths/logs, SSID or credentials are exported.

After detecting the first panic, the reader collects a one-second bounded tail and stops with `capture_stop: panic_captured`. The 64 KiB processing ceiling and 768-character line bound remain enforced. This prevents a repeating startup failure from obscuring the first useful evidence with an output-limit error. The native image remains unchanged until the failing call site/image can be established from the next sanitized capture.

For app `9431969a70d060db94f92a11873ce5200d597a6df199ceeed90c80de2deae33e`, the embedded ELF digest and actual compiled ELF both equal `6ea09dd6dc6966b3882e13ff6fd758edee5c1c9dc7b13ee89e5abfb718f818f6`. A private copy is retained under the external `firmware-debug/<app-sha256>/` directory, separate from immutable signed release files, so a future build cannot destroy the matching symbolication evidence.
