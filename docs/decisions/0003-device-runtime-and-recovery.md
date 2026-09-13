# ADR 0003: A small AMPVE device shell with recoverable firmware

Date: 2026-09-13
Status: Product direction accepted; release/build parameters pending local audit.

## Verified and unresolved facts

Lucas successfully ran the browser inspection and reported ESP32-P4 revision v1.3, USB VID 0x1a86 and PID 0x55d3. This reconfirms the chip revision. USB IDs describe the selected interface, not the exact board, flash capacity or partition map. The target remains Waveshare ESP32-P4-WIFI6-Touch-LCD-7B; its label, flash/security state and original partition layout still require a local audit. Historical observations of 32 MiB flash/PSRAM, GT911, ES7210 and ES8311 are not fresh functional test results.

PR #3 was merged with the owner's authorization. USB detection is user-validated; the embedded runtime, Wi-Fi provisioning, pairing on hardware, codec/audio, display/touch and OTA remain unvalidated.

The pinned XiaoZhi board source already uses WifiBoard, esp_lvgl_port, GT911 touch initialization and BoxAudioCodec. Reuse those integrations; do not add a mobile OS, browser engine or parallel firmware framework. Its touch initialization includes fatal ESP_ERROR_CHECK paths: a robust AMPVE integration needs to review those failure paths rather than assuming a themed upstream image provides graceful recovery.

## Runtime composition

One XiaoZhi-derived ESP-IDF firmware contains the native LVGL shell, board drivers, management task and eventually Companion. The shell stays usable without provider access and without an internet connection. It is not an independently resident agent that survives arbitrary replacement firmware.

- Board adapter: hardware profile, safe bus/peripheral initialization and diagnostics.
- Local UI: Home, Wi-Fi, My device, Settings, Companion states and persistent mute/stop.
- Management task: verified HTTPS, pairing, NVS credential state, heartbeat and revision acknowledgement. It never blocks the UI thread waiting for DNS, TLS or a response.
- Audio task: existing XiaoZhi capture/playback machinery; cloud voice is gated on the AMPVE Opus adapter and explicit session start.
- Lifecycle: reset-reason tracking, bounded recovery mode, compatible updates and confirmed startup.

Use LVGL's established event/task synchronization, existing ESP-IDF tasks/queues and bounded buffers. Record actual resource budgets only after a pinned build and hardware measurements. Disable unvalidated camera features for the first target; never initialize unrelated peripherals merely because an upstream profile enables them.

## Interface specification

Reuse the original AMPVE symbol avatar and Companion icon. English throughout. Warm ivory canvas, graphite text, sage surfaces and orange actions. New imagery is unnecessary for the first shell; optimize existing assets into target-sized LVGL image data when the graphics/toolchain version is pinned. Do not load the original large PNGs into firmware unchanged.

For the 1024 × 600 target: a short optional boot mark, then Home with three large entries: Companion, Wi-Fi and My device. Keep Home, Settings and microphone mute in a predictable bottom bar. Aim for 56–72 pixel minimum touch targets, 18–24 pixel body text and 32–40 pixel titles; verify actual legibility at the owner's viewing distance. Avoid scrolling on Home; detailed diagnostics may scroll. Smaller screens use fewer columns and progressive disclosure, not a scaled-down screenshot.

- Home: symbol/wordmark, a short greeting, the Companion icon and connection state. No boot animation that delays recovery or local controls.
- Wi-Fi: reuse the pinned XiaoZhi local provisioning path first, launched from the device. Show concise instructions and connection/error states. An on-screen network picker/keyboard is a later refinement if upstream provisioning cannot offer it cheaply. Passwords stay local, are masked, never echoed into logs/telemetry, and are cleared from transient widgets. Opening Wi-Fi settings must not immediately erase a working network.
- Pairing: only show a real server-issued code after connectivity; mask/expire it on timeout. No fabricated success offline.
- My device: AMPVE version/source build, chip/revision, measured flash/PSRAM, display profile, capabilities and last test result. Firmware version comes from app metadata, not browser USB IDs.
- Speaker check: explicit local tap, short low-volume tone, then “Did you hear it?” The codec acknowledging I2C/I2S initialization does not prove an attached, audible speaker.
- Microphone check: explicit permission and local level meter only, with no raw-audio retention or network upload. Silence is not automatically a failed microphone; present “inconclusive” rather than claiming failure from one quiet sample.
- Settings: bounded volume, local mute, network setup and advanced diagnostics. No generic shell, destructive reset or OTA action on Home. Local mute wins over server configuration and defaults to muted after boot/recovery.
- Companion: unavailable until real prerequisites pass. Loss of cloud connectivity stops the session predictably and leaves local navigation/mute responsive.

