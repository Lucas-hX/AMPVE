# AMPVE Core for XiaoZhi ESP32

This directory contains AMPVE's native ESP-IDF integration for a pinned XiaoZhi ESP32 revision. The upstream repository is resolved during preparation and is not vendored here.

## Contents

| Path | Purpose |
|---|---|
| `upstream.json` | Pinned upstream source and supported hardware profile |
| `dependencies.lock` | Resolved component versions and integrity metadata |
| `sdkconfig.ampve` | AMPVE configuration for the supported Waveshare 7B profile |
| `overlay/main/` | Core startup, display, enrollment, management, OTA and console integration |
| `partitions/` | Reviewed stock-compatible partition definition |
| `../tools/` | Source preparation, verification, build and release tooling |

AMPVE Core preserves a managed runtime beneath Companion and future applications. It authenticates device traffic, verifies signed releases, reports bounded capabilities and retains local recovery controls.

The supported target is documented in [Supported hardware](../../docs/SUPPORTED_HARDWARE.md). High-level trust and update boundaries are described in [Architecture](../../docs/ARCHITECTURE.md) and [Security](../../SECURITY.md).

Private device backups, resolved upstream worktrees, build output, firmware binaries, publisher keys and deployment records must remain outside Git.

Upstream references:

- [XiaoZhi ESP32](https://github.com/78/xiaozhi-esp32)
- [ESP-IDF](https://github.com/espressif/esp-idf)
- [esptool](https://github.com/espressif/esptool)
