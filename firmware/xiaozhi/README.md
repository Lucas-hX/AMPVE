# AMPVE Core for XiaoZhi ESP32

This directory contains AMPVE's native ESP-IDF integration for a pinned XiaoZhi ESP32 revision. The upstream repository is resolved during preparation and is not vendored here.

## Contents

| Path | Purpose |
|---|---|
| `upstream.json` | Pinned upstream source and supported hardware profile |
| `dependencies.lock` | Resolved component versions and integrity metadata |
| `sdkconfig.ampve` | AMPVE configuration for the supported Waveshare 7B profile |
| `overlay/main/` | Core startup, minimal display, enrollment, management, OTA and package host |
| `partitions/` | Reviewed stock-compatible partition definition |
| `../tools/` | Source preparation, verification, build and release tooling |

AMPVE Core Lite preserves a managed runtime beneath bounded applications. It authenticates device traffic, verifies signed releases, reports typed health figures and retains local recovery controls. The `0.1.25-core-lite-dev` preparation step replaces XiaoZhi's broad source set with an allowlist: board display/touch/backlight, Wi-Fi, enrollment, OTA, diagnostics and signed app hosting. Companion, codec/I²S, camera, AI protocols, visual-console client, sounds and emoji/assets are not compiled into this candidate.

The Reader package kind currently presents only a truthful host-ready screen. PDF preparation, bounded internal-flash synchronization and physical reading are separate pending work. The first Reader intentionally omits microSD and SD-card drivers. No candidate artifact or physical deployment exists merely because the source prepares successfully.

The supported target is documented in [Supported hardware](../../docs/SUPPORTED_HARDWARE.md). High-level trust and update boundaries are described in [Architecture](../../docs/ARCHITECTURE.md) and [Security](../../SECURITY.md).

Private device backups, resolved upstream worktrees, build output, firmware binaries, publisher keys and deployment records must remain outside Git.

Upstream references:

- [XiaoZhi ESP32](https://github.com/78/xiaozhi-esp32)
- [ESP-IDF](https://github.com/espressif/esp-idf)
- [esptool](https://github.com/espressif/esptool)
