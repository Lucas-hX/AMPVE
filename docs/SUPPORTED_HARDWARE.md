# Supported hardware

AMPVE compatibility is defined per complete hardware profile. A shared ESP32 chip family or similar product name does not establish compatibility.

## Private preview profile

| Hardware | Status | Available capabilities |
|---|---|---|
| Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, ESP32-P4 revision 1.3, 32 MiB flash/PSRAM, 1024 × 600 display | Private preview | Browser setup, Wi-Fi management, display and touch interface, authenticated visual console, capability reporting and signed Wi-Fi updates |

The profile uses the board's ESP32-C6 connectivity path, GT911 touch controller and stock-compatible flash layout. AMPVE preserves the original bootloader, partition table and factory application during the supported initial installation flow.

Native Companion audio and camera support are not included in the current preview compatibility statement. Other ESP32 boards, Raspberry Pi devices and general-purpose third-party firmware are not currently supported.

## Setup and updates

Supported devices begin with the guided installer at [ampve.com](https://ampve.com). The browser verifies the expected device profile before presenting an installation action. Once enrolled and connected to Wi-Fi, the device receives approved updates through its authenticated AMPVE connection.

Do not use a package or firmware image for a different board revision or layout. AMPVE compatibility checks are part of the supported setup and recovery path.
