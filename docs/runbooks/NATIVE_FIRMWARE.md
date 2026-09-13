# Native development firmware: audit, build and hardware acceptance

Status: native source and build tooling merged in PR #5, followed by the stock-preserving browser flow in PR #39. Hardware installation is **not approved**. See the delivery evidence at the end of this runbook for the actual build result.

## Stock-preserving successor

The current source builds `0.1.2-profile-dev` with the [shared versioned hardware contract](HARDWARE_PROFILES.md). Its generated native header checks board pins, initialized PSRAM and partition entries; new review bundles include the matching compatibility tuple. The `0.1.1-stock-dev` evidence below remains historical until the new candidate's build evidence is recorded.

The active build uses `7b-stock-v1.csv`; the previous stock candidate was `0.1.1-stock-dev`. See [browser installation](BROWSER_INSTALLATION.md) and [ADR 0004](../decisions/0004-stock-preserving-browser-installation.md). The original 2026-09-13 layout-migration build and hashes below are historical evidence, not the current write plan. The current installer proposes only the empty stock OTA slot plus locally generated boot selection; it never writes the generated bootloader/table/blank otadata. Lucas reports completed matching physical backups and confirms stock startup after audit; exact local candidate comparison, C6/bootloader review, separate-storage confirmation and write approval remain pending.

## What this milestone contains

A small overlay on XiaoZhi commit `563a4f0a70d34eea5547977f2a39efa401c2ea35`, not a copied firmware repository. The selected build is the legacy Waveshare P4 7B profile. ESP-IDF is **v6.1**, commit `fff9895c82d744c7237be8847347bdd1b07c6643`; its installer pins the compiler and Python constraints. `firmware/xiaozhi/dependencies.lock` pins registry component versions/hashes. The protected local Wi-Fi component is derived from `78/esp-wifi-connect` **3.3.1**; its original MIT notice is preserved in the isolated build and review bundle.

The native LVGL interface uses the original AMPVE symbol and Companion icon, converted deterministically to small RGB565 arrays. English Home, Wi-Fi, My device, Settings and Companion screens use large controls and the existing ivory/graphite/sage identity. This is native C++/LVGL source, separate from the explicitly simulated web interface preview.

- The real Wi-Fi manager reuses XiaoZhi/ESP-Hosted. Local setup uses WPA2, a random 16-character per-boot password shown only on the display, one client and an approximately five-minute window. It preserves saved networks; opening setup does not erase them. Reopen using the screen or the board's BOOT button. The portal uses local HTTP inside that temporary protected WLAN, accepts connections only to the AP interface, checks local Host/Origin, requires a same-origin request header for API calls and escapes SSID output. This is development provisioning, not an internet-facing admin service.
- Pairing uses the existing AMPVE HTTPS enrollment/exchange API, a server-issued expiring code and a random device credential stored before exchange. Pending proof/code/expiry survive a reboot; retrying exchange reuses the same credential. No provider key reaches firmware. A pending pairing that cannot resume before server expiration may leave an awaiting device in the dashboard; revoke that entry before starting again.
- Verified HTTPS uses the ESP-IDF root certificate bundle, a fixed `ampve.com` origin, bounded JSON/responses/timeouts and no redirects. SNTP time is required before TLS requests. No raw API response, credential or Wi-Fi password is logged by the AMPVE management client. SNTP is not authenticated; TLS still verifies the server certificate and host.
- Heartbeats report measured flash, detected external RAM, the configured display dimensions and explicitly qualified capabilities. A known-address codec response is not speaker detection; only local confirmation after the quiet tone reports the speaker test as passed. Microphone testing/capture is unavailable; even the RX DMA channel stays disabled during speaker testing.
- Name and bounded volume persist before acknowledging configuration. **Keep the dashboard microphone muted:** remote unmute is unsupported and deliberately leaves that configuration pending. Acknowledgement means accepted settings, not successful audio playback. Local volume changes remain local until a newer remote configuration arrives. Revocation stops authenticated management; pairing again requires a local action and starts acknowledgement from zero.
- The management worker is separate from the LVGL event loop. Network/provider failure does not intentionally block navigation. No upstream `Application::Initialize/Run`, XiaoZhi cloud registration, camera initialization, provider session or firmware-download endpoint runs in this shell.
- Startup has a separate 60-second local check: UI ticks, touch initialization, management task and storage readiness. It does not require Wi-Fi association, internet or provider access. A successful check confirms a pending OTA app; failure attempts SDK app rollback and otherwise restarts. Three unconfirmed boots stop peripheral initialization. In this bounded recovery state, hold BOOT for five seconds to retry: only the AMPVE boot counter is cleared. NVS initialization errors never cause automatic erasure. Fatal upstream LCD/audio-driver paths still exist; graceful handling and the boot guard must be physically tested.

