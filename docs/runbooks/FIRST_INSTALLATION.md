# First Waveshare 7B installation handoff

## Idle-task allocation failure — 2026-09-13

The owner's expanded 0.1.12 report matches ELF `c441d686a` and identifies `vApplicationGetIdleTaskMemory`, `port_common.c:53`. The exact pinned SDK asserts a non-null idle task control block there; its allocator requires internal 8-bit memory. This is before `app_main`, so Wi-Fi, dashboard pairing and AMPVE peripheral initialization have not run. The report does not measure the remaining heap or prove which earlier allocation exhausted it.

The 0.1.13 candidate reduces the early main-task stack by 12 KiB (16 to 4 KiB) and starts AMPVE on its original 16 KiB budget after the SDK normally reclaims startup RAM. It retains core affinity, main-task priority, allocator behavior and assertions. Two bounded numeric heap checkpoints support automatic diagnosis. See NATIVE_FIRMWARE.md and USB_COMMISSIONING_REVIEW.md for allocation order, source review and the known 0.1.12 replacement route. Software validation: actual entry-point host fixtures under ASan/UBSan, 44 firmware-tool tests, 69 browser tests and rendered Chromium onboarding. Physical startup and subsequent setup remain unverified; binary identity and publication evidence are recorded after compilation below.


## Startup failure continuation — 2026-09-13

The owner's 0.1.12 report identifies ELF prefix `c441d686a` and an assertion. Resolving PC `0x4ff0de92` against the retained exact ELF gives `panic_abort` in `panic.c:509`, which does not identify the assertion's caller. No firmware correction is justified by this address alone. The published firmware remains unchanged.

The browser now retains installed identity, checked backup files and prepared recovery in the current tab after a startup-check failure. It keeps the existing USB restart/check control visible, pauses installation of the candidate associated with a captured panic, and disables Wi-Fi connection until startup succeeds. A successful authenticated runtime status clears the pause; a different signed candidate can be prepared through the existing release check. The installation handler enforces the pause as well as the button. Opening repair no longer discards the session's evidence, and an unbound startup check uses the current release rather than assuming the old recovery release is installed.

Startup summaries add at most four assertion source locations (function identifier, source basename and line number); absolute paths and assertion expressions are discarded. This enables one USB restart/check without a flash read, backup import or reinstall. The original recovery route retains all its existing checks and explicit consent. Session evidence is not persisted across reloads; private files remain local. Validation covers 67 Node tests and rendered Chromium fixtures, including repeated startup checks after a panic, visible result downloads, blocked same-candidate installation and redacted assertion locations. An existing diagnostic-wrapper regression found by the suite was corrected: validation failures no longer access the reader merely to collect transfer diagnostics. Neither this UI change nor an assertion report establishes successful physical startup, recovery, Wi-Fi or pairing.


## Buffered serial receiver — 2026-09-13

The next owner attempt stopped with `flash_packet_incomplete` after 1,495,040 bytes; the failing 64 KiB read began at 1,441,792 and had accepted 53,248 bytes. No write was attempted. The report did not record the unexpected packet's actual length, so it cannot establish whether the cause was an empty SLIP frame, dropped bytes, corruption or another transport problem.

Local inspection of pinned esptool-js 0.6.1 found that `Transport.read()` reallocates/copies the accumulated decoded frame for each byte and the inherited receive loop silently continues after Web Serial overrun/framing errors. A measured 4,096-byte decode made 4,096 append calls and copied 8,390,656 accumulated bytes. This is concrete implementation overhead, not proof of the physical failure's cause.