A web interaction concept is implemented at /devices/interface-preview/. Its networks, mute and speaker flows are explicitly simulated; it is not LVGL firmware or physical validation.

## Capability evidence

The server now accepts an optional bounded hardware_report on the authenticated v1 heartbeat. Capabilities are display, touch, speaker, microphone and Wi-Fi. Each reports one of unknown, configured, initialized, passed, failed or unavailable. Unknown is different from absent; configured is different from detected; driver initialization is different from a functional test. All values are client-reported, not independently attested.

The same state model must drive the native About screen and dashboard. Measure chip/flash/PSRAM using the pinned SDK's runtime APIs. Use explicit profile knowledge for fixed board wiring, constrained known-address probes for supported peripherals and functional tests for real operation. Do not scan arbitrary buses or label speakers as detected based only on the chip family. Preserve a report timestamp so old capability results are not implied to be freshly tested.

## Release and recovery gates

1. **Before any write:** confirm the board label, local programming port, stable power, measured flash size, bootloader/partition addresses, security/eFuse read-only state, original app metadata and full backup size/hash. Keep two private copies outside Git. Verify the backup is readable and its partition boundaries are coherent; a file called “backup” is not recovery evidence. No erase, security provisioning or flash-write commands are authorized by this planning step.
2. **Build baseline:** pin XiaoZhi source, exact ESP-IDF/toolchain and resolved component lock; build in an isolated workspace or CI. Do not select ESP-IDF “latest” from the stable docs URL. Compare generated partitions/image sizes against the real audit.
3. **Layout review:** the pinned upstream CSV has ota_0 at 0x200000 and ota_1 at 0x600000, each 4 MiB, plus an assets partition at 0xA00000 of 16 MiB. These are upstream-source facts, NOT approved write offsets for this board. NVS/otadata addresses must be resolved by the chosen build. Do not assume the stock bootloader/partition layout is compatible.
4. **First approved USB installation:** review exact files, offsets, sizes, hashes, preserved regions and a matching restore procedure. The initial replacement may change bootloader/partition layout and does not inherit OTA safety automatically. A verified backup and ROM download access remain the development recovery route.
5. **Recoverable application updates:** deliberately enable app rollback in a compatible bootloader with two app slots and otadata. Update only the inactive app slot; keep bootloader/partition/data migrations out of automatic v0 OTA. Authenticate the publisher with signed release metadata or signed artifacts and enforce exact board/revision/layout compatibility before scheduling.
6. **Startup confirmation:** run bounded local diagnostics before marking a new app valid. Do not require provider, internet or account availability to confirm local startup. Essential display/event-loop/management-state failure must have a deliberate rollback or local recovery path; optional audio/camera failures should be surfaced as degraded capabilities. Show the failure reason, preserve mute and prevent an infinite crash/retry loop.
7. **Independent asset/data safety:** application rollback does not roll back a shared assets or NVS partition. Keep the recovery UI's minimal fonts/mark in the app image; freeze shared assets for initial releases or define a separately atomic/version-compatible scheme. Test NVS configuration migration before changing formats; never erase NVS automatically on every initialization error.
8. **Physical acceptance:** test repeated cold boots, absent Wi-Fi, VPS outage, bad credentials, touch/audio failures, settings acknowledgement/reconnect and revocation. Then test interrupted downloads, bad image rejection, failed-new-app rollback and USB recovery on the development board. No “cannot brick” guarantee is justified before these tests, and zero risk cannot be promised afterwards.

Secure Boot activation, flash encryption provisioning and eFuse anti-rollback remain outside this development MVP. They are distinct from ordinary application rollback and may constrain recovery irreversibly.

## Smallest firmware milestone

A buildable, traceable AMPVE shell on the pinned XiaoZhi base, with native Home/navigation, working display/touch, local Wi-Fi setup, truthful About/diagnostics, muted-by-default audio, authenticated pairing/heartbeat and applied-settings acknowledgement. No camera, on-device cloud conversation or remote firmware update is required to prove this first shell. The testable web concept and capability schema are preparation, not completion of that milestone.

References: [ESP-IDF OTA and rollback](https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-reference/system/ota.html), [partition tables](https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-guides/partition-tables.html), [pinned XiaoZhi board](https://github.com/78/xiaozhi-esp32/blob/563a4f0a70d34eea5547977f2a39efa401c2ea35/main/boards/waveshare/esp32-p4-wifi6-touch-lcd/esp32-p4-wifi6-touch-lcd.cc), [pinned upstream partition CSV](https://github.com/78/xiaozhi-esp32/blob/563a4f0a70d34eea5547977f2a39efa401c2ea35/partitions/v2/32m.csv).
