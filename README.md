![AMPVE — Your devices. New possibilities.](images/ampve-brand-kit-v1/banners/github-readme-banner-v1.png)

<p align="center">
  <strong>Bring apps and AI into your world.</strong><br>
  <a href="https://ampve.com">ampve.com</a> ·
  <a href="docs/ARCHITECTURE.md">Architecture</a> ·
  <a href="docs/SUPPORTED_HARDWARE.md">Supported hardware</a> ·
  <a href="SECURITY.md">Security</a>
</p>

AMPVE is a web platform for giving supported devices new capabilities. It brings device setup, ownership, applications, configuration and software updates into one approachable workspace.

The active application is **AMPVE Reader**, an offline-first reading experience for private PDF libraries. **AMPVE Core Lite** is the small managed foundation beneath it: ownership, connectivity, display/touch, signed updates, recovery and a bounded application host. The earlier Companion path remains historical compatibility work and is not compiled into the new candidate.

## Private preview

AMPVE is available as a private preview at **[ampve.com](https://ampve.com)**. The current hardware profile is the Waveshare ESP32-P4-WIFI6-Touch-LCD-7B.

The preview includes:

- guided browser setup for supported hardware;
- authenticated device enrollment and ownership;
- device status, configuration and capability reporting;
- signed software delivery over Wi-Fi;
- a private Reader library with collections, books, ordered PDF parts and virtual page ranges;
- signed, resource-bounded application declarations; and
- retained legacy provider/Companion services for the already-installed development board.

PDF preparation, bounded internal-flash delivery and on-device reading are not complete. The first physical 7B still runs the prior `0.1.24-core-dev` image; no Core Lite update has been built, signed or deployed. The first Reader intentionally has no microSD support. Additional hardware profiles remain outside the current preview offering. See [Reader](docs/READER.md), [architecture](docs/ARCHITECTURE.md) and [supported hardware](docs/SUPPORTED_HARDWARE.md).

## How AMPVE works

1. Sign in to your AMPVE workspace.
2. Connect a supported device through the guided browser flow.
3. Claim the device and configure it from your account.
4. Choose an available application and personalize it.
5. Manage the device and receive authenticated software updates over Wi-Fi.

Private PDF sources stay on the AMPVE server until a later preparation pipeline creates verified device content. Devices connect outbound with revocable credentials and receive only assigned, signed capabilities.

## Applications without losing AMPVE

AMPVE Core Lite owns device startup, required profile drivers, enrollment, recovery, updates and the application host. Reader uses a signed `document_reader` declaration; compact prepared content will use a separately verified, quota-bound internal-flash path. The first Reader does not compile or initialize an SD-card stack. Applications that require new native drivers still follow the reviewed Core release path.

This separation allows AMPVE to grow into a curated application catalog while preserving a consistent management and recovery experience.

## Technology

| Component | Role |
|---|---|
| Django and PostgreSQL | Accounts, devices, applications, configuration and deployment state |
| FastAPI and Pipecat | Retained legacy realtime provider sessions; not part of Core Lite |
| ESP-IDF and pinned XiaoZhi integration | Core Lite runtime and supported-board integration |
| ESP Web Tools | Browser-assisted USB setup |

AMPVE builds on these open-source foundations and retains their respective notices. No project-wide open-source license is currently provided.

## Repository

This repository contains the AMPVE web platform, device runtime integration, browser setup tools, automated tests and selected brand assets. Operational records, private hardware backups, credentials, release signing material and internal product notes are maintained outside the public repository.

For a technical overview, read [Architecture](docs/ARCHITECTURE.md). Security researchers should follow the private reporting process in [Security](SECURITY.md).

<p align="center">
  <a href="https://ampve.com"><strong>Visit AMPVE →</strong></a>
</p>