The audit/install reader now uses a small `BufferedTransport` subclass while retaining the pinned loader, framing writer and reset strategies. It explicitly configures a 64 KiB Web Serial buffer at both initial connection and baud changes ([Chrome's bufferSize documentation](https://developer.chrome.com/docs/capabilities/serial)). It holds one stream reader until close/error, bounds pending input to 256 KiB, and decodes SLIP linearly into an 8 KiB maximum packet buffer. Split escape sequences, multiple frames and empty delimiter runs are handled without per-byte append allocations. Non-empty short flash packets still fail; no data is stitched across invalid frame boundaries. Timeouts and malformed framing remain fatal to the operation, with no raw serial contents in errors.

Overrun/framing/parity/disconnection errors now terminate the receiver with fixed diagnostic codes instead of silently continuing after lost bytes. `packet_bytes` records the actual decoded packet length when available; `transport_revision: buffered-slip-v1` identifies the active receiver in subsequent results. Existing complete-transaction MD5 retries and all image/protected-region/readback checks remain unchanged. Baud rate, firmware and write regions are unchanged.

Validation: 66 Node tests, including a 32 MiB framed decoder workload, split escapes, malformed/oversized frames, partial-frame timeout, one-reader lifecycle across reconnects, overrun/queue limits, and the actual buffered receiver feeding fragmented data through `readChunk` with all acknowledgements and terminal MD5. Rendered Chromium onboarding remains covered. The new decoder makes zero per-byte append calls in the measured 4 KiB case. Physical USB stability/startup and real elapsed time remain unverified.

## Bounded USB transfer retries — 2026-09-13

The owner clarified the stopped preflight message: `Flash transfer MD5 mismatch`. The report recorded 20,512,768 received bytes and 533,247 ms with `write_attempted=false`; this was a transfer-integrity failure before any flash write, not evidence of a user cancellation or a protected-region mismatch. The earlier report did not distinguish a malformed terminal digest from an actual digest disagreement. The physical reason for the USB transfer error is not established.

`readChunk` now retries a block only after consuming all expected data, sending all acknowledgements and receiving the complete 16-byte terminal digest. A digest disagreement allows at most three attempts for that block and eight extra read attempts across the current connection. Hashing/comparison receives only a successful block, so a transient error does not discard preceding validated blocks or restart the full preflight. Packet/digest truncation, timeouts, disconnects and unknown command boundaries stop rather than issuing another potentially desynchronized command. Cancellation remains honored before a retry. This is read-only retry; no flash write is retried automatically.

The installation result records a fixed read-failure code, block offset/size, attempt, received bytes and read stage, plus the connection retry count. Raw bytes, digests and transport exception text are excluded. The existing stopped attempt cannot resume retrospectively after its reader/state has been discarded; the optimization applies within a new attempt.

Validation: 60 Node tests cover transient/persistent corruption, malformed packets, the per-block and connection limits, cancellation, continuation at the same mid-preflight block and zero writes after exhaustion. Rendered Chromium onboarding remains covered. Real USB reliability and physical installation/startup remain pending; firmware stays 0.1.12.

## Single-pass installation and retained results — 2026-09-13

The owner reported more than one hour spent on repeated comparisons, followed by a generic possible-write warning. The supplied JSON is an imported-backup review, not installation evidence; clicking its download had replaced the actual operation error. The previous failure phase cannot be reconstructed from that report.

Preparation now performs local file checks only. At installation time one full 32 MiB read on the same stopped ROM/stub connection simultaneously checks protected bytes, the original stock selection and the known padded app identity. It replaces the preparation-time scan, separate known-app reread and second complete pre-write scan. Publisher approval is still rechecked after that scan, and app/selection readbacks remain mandatory before reset. There is no reusable preflight flag or unchecked write path: the validator belongs to the in-memory prepared plan and executes on every installation attempt. Software tests count exactly one flash-length preflight plus the two write-region readbacks. Real USB duration is not yet measured.

The operation exports `ampve-installation-result.json` with bounded phase, preflight byte count, elapsed time, whether a write was attempted, separate app/selection verification and reset completion. Raw exceptions, serial output and private data are excluded. If post-write startup fails, the same visible result link exposes the bounded startup-failure summary instead of leaving that diagnostic inside the hidden Wi-Fi section. A reset failure after both successful readbacks is distinguished from an incomplete write. Downloading backup/plan/result evidence never overwrites the visible operation message. The existing backup summary still describes the original files only.

Validation: 56 Node tests, including byte-count enforcement and write/reset failure injection, and rendered Chromium onboarding at three widths, including preservation of the operation message after downloading a backup summary. Physical installation, the previous failure's cause and measured on-device duration remain unverified. Firmware artifacts remain unchanged.

## Direct USB reinstallation — 2026-09-13

The owner reports that the previous recovery screen kept offering startup checks for 0.1.11. **Repair or reinstall AMPVE** now enters the same installation flow and always selects the current signed release (0.1.12). A failed USB startup exposes original-backup import instead of another mandatory startup attempt. The existing **Install AMPVE** action requests the USB port when needed; no additional installation-method button is added.

The browser derives both current and previous signed application plans from the original verified backup. It saves recovery for the larger of the two sector-rounded app spans. On the same security-checked ROM connection it compares the whole flash, allows differences only inside that app span, NVS and otadata, requires the entire installed padded image to match either known signed app, and checks that the untouched original stock boot-record sector is unchanged. Untouched original flash is also accepted. Unknown/partial images or other changed regions stop before writing and retain explicit original restoration as a fallback.

It then repeats a full current-flash hash comparison and revalidates both signed references before the first write. Only the new app (padding the previous longer tail with erased bytes) and the original plan's AMPVE boot-selection sector are written and read back. NVS/settings are preserved, stock software never needs to run between attempts, and reset happens only after both readbacks. A runtime handshake is not a prerequisite for ROM installation. Power-loss recovery and corrected physical startup remain unvalidated; this does not broaden support beyond the validated-profile workstream.

Validation: 54 Node tests cover recognized previous/latest images, untouched originals, longer-tail clearing, NVS preservation, write/reset order, unknown apps, protected regions, stock selection changes, cancellation, revocation and failed app readback. Rendered Chromium fixtures cover signed current/previous release selection, enabled installation after saved recovery/consent without a previously selected port, cancellation, fallback restoration and three widths. These are software fixtures, not hardware acceptance. Firmware and signed artifacts are unchanged from PR #72.

## Corrected USB-assisted release — 2026-09-13

The owner summary identifies `sleep_clock_icg_startup_init` failing with `0x101` before `app_main` in 0.1.11, with its exact ELF prefix. No repeated diagnostic of that image is needed. Version **0.1.12-startup-fix-dev** disables the optional sleep-clock REGDMA initialization; see [the engineering review](USB_COMMISSIONING_REVIEW.md#startup-retention-correction--2026-09-13). The final ELF contains 26 system initializer functions and no failing `sleep_clock_icg_startup_init` symbol. This removes the observed failing path; physical startup and subsequent phases remain unvalidated.

- Firmware source: `19a2166b9b0c5c6291fc4f4517cb166b096aa89d`, native build sequence 2.
- Candidate: `/home/ampve/.local/state/ampve/firmware-usb-startup-fix-review-02`.
- Signed initial-install release: `/home/ampve/.local/state/ampve/firmware-usb-initial-release-02`; ID `30fe152db1a099a4d5bc5e0fd586e25d41d292638272c289adc4c76cc61310e1`, expires `2026-09-27T17:38:33Z`. Signature/provenance verification passed against the existing public registry; this is not an OTA release.
- Application: 2,875,904 bytes, SHA-256 `bc334f7d5c744d693f0de9034aaaea26de0694dfc94aed90fcf8087eba466406`; rounded span `0x2BF000` at `0xE00000`.
- ELF SHA-256: `c441d686acd999fa8c8b5aa8a48acdb4ad451ece33ff3bf37ee673710e81c77a`; retained privately under `firmware-debug/<app-sha>/xiaozhi.elf`. Browser symbol catalogs retain both versions and require matching app/ELF identities.
- Review archive: 1,883,817 bytes, SHA-256 `28526c0d416a12207a15b045bd95a18f4a07c561f4d81fe118a06e0a238522a6`.
- Four packaged artifacts are byte-identical between two separately executed builds on the same VPS/toolchain/cache. Logs: `startup-fix-build-a.log` and `startup-fix-build-b.log` in the external firmware cache. Both generated configs disable the option; the pinned CMake excludes its source. This is not cross-machine reproduction.
- Validation: 44 firmware-tool tests, 51 Node tests, 9 Django firmware/diagnostic tests and rendered Chromium onboarding fixtures at three widths. Recovery delivery tests cover a smaller current app, the previous full span, authentication, invalid selectors and missing/invalid release data.

The private platform configuration should select this new release for installation and retain `firmware-usb-initial-release-01` as `firmware_recovery_root`. Recovery mode uses the prior signed release through `?recovery=1`, preserving its exact `0x2C0000` span instead of shrinking to the new binary. Publication does not change any device. Keep the existing trust floor at 1 while the prior recovery policy remains applicable; revocation and expiry still apply.

Owner route: reload onboarding, choose **Repair or reinstall AMPVE**, confirm the board and select the original two `.bin` files plus capture record. Save the prepared return-to-original files, confirm the existing installation consent and choose **Install AMPVE**. The browser requests USB TO UART if needed and checks whether the connected flash is untouched stock or a recognized AMPVE image before writing the current release. A failed old-runtime diagnostic is not required. **Restore original software** remains an explicit fallback for states that cannot be reinstalled safely. Corrected AMPVE USB startup, Wi-Fi, pairing, peripherals and physical recovery remain acceptance tasks.

## USB-assisted commissioning update — 2026-09-13

[ADR 0005](../decisions/0005-usb-assisted-commissioning.md) supersedes the mandatory pre-install C6 check **only for an explicitly signed USB-assisted initial-install release**. The platform prepares the same exact stock-preserving write/recovery plan, then checks the installed core over USB before network provisioning. A failed C6 version query remains a diagnostic finding, not proof of incompatibility or a mandatory gate for this mode. Core confirmation, Wi-Fi initialization, actual network operation, pairing and physical recovery are separate evidence. The browser now exposes explicit original-backup restoration with fresh full-flash comparison; it is not yet physically validated. Other releases retain their existing gates.

## Previous USB-assisted development release (recovery reference)

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

## Matched initializer-dispatch abort

The owner supplied a bounded 8,997-byte capture with ELF prefix `6ea09dd6d`, abort PC `0x480019e9` and MEPC `0x4ff0de92`. The prefix matches the archived/published AMPVE ELF. Using the pinned toolchain's `addr2line -pfiaC -e <matching-elf>` resolves these to `do_system_init_fn` at `esp_system/startup.c:135` and `panic_abort` at `esp_system/panic.c:509`. This locates the abort before `app_main`, but identifies the dispatcher, not the failed initializer. Allocation failure remains observed; a PSRAM-specific cause is not established.

The exact pinned dispatcher logs `init function %p has failed (0x%x), aborting` immediately before abort. The browser now captures this bounded address/error pair separately as `startup_initializer_failures` (at most four entries). It does not export the raw line. `startup-symbols.json` contains the 27 initializer function pointers extracted from `esp_sys_init_fn_*` ELF symbols: each 8-byte entry contains a little-endian 32-bit function pointer followed by 16-bit core/stage fields. The extraction checked the ELF SHA against the published app descriptor before writing the sorted JSON. Symbol names are attached only when both the expected full app SHA and exactly one sufficiently long observed ELF prefix match the index. Unknown/mixed images retain addresses without guessed labels. These labels never authorize writes or replace runtime confirmation.

The next capture is needed to identify the actual failed initializer and its returned error. The firmware binary and release policy remain unchanged; no hardware write has been performed from the VPS.