The runtime refuses board initialization unless chip revision is exactly **1.3** and flash reports **32 MiB**. This is an application guard, not a pre-flash compatibility check: the bootloader must already be able to boot the chip. The compiled bootloader targets pre-v3 P4 revisions 1.x. The C6 companion firmware must also match the resolved ESP-Hosted host (**2.12.13**); no C6 image is installed or assumed compatible here.

## Step 1 — local audit and backup, before installation

Run these commands on the computer physically connected to the board, not on the VPS. Close browser serial inspection, serial monitors and other port users first. Use stable power and confirm the printed **Waveshare ESP32-P4-WIFI6-Touch-LCD-7B** label. A USB VID/PID is not a board-model check.

From an updated repository checkout, Windows PowerShell:

```powershell
py -3 -m venv "$env:USERPROFILE\.ampve-firmware-tools"
& "$env:USERPROFILE\.ampve-firmware-tools\Scripts\python.exe" -m pip install -r firmware/tools/requirements.txt
& "$env:USERPROFILE\.ampve-firmware-tools\Scripts\python.exe" firmware/tools/audit.py ports
# Replace COM7 with the selected programming port; use a NEW private output directory.
& "$env:USERPROFILE\.ampve-firmware-tools\Scripts\python.exe" firmware/tools/audit.py capture --port COM7 --output "$env:USERPROFILE\AMPVE-private\audit-7b-01" --ram-stub --baud 460800
```

`--ram-stub` explicitly opts into esptool's temporary RAM reader to speed up two full 32 MiB reads; it does not write flash. Omit it and use the default 115200 baud for ROM reading, which can be substantially slower. The script can reset the chip into download mode and change volatile communication settings. It only reads security state/flash; there are no erase/write/eFuse operations. After completion, reset the board manually. If automatic ROM entry fails, follow this board's documented BOOT/RESET procedure; do not improvise a write command.

Linux/macOS use an external virtualenv and its `bin/python`, with the actual `/dev/...` port. Never run this process as a generic root operation merely to solve port access. The tool refuses audit output inside a Git checkout and creates private files (Windows users should also retain their normal private-user directory ACLs).

The capture stops for an unexpected chip/revision/capacity, enabled or unknown security state, mismatching independent reads, incomplete dump or ambiguous/corrupt partition table. Failure details stay in `serial-private.log`; partial files are **not** approved backups. A successful directory contains two independently read dumps, hardware metadata and `audit-private.json`. Copy the complete directory to separate private storage. Do not upload flash dumps, NVS or raw serial logs to GitHub or AMPVE: they may contain stock credentials and other personal data.

An existing owner's backup can also be inspected **offline**:

```powershell
& "$env:USERPROFILE\.ampve-firmware-tools\Scripts\python.exe" firmware/tools/audit.py inspect "$env:USERPROFILE\AMPVE-private\original-backup.bin"
```

Offline inspection verifies partition MD5, boundaries and full-dump size, and extracts bounded app metadata where recognizable. It does not verify current security state, the board label, stock bootloader location, successful restore or the C6 firmware. A missing MD5 or unusual stock layout requires manual review; do not weaken the validator to force a pass. This audit is purposefully limited to the first P4 1.3/32 MiB unit.

## Steps 2 and 3 — isolated native build and review bundle

The Debian build needs Git, Python 3.13 with venv, CMake, Ninja, GCC build prerequisites, flex, bison, libffi-dev and the exact ESP-IDF tool installation. Keep upstream repositories, Python environments and all output outside AMPVE's Git checkout.

