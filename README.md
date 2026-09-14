![AMPVE — Your devices. New possibilities.](images/ampve-brand-kit-v1/banners/github-readme-banner-v1.png)

<p align="center">
  <strong>Bring apps and AI into your world.</strong><br>
  <a href="https://ampve.com">ampve.com</a> ·
  <a href="docs/ARCHITECTURE.md">Architecture</a> ·
  <a href="docs/SUPPORTED_HARDWARE.md">Supported hardware</a> ·
  <a href="SECURITY.md">Security</a>
</p>

AMPVE is a web platform for giving supported devices new capabilities. It brings device setup, ownership, applications, configuration and software updates into one approachable workspace.

The first experience is **AMPVE Companion**, a friendly AI application designed for voice, touch and expressive screens. AMPVE Core provides the managed foundation beneath it and creates a path for additional applications without giving up device ownership or recovery.

## Private preview

AMPVE is available as a private preview at **[ampve.com](https://ampve.com)**. The current hardware profile is the Waveshare ESP32-P4-WIFI6-Touch-LCD-7B.

The preview includes:

- guided browser setup for supported hardware;
- authenticated device enrollment and ownership;
- device status, configuration and capability reporting;
- signed software delivery over Wi-Fi;
- an authenticated visual console with mouse, touch and keyboard input;
- encrypted Gemini Live and OpenAI Realtime provider connections; and
- a browser-based Companion voice experience.

Native Companion audio on the device and additional hardware profiles are outside the current preview offering. See [supported hardware](docs/SUPPORTED_HARDWARE.md) for the precise compatibility boundary.

## How AMPVE works

1. Sign in to your AMPVE workspace.
2. Connect a supported device through the guided browser flow.
3. Claim the device and configure it from your account.
4. Choose an available application and personalize it.
5. Manage the device and receive authenticated software updates over Wi-Fi.

Provider credentials stay on the AMPVE server. Devices connect outbound with revocable credentials and receive only the configuration and capabilities assigned to them.

## Applications without losing AMPVE

AMPVE Core owns device startup, drivers, enrollment, recovery, updates and the visual interface. Companion uses this native foundation. The application model also supports future signed, resource-bounded packages that can coexist with Companion. Applications that require new native drivers follow the reviewed Core release path.

This separation allows AMPVE to grow into a curated application catalog while preserving a consistent management and recovery experience.

## Technology

| Component | Role |
|---|---|
| Django and PostgreSQL | Accounts, devices, applications, configuration and deployment state |
| FastAPI and Pipecat | Realtime provider sessions and audio transport |
| ESP-IDF and XiaoZhi ESP32 | Native device runtime and supported-board integration |
| ESP Web Tools | Browser-assisted USB setup |

AMPVE builds on these open-source foundations and retains their respective notices. No project-wide open-source license is currently provided.

## Repository

This repository contains the AMPVE web platform, device runtime integration, browser setup tools, automated tests and selected brand assets. Operational records, private hardware backups, credentials, release signing material and internal product notes are maintained outside the public repository.

For a technical overview, read [Architecture](docs/ARCHITECTURE.md). Security researchers should follow the private reporting process in [Security](SECURITY.md).

<p align="center">
  <a href="https://ampve.com"><strong>Visit AMPVE →</strong></a>
</p>
