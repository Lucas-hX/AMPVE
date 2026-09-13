# XiaoZhi native AMPVE shell

This directory contains a small native integration on a pinned upstream revision, not a vendored XiaoZhi repository. See [the native firmware runbook](../../docs/runbooks/NATIVE_FIRMWARE.md) for build commands, local audit instructions, verified delivery evidence and the hardware acceptance checklist.

- `upstream.json`: reviewed upstream commit, exact first hardware profile and candidate status.
- `sdkconfig.ampve`: legacy P4 7B, English, IDF reproducible-build mode, rollback, minimum in-app assets and muted development configuration.
- `dependencies.lock`: registry versions/hashes, before the explicitly tracked local provisioning override.
- `overlay/main/`: native entry point, LVGL shell and authenticated HTTPS management worker. The upstream application/voice/OTA state machine is not started.
- `../tools/prepare.py` and `provisioning.py`: checked source transformations and a protected local copy of the resolved Wi-Fi component, retaining its upstream license outside Git.
- `../tools/audit.py`, `build.sh`, `release.py`, `compare.py`: read-only local backup, build, non-installable review bundle and comparison workflow.

At the pinned commit, the upstream `esp32-p4-wifi6-touch-lcd-7b` profile targets P4 revisions 1.x, 32 MiB flash and `partitions/v2/32m.csv`. The similarly named `p4x` profile is not selected. The AMPVE runtime adds an exact revision-1.3/32-MiB guard, and deliberately skips camera initialization. None of these facts certify the owner's current partitions, security state, C6 firmware or a successful recovery.

The shell implements real enrollment/heartbeat calls against [the management contract](../../docs/runbooks/DEVICES.md); it has been compiled, not validated on physical hardware. Display/touch, provisioning, speaker output and recovery remain local acceptance work. Microphone capture, on-board provider sessions, the XiaoZhi Opus adapter and remote OTA are not delivered in this milestone.

No firmware was flashed, eFuse changed or public installer manifest published. Private backups, credentials, build output and whole upstream checkouts remain outside Git. The review bundle is a development artifact with `installable: false`; it is not a release approval. Raspberry Pi and a permanent USB bridge remain future runtimes.

References: [pinned board configuration](https://github.com/78/xiaozhi-esp32/blob/563a4f0a70d34eea5547977f2a39efa401c2ea35/main/boards/waveshare/esp32-p4-wifi6-touch-lcd/config.json), [official esptool scripting API](https://docs.espressif.com/projects/esptool/en/latest/esp32p4/esptool/scripting.html), [ESP-IDF v6.1 P4 OTA API](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32p4/api-reference/system/ota.html).