```bash
# One-time preparation in an external cache. Verify the IDF commit before installing tools.
git clone --branch v6.1 --depth 1 --recursive --shallow-submodules \
  https://github.com/espressif/esp-idf.git ~/.cache/ampve-firmware/esp-idf
git -C ~/.cache/ampve-firmware/esp-idf rev-parse HEAD
# Required: fff9895c82d744c7237be8847347bdd1b07c6643
IDF_TOOLS_PATH="$HOME/.cache/ampve-firmware/idf-tools" \
  ~/.cache/ampve-firmware/esp-idf/install.sh esp32p4
python3 -m venv ~/.cache/ampve-firmware/tooling
~/.cache/ampve-firmware/tooling/bin/pip install -r firmware/tools/requirements.txt

export IDF_TOOLS_PATH="$HOME/.cache/ampve-firmware/idf-tools"
export AMPVE_IDF_PATH="$HOME/.cache/ampve-firmware/esp-idf"
export AMPVE_WORK="$HOME/.cache/ampve-firmware/xiaozhi"
export AMPVE_TOOL_PYTHON="$HOME/.cache/ampve-firmware/tooling/bin/python"
firmware/tools/build.sh
"$AMPVE_TOOL_PYTHON" firmware/tools/release.py --work "$AMPVE_WORK" \
  --idf "$AMPVE_IDF_PATH" --output "$HOME/.local/state/ampve/firmware-review-01"
"$AMPVE_TOOL_PYTHON" -m unittest discover -s firmware/tests -v
```

Use a new isolated work directory when changing the integration scripts. `prepare.py` intentionally refuses a checkout at another upstream revision or an initially modified checkout. A prepared directory is for repeated overlay builds; it is not an arbitrary upstream working copy. The build resolves the pinned baseline, creates the protected local provisioning override and rejects registry version/hash drift after reconfiguration. Compilation uses two jobs with reduced priority for this shared VPS.

The review bundle includes the app/bootloader/partition/otadata files referenced by the build, SHA-256 hashes, proposed regions, SDK configuration, resolved dependency lock, compiler version, Python environment snapshots, source/input hashes, integration diff and modified provisioning component with license. The minimum UI assets live in the app, and the build does not propose a shared-assets write. It is **not** an ESP Web Tools manifest and always says `installable: false`. Packaging validates the selected profile, disabled irreversible security options, app fit in both slots and non-overlapping artifact regions.

The recipe is pinned and traceable, with `CONFIG_APP_REPRODUCIBLE_BUILD=y`. Two separately compiled project directories on this VPS produced identical app, bootloader, partition-table and otadata bytes. This shares one pinned toolchain and registry source cache; reproduction on a second machine is still a separate acceptance test. `release.py --comparison-work /path/to/second/checkout` rechecks all proposed artifact hashes before recording that evidence.

After privately transferring a candidate review bundle to the local computer, compare it with the new audit:

```powershell
& "$env:USERPROFILE\.ampve-firmware-tools\Scripts\python.exe" firmware/tools/compare.py --audit "$env:USERPROFILE\AMPVE-private\audit-7b-01" --candidate "$env:USERPROFILE\AMPVE-private\firmware-review-01"
```

The comparison rehashes both full backups and proposed artifact files, checks the recorded hardware/security profile and reports whether partition layouts agree. It still cannot approve installation. Before a first write, review exact stock and candidate bootloader/partition locations, every overwritten/preserved data region, image compatibility, power/ROM access and the matching restore procedure. No generic full-chip erase, Secure Boot, flash encryption or eFuse changes belong to this milestone. Never execute upstream `idf.py flash` from these development files just because compilation passed.

## Acceptance on the physical board — only after a separately reviewed installation

1. Record initial serial boot diagnostics privately. Confirm no boot loop, correct orientation, visible original mark, legible Home and working touch across the screen. Confirm actual RAM/flash readings and firmware version. The web preview is not evidence for any of these.
2. Without Wi-Fi/internet, verify local navigation remains responsive and microphone remains muted. With no saved network, join the displayed temporary WPA2 setup WLAN from a phone/PC using its screen-only password; supply Wi-Fi locally. Verify it closes after setup or timeout, and saved Wi-Fi reconnects after power cycling.
3. On-device, tap **Pair with my AMPVE account**. In the existing dashboard **Add a device**, enter that real code. Verify online status and explicitly device-reported capabilities. Reboot during pending pairing and verify exchange resumes before expiration without a second identity.
4. Keep microphone muted in dashboard settings; change device name/volume. Verify the name/desired volume on-device and acknowledgement on the next heartbeat. Requesting unmute must remain pending and must not enable capture. Test VPS outage/reconnect and owner isolation/revocation; a revoked device requires local pairing again.
5. Tap **Play a quiet speaker test** once. Confirm **I heard the tone** only if actually audible. Verify the dashboard distinguishes configured/initialized/passed. Do not infer microphone or USB-camera support from a speaker result.
6. Run repeated cold boots and intentionally unavailable Wi-Fi/VPS. Validate startup confirmation and the bounded recovery route. App rollback requires an actual previously valid OTA slot and compatible bootloader; a first USB installation has no guaranteed fallback app. Power-interruption/failed-image recovery testing needs its own exact reviewed test plan.

