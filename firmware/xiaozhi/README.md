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

AMPVE Core Lite preserves a managed runtime beneath bounded applications. It authenticates device traffic, verifies signed releases, reports typed health figures and retains local recovery controls. The `0.1.26-reader-mvp-dev` preparation step replaces XiaoZhi's broad source set with an allowlist: board display/touch/backlight, Wi-Fi, enrollment, OTA, diagnostics, signed app hosting and the bounded Reader client. Companion, codec/I²S, camera, AI protocols, visual-console client, sounds and emoji/assets are not compiled into this candidate.

The Reader package kind presents an e-paper-inspired shelf and touch page navigation backed by authenticated, display-sized text responses. Progress is synchronized to the private platform. This MVP intentionally remains online-only: it does not mount, format or write the preserved internal `storage` partition. It also omits FAT, removable storage and every microSD path. The board's C6 Wi-Fi coprocessor still requires the ESP-Hosted SDIO transport (`sdmmc` in ESP-IDF); Reader cannot mount or use it as storage. No candidate artifact or physical deployment exists merely because the source prepares successfully.

The supported target is documented in [Supported hardware](../../docs/SUPPORTED_HARDWARE.md). High-level trust and update boundaries are described in [Architecture](../../docs/ARCHITECTURE.md) and [Security](../../SECURITY.md).

Private device backups, resolved upstream worktrees, build output, firmware binaries, publisher keys and deployment records must remain outside Git.

Upstream references:

- [XiaoZhi ESP32](https://github.com/78/xiaozhi-esp32)
- [ESP-IDF](https://github.com/espressif/esp-idf)
- [esptool](https://github.com/espressif/esptool)
