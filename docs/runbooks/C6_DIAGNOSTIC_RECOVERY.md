# 7B automatic diagnostic and recovery validation

Scope: Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, P4 revision 1.3, 32 MiB flash, the stock-preserving profile only. Other ESP32 profiles remain future work. No physical C6 probe, restoration, AMPVE startup or Wi-Fi session has been validated from this VPS.

## Browser behavior

After the owner confirms the board name, the browser fetches an authenticated, curated RAM diagnostic and rechecks the connected P4 revision, flash capacity and security state. It uses ROM memory commands without the flash-reader stub to load the diagnostic. The program queries ESP-Hosted over the profile's SDIO pins and returns a bounded response tied to a fresh browser nonce. No credentials, private flash bytes or raw serial logs are uploaded. The temporary program may reset the C6 connection. RESET returns the P4 to its existing boot selection.

An observed C6 target and version 2.12.13 match the pinned host version; this is not proof of a working network, cryptographic C6 attestation, bootloader rollback or release approval. A different version, malformed response, timeout or unavailable package never passes. The diagnostic does not upgrade the C6. The optional connection help provides a retry action. An imported backup alone never supplies live diagnostic evidence.

The RAM-only build uses Espressif's experimental RAM application mode, with SPI flash/PSRAM initialization excluded. See the [Espressif configuration reference](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32p4/api-reference/kconfig-reference.html#config-app-build-type-pure-ram-app); the actual build is pinned to the IDF source listed below. Firmware source, linker ranges and the linked executable are checked before selecting a package. This is a development diagnostic awaiting its first physical trial, not a validated release.

Once the candidate is compared with verified backups, a connected board with read consent is automatically compared against the recovery plan. Technical details provide a retry. Without a connected board, file preparation can continue but physical comparison is not implied.

## Build and select the RAM package

Use external build/output directories and the existing firmware toolchain. Pin IDF to `fff9895c82d744c7237be8847347bdd1b07c6643`, ESP-Hosted 2.12.13, esp_wifi_remote 1.6.4, and the checked-in component lock. Stage with:

```bash
"$AMPVE_TOOL_PYTHON" firmware/tools/c6_probe.py stage --work "$AMPVE_PROBE_WORK"
# After sourcing the pinned IDF export.sh:
idf.py -C "$AMPVE_PROBE_WORK" -DIDF_TARGET=esp32p4 reconfigure
nice -n 10 ninja -C "$AMPVE_PROBE_WORK/build" -j2
"$AMPVE_TOOL_PYTHON" firmware/tools/c6_probe.py package \
  --work "$AMPVE_PROBE_WORK" --idf "$IDF_PATH" --output "$AMPVE_PROBE_OUTPUT"
```

Defaults must select `ESP32P4_SELECTS_REV_LESS_V3` and `ESP32P4_REV_MIN_100`; assigning the hidden min/max values alone does not override IDF's newer-chip default. For a previously configured external project, retain its rejected sdkconfig under another filename and regenerate from the staged defaults. Use size optimization for the constrained RAM application.

Never run the generated `idf.py flash` instructions. The packager checks exact staged source, configuration, internal-RAM image segments/entrypoint, and the defined ELF symbols for flash/NVS/OTA/eFuse write entrypoints. Package only committed source. Keep the ELF, lock, SDK configuration and symbol report with the artifact outside Git. This inspection is defense in depth, not a formal proof of every library instruction.

Select the verified output through the private platform configuration's `c6_probe_root`, then restart the platform. The default selects no package. Metadata and bytes require login; the server rehashes the selected artifact for each request. The browser independently checks the full artifact hash and RAM boundaries. Neither this configuration nor the diagnostic response changes the signed installation-release gate.

## Recovery comparison and execution contract

The original full backup is rehashed locally. The recovery module derives original bytes itself, never trusting uploaded region instructions. The only allowed restoration intervals are:

| Order | Region | Bound |
| --- | --- | --- |
| 1 | Original NVS | `0x3B000`, `0xD2000` bytes |
| 2 | Originally empty AMPVE app area | `0xE00000`, exactly the initial plan's sector-rounded app span, at most `0x3F0000` |
| 3 | Original boot selection | `0x10D000`, both original sectors, `0x2000` bytes |