## Next implementation after this candidate

- Finish the owner's local audit and C6 compatibility review; then prepare a specific first USB write/restore plan for approval.
- Validate and harden the native drivers, screen legibility, provisioning and management on this physical board. Replace remaining fatal optional-codec paths with degraded UI errors before calling the runtime production ready.
- Implement the XiaoZhi Opus/audio adapter to FastAPI/Pipecat and explicit local Companion start/stop, echo behavior and interruption. Browser voice success does not prove this adapter.
- Add a permissioned local microphone meter before enabling network capture; keep local mute authoritative.
- Validate the implemented native inactive-slot OTA candidate and complete physical rollback tests; see [NATIVE_OTA.md](NATIVE_OTA.md). ESP-IDF rollback configuration alone is not an update service.

## Sources used for compatibility review

- [ESP-IDF v6.1 P4 random-number generation](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32p4/api-reference/system/random.html): P4 application startup keeps the SAR entropy source enabled by default. The shell does not disable or repurpose it.
- [Official esptool scripting API](https://docs.espressif.com/projects/esptool/en/latest/esp32p4/esptool/scripting.html): explicit connection, optional RAM stub, flash attachment and read-only flash API sequencing. The installed API was checked against esptool 5.4.0 source.
- [ESP-IDF v6.1 P4 OTA](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32p4/api-reference/system/ota.html): pending-app confirmation and rollback are distinct from initial USB layout replacement.

## Verified delivery evidence — 2026-09-13

- PR #4 merged: `24f2cee` on main, after Lucas's approval. This native milestone is a separate review branch.
- Actual ESP32-P4 compile succeeded in two separate source/build directories with IDF v6.1, RISC-V GCC `esp-15.2.0_20251204` and the pinned registry lock. The app, bootloader, partition table and initial otadata are byte-identical between those builds. No AMPVE compiler warnings were reported.
- App: **2,653,600 bytes** (`0x287da0`), with **1,540,704 bytes / 37%** remaining in each 4 MiB app slot. SHA-256: `769e510f5cf0b11cf0dc7d9cf438ca851a500961c2e65c4ee01c7d01ec58864e`.
- Generated regions, **not approved writes**: bootloader `0x2000`, partition table `0x8000`, initial otadata `0x10d000`, app `0x200000`. The candidate leaves shared assets out of its proposed files; that does not prove preservation against the owner's stock layout.
- Eleven Python tests passed for offline audit, malformed/ambiguous tables, full-dump boundaries, unknown/enabled security rejection, capture sequencing/port cleanup using a strict fake and release configuration gates. No physical serial port was used by these tests.
- Forty-two Django tests passed against the isolated test database. The public web runtime-concept test passed its five screens, three viewport widths and explicitly simulated controls. A separate browser fixture test of the actual patched provisioning HTML passed escaped SSID rendering, required API headers and cleared password input. This does not validate ESP-Hosted, Wi-Fi radio or the on-board HTTP server.
- The upstream patch transformations reproduced against a fresh pinned checkout/original resolved Wi-Fi component. Build environments, upstream repositories, artifacts and logs remain outside Git. Existing AMPVE and NEUROSIS services remained active; no platform migration or service reconfiguration was needed.
- **Not tested:** the current physical board's flash/security/layout, backup/restoration, C6 ABI, native screen/touch, speaker, on-board HTTPS enrollment, reboot/revocation behavior, power interruption or rollback. No firmware was installed and no hardware security settings changed.

## Native verification foundation

See [NATIVE_OTA.md](NATIVE_OTA.md) for the `0.1.3-ota-verify-dev` candidate: native signed-policy verification, complete-image hashing and checked startup identity reports. The integrated client follows in `0.1.4-ota-client-dev`; physical OTA/rollback remain pending.