Before any proposed restore, a full connected-flash read rejects differences outside those intervals. A repeated full comparison rejects changes since review. Consent to restore original software, lose AMPVE settings and keep stable USB power is separate from the read-only check. Every region is read back and hashed before the next write; boot selection is last. A final full read must match the original backup SHA-256 before reset. No full-chip erase, bootloader/table/factory/ota_0/asset writes, C6 flashing or security provisioning is supported. If other software changed outside the initial installation span, this bounded route refuses it.

The write executor is tested with synthetic flash but deliberately has no production button yet. Physical write approval must name the actual locally generated plan before a supervised restore trial. The read-only comparison does not exercise the stock bootloader and cannot close that gate.

## First physical evidence to collect

1. Connect the programming USB port, confirm the board and run the temporary check. Record only the bounded status/version and diagnostic package hash; do not share raw logs or backups.
2. Import the existing two verified backups and audit record. With the board connected, let AMPVE prepare the candidate and compare recovery readiness. A changed stock NVS state can be legitimate; changes outside the allowed restoration intervals require investigation.
3. Press RESET and confirm the original application still starts. This checks return from the RAM diagnostic, not restoration after installation.
4. After C6/stock boot behavior and the exact write plan are reviewed, obtain applicable physical-write consent, install the exact AMPVE app and selection, and check startup/provisioning/pairing/heartbeat.
5. Perform the separately approved exact restoration, verify the full flash against the original backup, and physically confirm original startup. Only then record physical recovery success. Power-interruption and Wi-Fi OTA/rollback tests remain separate acceptance evidence.

Software coverage includes ROM memory-only transfer, nonce mismatch, silent cancellation, artifact tampering, changed recovery source/intervals/current flash, app readback failure before boot selection, full recovery readback, authenticated delivery and rendered onboarding. Fixtures do not establish physical results. Track remaining hardware gates in #10 and #12; do not close them from compilation or synthetic tests.

## Prepared package evidence (2026-09-13)

Source `4b7d6a4a6913c9fec159eadc17d9bebc35fb0442` produced the RAM package at the private `c6-probe-review-01` directory: **277,152 bytes**, SHA-256 `cd949ab8d557e4310f709c8b8a61fdae2fa15bcc733f3b99bf404b090f2b4b79`. The browser parsed the actual artifact successfully. Entry is `0x4FF0031A`; segments are SPM `0x30100000`/180 bytes, low SRAM `0x4FF00000`/158488, `0x4FF26B80`/4988, `0x4FF28200`/572, and high SRAM `0x4FF40000`/112824. The linker retains the ROM/bootloader gap; no linker memory-region expansion or IDF source patch was made.

The dedicated diagnostic uses size optimization, disabled debug assertions, no CLI/memory monitor/termios and newlib nano. The pinned IDF newlib dispatch table otherwise retains unused floating-point stdio routines: two explicit linker wrappers reject float formatting/parsing with `ENOTSUP`. Diagnostic output uses ROM string/unsigned-integer formatting. This reduced the image to the actual rev1 RAM limits without removing explicit profile, protocol, timeout or browser safety checks. These settings apply only to this temporary probe, not AMPVE firmware. Earlier wrong-revision and oversized builds were rejected and are not selected artifacts.

Packaging checked staged source, IDF pin, SDK profile/security flags, image checksum/digest/revision, RAM intervals/entrypoint and defined executable symbols. No forbidden flash/NVS/OTA/eFuse write entrypoints were linked. The ELF places the low/high heap starts at `0x4FF28440` and `0x4FF5CA30`; runtime free heap and task behavior still need measurement on the device. One successful build is recorded, not independent reproduction.

Validation: 36 Node tests, eight Django delivery tests and the rendered Chromium onboarding fixture at three viewport widths passed. The ROM memory-transfer fixture also checks silent cancellation and transport closure. Physical results remain unvalidated; selecting this diagnostic cannot authorize an AMPVE installation or a restore.
