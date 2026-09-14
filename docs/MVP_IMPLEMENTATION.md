# AMPVE — MVP Implementation Brief

Current device milestone: the first physical 7B runs the signed 0.1.13 development release. The server observed an authenticated Wi-Fi heartbeat and settings acknowledgement 1/1. Touch/Home navigation, physical restoration, audio and Wi-Fi OTA remain pending; this is not production hardware acceptance. The current 0.1.16 candidate retains the touch transform and prepares the corrected bounded Wi-Fi trial. See [the device runbook](runbooks/DEVICES.md).
Current delivery: see [the platform runbook](runbooks/PLATFORM.md) and [ADR 0002](decisions/0002-provider-audio-and-xiaozhi.md). OpenAI browser voice is user-validated; Gemini remains unvalidated; XiaoZhi remains the sole selected firmware foundation.

Date: 2026-09-12

Status: Platform, browser voice and device-management server delivered; first 7B onboarded; remaining physical acceptance pending

Audience: Developers and coding agents building AMPVE on a Debian VPS

## 1. What we are building

**Your devices. New possibilities.** AMPVE brings apps and AI into the world around you. A user signs in, connects supported hardware, chooses an application, and makes it their own. Device management is the technical foundation behind that experience, not the public-facing product category.

The first application is an expressive AI companion on a **Waveshare ESP32-P4-WIFI6-Touch-LCD-7B**. It listens, responds through a speaker, and displays a face alongside a compact diagnostic panel. Cloud AI providers supply the model intelligence. The device runs the embedded application, audio processing, display, and connectivity locally.

The first installation is for the project owner, using an administrator account and a regular test account. The experience should already feel like a product: clear setup steps, honest capability status, understandable errors, and a small application catalog. Public registration, billing, and support for arbitrary boards are outside this MVP.

The long-term product is device and application management. The companion is its first application, demonstrating the complete lifecycle from an unregistered board to a configured, connected device.

## 2. Selected foundation and reuse strategy

| Component | Responsibility | How AMPVE uses it |
|---|---|---|
| XiaoZhi ESP32 firmware, MIT | Embedded voice assistant, display integration, device state, audio, network protocol | Maintain a small, pinned fork for the Waveshare 7B; add AMPVE enrollment, management, UI, and application settings. |
| ESP Web Tools, Apache 2.0 | Browser-based USB firmware installation | Embed the installer in the AMPVE onboarding wizard with curated manifests and firmware artifacts. |
| Pipecat, BSD 2-Clause | Realtime AI sessions and provider integrations | Run a Python service on the VPS; start with Gemini Live and OpenAI Realtime integrations. |
| ESP-IDF OTA facilities | Download and boot a compatible firmware update | Reuse native update and rollback mechanisms; connect progress and results to AMPVE deployments. |
| AMPVE application | Product experience and device lifecycle | Implement accounts, ownership, credentials, catalog, configuration, deployment tracking, and the protocol adapter. |

Use upstream dependencies instead of copying their internals when possible. Keep firmware changes small and identifiable so upstream fixes remain practical to merge. Pin source commits, dependency versions, build tools, and release artifacts; do not build production releases from a moving `main` branch.

ElatoAI is a useful reference for companion settings and provider integration. It is not a required service in this architecture. ThingsBoard, MeshCentral, openBalena, a separate OTA fleet server, and an MQTT broker are not initial dependencies. Add a service only when a demonstrated requirement justifies it.

The selected projects do not form a ready-made compatible stack. **The XiaoZhi-to-Pipecat adapter is an explicit AMPVE deliverable.**

## 3. Deployment and execution locations

```text
User's computer
  Browser: AMPVE UI, account setup, provider settings, USB installer
  USB cable: first firmware installation and local diagnostics
                         |
                         v
Waveshare ESP32-P4 + ESP32-C6 connectivity
  AMPVE firmware based on XiaoZhi
  Face, touch, audio, local state, device identity, update client
                         |
              outbound HTTPS / WSS
                         |
                         v
OVH Debian VPS
  HTTPS ingress
  AMPVE web application and management API
  PostgreSQL
  XiaoZhi protocol adapter + Pipecat session service
  Curated firmware artifacts and deployment records
                         |
                         v
  Gemini Live or OpenAI Realtime API
  Credentials supplied by the device owner's AMPVE account
```

Accepted implementation stack (2026-09-13; see [ADR 0001](decisions/0001-platform-architecture.md)):

- **Django/templates** for the web interface, accounts, management API and future embedded ESP Web Tools component.
- **FastAPI/Python + Pipecat** for the future audio/session service and XiaoZhi adapter, separate from Django management.
- **PostgreSQL** for durable application state, reusing the VPS server with a dedicated AMPVE database and login role. Use migrations from the beginning.
- **Docker Compose** remains the portable deployment direction. The initial delivery uses a dedicated virtual environment and systemd to reuse the existing Unix-socket PostgreSQL and tunnel without adding a container daemon.
- **Existing Cloudflare Tunnel for ampve.com** as HTTPS ingress to the loopback application origin. Test WSS connection behavior before enabling audio; do not assume generic WebRTC/UDP transport.
- A persistent directory for immutable, versioned firmware artifacts. Object storage can be introduced later.

This is an implementation choice, not an upstream stack requirement. It deliberately avoids operating a full Supabase installation solely for this MVP.

The VPS routes sessions; it does not host the large AI models. Its available CPU, RAM, disk, and existing workloads must be inventoried before deployment. Capacity must be measured with actual audio sessions. Do not promise a device or concurrency limit from server specifications alone.

Only HTTPS/WSS ingress should be publicly accessible. Database and internal services stay private, using the existing Unix socket initially. Back up the database, artifact metadata, and the separately protected encryption key required to restore provider credentials.

## 4. Supported first device and known constraints

The local hardware audit recorded:

- Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, ESP32-P4 revision 1.3.
- 32 MiB flash and 32 MiB PSRAM.
- EK79007 display, 1024 × 600, with GT911 touch.
- ES7210 microphone input and ES8311 audio output.
- ESP32-C6 radio connected through ESP-Hosted/SDIO.
- Factory demo firmware, with an additional factory XiaoZhi image and an unused OTA slot.

These observations are a starting point, not proof that every peripheral works simultaneously in our new firmware. Reconfirm the attached unit before writing to it.

XiaoZhi includes an `esp32-p4-wifi6-touch-lcd-7b` build profile with 32 MB flash settings and revision-related configuration. Validate its current toolchain, partition layout, peripheral setup, and revision selection against our board. ESP-IDF 5.5.4 was evaluated in previous local work, but is not a pinned dependency of this new repository. Choose and record a toolchain compatible with the selected XiaoZhi commit and the physical board.

The planned Razer Kiyo RZ19-0232 camera is **not validated**. The reviewed XiaoZhi board profile configures an OV5647 MIPI camera, which does not establish USB Kiyo compatibility. USB host/UVC support, supported video formats, bandwidth, power, and coexistence with audio/display need a separate bring-up.

Build the first working voice-and-face flow before adding camera capture. The eventual first companion should support on-demand vision when the camera passes validation. Show camera status as unavailable or experimental until then; never advertise functioning vision based only on a connected USB cable.

## 5. What an application means on this ESP32

The stock Waveshare demo is not an operating system into which AMPVE can copy an arbitrary application. The board needs an initial installation of AMPVE-compatible firmware.

For this MVP, the management client and companion application share **one firmware image**. There is no independent resident management daemon that survives arbitrary replacement firmware.

The first catalog entry is `AMPVE Companion`. Its application definition contains a compatible firmware requirement and a configuration schema. The onboarding image can already contain the companion code in an inactive state. Clicking **Install & Activate** then assigns the application and applies its settings; it does not needlessly flash the same image again. If a different compatible firmware is required, the platform creates an OTA deployment first.

The UI must show these steps accurately: firmware installation, device registration, application assignment, configuration acknowledgement, and readiness. Each future ESP32 application must retain the AMPVE management integration to remain remotely manageable.

For Raspberry Pi later, applications may be separate Linux processes or containers. Preserve the distinction between hardware profile, firmware/runtime release, and application assignment in the data model without implementing a universal runtime now.

## 6. Administrator and test-user workflow

### 6.1 Administrator prepares the instance

1. Deploy AMPVE to a domain on the Debian VPS.
2. Create the initial administrator through a one-time bootstrap command or equivalent controlled setup. Do not ship a shared default password.
3. Create a normal test-user account. Public signup remains disabled.
4. Publish the supported Waveshare 7B hardware profile and a verified firmware release.
5. Publish the single `AMPVE Companion` catalog entry and its compatible release requirement.
6. Enable the Gemini Live and OpenAI Realtime integrations that have passed session tests.

Administrator and owner roles should be exercised as separate accounts even when the same person operates both. This verifies ownership checks early.

### 6.2 Test user configures a provider

1. Sign in and open **Providers**.
2. Select Gemini Live or OpenAI Realtime.
3. Enter an API key for that provider, give it a recognizable label, and save it.
4. Run **Test connection**, which clearly indicates that it may make a small billable API request.
5. Show a masked credential and last validation result. Never return the saved secret to the browser for display.

The first authentication route is API keys. Consumer ChatGPT/Codex or Google subscription login is not implemented as API authentication. API availability, billing, and quotas belong to the supplied provider account.

Keep provider keys encrypted at rest on the VPS, with the encryption key outside the database and repository. Resolve credentials from the authenticated device owner's account on the server. Keys must not appear in firmware, installer manifests, device logs, browser storage, or diagnostic exports. Support replacing and deleting a credential; deletion prevents new sessions and should terminate sessions using it.

### 6.3 Test user onboards the board

1. Open **Devices → Add device** and select **Waveshare P4 Touch LCD 7B**.
2. Show the supported browser and USB connection requirements. Web Serial requires user interaction and browser support; start with desktop Chrome/Edge and verify the selected versions.
3. Connect the board through its supported programming port using a data-capable USB cable.
4. Verify the chip family and confirm the exact board profile. Chip detection alone cannot distinguish every ESP32-P4 board.
5. Present the firmware version and what the installation will replace. The user's explicit **Install firmware** action authorizes that write in the product flow.
6. Flash the curated onboarding image using ESP Web Tools. Show progress and a useful recovery path on failure.
7. Configure Wi-Fi locally using the provisioning flow retained from the selected XiaoZhi fork. A local access-point or on-device flow is acceptable for v0; explain any temporary network switch. ESP Web Tools does not automatically supply provisioning unless the firmware implements the corresponding protocol.
8. The device connects to AMPVE and displays a short-lived pairing code.
9. The signed-in test user enters that code, names the device, and confirms ownership.
10. AMPVE shows connection status, firmware version, and capabilities reported by the device.

Implement pairing as a real ownership exchange: a cryptographically random bootstrap secret remains on the device, a short-lived human code identifies the pending enrollment, and atomic claiming associates it with one account. The device exchanges its bootstrap proof for its own revocable credential after claiming. Rate-limit attempts and expire pending enrollments. A MAC address or serial number is metadata, not authentication.

For the first development board, preserve the existing private flash backup and establish a restoration procedure before writing. Do not assume an empty factory OTA slot makes an arbitrary image or partition layout compatible. Do not enable full-chip erase as a generic installer default.

### 6.4 Test user installs and uses the first agent

1. Open the device and choose **Install application → AMPVE Companion**.
2. Select a saved provider credential and an available provider-specific voice/model preset.
3. Set companion name, language, personality instructions, and display style.
4. Review microphone behavior and enable optional camera access only if supported.
5. Click **Install & Activate**. AMPVE validates compatibility, assigns the app, and applies a versioned configuration; perform OTA only if required.
6. Show **Ready** only after device acknowledgement and successful application initialization. An accepted API request is not proof of installation.
7. Start a session from the device, initially through a touch/button action. Wake-word operation and hands-free interruption can follow measured audio validation.
8. The device captures audio, the VPS opens the selected Pipecat provider session, and the response plays through the device speaker.
9. The face changes with local listening, thinking, speaking, and error states. The debug area shows sanitized connection and session information.
10. Change provider or personality from the platform. Apply at the next session boundary, or offer an explicit restart of the current session.

The computer can disconnect after setup when the board has a working network connection. A permanent USB bridge for devices without networking is a future client application, not a capability supplied automatically by ESP Web Tools.

## 7. First companion behavior

Use approximately two-thirds of the display for the face and one-third for readable diagnostics, with a touch control to collapse diagnostics. This is a starting layout for the 1024 × 600 panel, not a fixed design system.

Required local states: starting, provisioning, pairing, idle, connecting, listening, thinking, speaking, updating, offline, and error. Blink and idle animations locally so the device remains expressive without continuous cloud messages.

The debug panel should include device name, network status, firmware version, selected provider, microphone state, and a concise last event. Transcripts are optional and must follow the user's history setting. Never show secrets.

Provide local session stop, microphone mute, and bounded volume controls. A cloud outage must stop or time out the session predictably, show offline status, and leave the UI responsive. Offline cloud conversation is outside scope; local controls and animations must continue working.

Start vision with a user-requested still image. Add a server-side image path and provider adapter support only after capture works on the board. A remote live camera viewer is a separate feature requiring an explicit streaming design. Neither Pipecat nor an IoT management API creates USB camera support by itself.

## 8. Device protocol and Pipecat integration

Retain the selected XiaoZhi WebSocket protocol wherever practical. It provides a hello exchange, binary Opus audio, listening/abort messages, text and speech events, emotions, and tool messages.

The AMPVE adapter must:

1. Authenticate the device and resolve its owner, application assignment, and provider configuration.
2. Validate the pinned protocol version and negotiate supported audio parameters.
3. Decode incoming Opus and convert sample rate/channel layout to the provider integration's requirements.
4. Feed audio into the Pipecat session; encode and packetize output audio for the device.
5. Translate listening, playback, interruption, transcript, expression, and error events in both directions.
6. Discard cancelled response audio so an interruption cannot replay stale output.
7. Release provider sessions and audio resources on stop, disconnect, timeout, or credential revocation.

Do not assume the same sample rate, voice identifier, model settings, interruption semantics, or image handling across providers. Maintain explicit provider capabilities and tested presets. Pipecat's ESP32 client is a reference, not evidence that its device transport already runs on this P4.

For v0, use HTTPS heartbeats/configuration polling independently of the on-demand audio WebSocket. This allows an idle device to receive configuration and update jobs without keeping an AI session open. Record the effective polling interval and expected command delay. A persistent management socket can replace polling later if needed.

Replace upstream activation and OTA destinations with AMPVE endpoints in the fork. An AMPVE-enrolled device must not silently register with a third-party demonstration backend.

## 9. Minimum management model and interface

Persist the following concepts:

| Entity | Essential fields or relationships |
|---|---|
| User | ID, authentication identity, role, status |
| Provider credential | Owner, provider, encrypted secret, label, validation state |
| Hardware profile | Board identity, revision constraints, supported capabilities |
| Firmware release | Immutable artifact, digest/signature, source revision, toolchain, partition compatibility |
| Enrollment | Expiring code, bootstrap proof hash, claim status |
| Device | Owner, hardware profile, credential hash, last seen, reported version/capabilities |
| Application definition | App ID, version, configuration schema, firmware/capability requirements |
| Application assignment | Device, app, credential reference, desired and acknowledged config versions |
| Deployment | Device, target release, state, progress, result and timestamps |
| Session/event | Owner/device, provider, lifecycle, timing, sanitized error details |

Start with five user-facing areas: **Home, My devices, Explore apps, Connections, and Settings**. Put release publishing and test-account administration behind the administrator role. One useful catalog card is sufficient; do not populate a fictional marketplace.

Management API contracts should cover accounts, provider credentials, enrollment, devices, assignments, releases, deployments, sessions, and events. Device endpoints should cover enrollment, heartbeat/configuration acknowledgement, update status, artifacts, and the XiaoZhi voice WebSocket. Final route names may follow the implementation's conventions.

Enforce ownership on every device, credential, event, and deployment operation. Browser authentication and device authentication are separate. Reuse a maintained authentication library; keep browser sessions in secure HttpOnly cookies with appropriate CSRF protection. Hash passwords and device bearer tokens using suitable maintained libraries. Do not develop custom cryptographic primitives.

Store operational metadata by default. Disable raw audio/video retention by default and make transcript history an explicit setting. Provider requests still send selected input to that provider; make this visible in session settings. An administrator's role must not turn provider secrets into downloadable plaintext.

## 10. Firmware releases and updates

Compile releases in a controlled build environment, locally or in CI. The VPS serves verified artifacts; it does not need to compile firmware when a user clicks Install. Keep the build pipeline separate from the running application.

Each release must identify the exact board/revision compatibility, upstream commit, AMPVE version, toolchain, partition requirements, artifact hash, and recovery procedure. Check compatibility before presenting an installation option and again before applying an update.

Use an authenticated release path with signed release metadata or signed artifacts. HTTPS and a hash alone do not replace publisher authentication. Configure OTA slots and rollback deliberately; rollback is not guaranteed just because ESP-IDF supports it. A new image must confirm successful startup after essential checks, or return to the previous valid image when rollback is configured.

Track queued, downloading, applying, rebooting, verifying, succeeded, failed, and rolled-back states. Commands and acknowledgements must be idempotent. After a VPS restart, reconcile persisted jobs against device-reported state instead of marking them successful automatically.

Leave eFuses, Secure Boot activation, and flash encryption activation outside this development MVP. First flashing, bootloader changes, or partition changes on the physical development board require the owner's explicit approval after artifacts and recovery details are reviewable. Writing this document is not authorization to flash hardware.

## 11. Implementation sequence and completion criteria

### Milestone 1 — Platform and provider path

Deploy the web/API/database skeleton. Create administrator and test-user accounts, credential storage, and one application definition. Establish Pipecat sessions using a development audio client before involving USB firmware.

Acceptance: the test user can save and replace a key, validate it, and complete a short conversation through each provider we advertise as available. Provider failures produce useful errors without exposing secrets. Another user cannot access that user's credentials or records.

### Milestone 2 — Firmware and enrollment

Pin the XiaoZhi fork, build for the exact 7B profile, implement AMPVE destinations and enrollment, and prepare the installer manifest. Validate board display, touch, microphone capture, speaker output, and networking in stages.

Acceptance: after an approved initial flash, the browser onboarding flow results in an owned device with truthful capabilities. Pairing expires and cannot be reused. Disconnecting the setup computer does not disconnect a Wi-Fi-connected device.

### Milestone 3 — Complete companion journey

Implement the protocol adapter, face/debug layout, assignment configuration, session control, and provider selection.

Acceptance: the test user activates the companion through AMPVE, speaks to it, hears a response, sees correct local states, and changes provider without reflashing. Verify stop/mute, network loss, invalid key, exhausted quota, and reconnection. Measure end-to-end response delay and device memory stability; record results rather than inventing an SLA.

### Milestone 4 — Lifecycle management

Add a second verified firmware release and exercise deployment tracking, startup verification, failure recovery, credential revocation, and backend restart recovery.

Acceptance: update success requires device confirmation. A failed update has a demonstrated recovery route. A revoked device cannot start new provider sessions. No key appears in browser responses, serial logs, or exported diagnostics.

### Milestone 5 — Experimental vision

Enumerate and validate the Kiyo or document the exact blocker. If supported, capture a still image, send it through the selected vision-capable provider path, and answer a user question about the scene.

Acceptance: successful camera operation is demonstrated alongside audio and display, or vision remains explicitly unavailable with the hardware/driver limitation documented. The working voice MVP is deliverable independently; do not claim the full vision feature is complete when this milestone is blocked.

## 12. Scope boundaries and future extension

Included now: one VPS, administrator and regular test account, one supported board, one companion application, user-owned API keys, Gemini Live/OpenAI Realtime, browser USB onboarding, ownership, configuration, basic diagnostics, and verified OTA.

Deferred: public signup, subscriptions, billing, application marketplace submissions, arbitrary firmware execution, automatic support for every ESP32, Raspberry Pi runtime, permanent PC bridge, continuous remote camera streaming, local large-model inference, and industrial fleet orchestration.

Preserve extension points for device capabilities, application definitions, provider adapters, runtime types, and deployment mechanisms. This allows later applications such as a sensor dashboard, notification display, physical AI experiment, or Raspberry Pi service without making the first implementation abstract and oversized.

The product value should appear in the completed workflow: a person connects supported hardware, understands what it can do, installs something useful, and continues managing it from AMPVE.

## 13. Handoff notes and references

This file is self-contained for planning and implementation on the VPS. Existing AMPVE hardware backups and audit artifacts remain on the development computer; copying this brief does not copy those files or prove the board is accessible from the VPS. Hardware work requires a local session or a deliberately implemented bridge.

This repository contains the current product direction and its first implementation brief. Use [PRODUCT_DIRECTION.md](PRODUCT_DIRECTION.md) for positioning and [../AGENTS.md](../AGENTS.md) for contributor instructions. Older local experiments are outside this repository and are not prerequisites for building the platform. The Django foundation is tracked in [the platform runbook](runbooks/PLATFORM.md); no verified firmware release is included yet.

Sources reviewed for the selected approach; upstream content may change, so pin the versions chosen during implementation:

- [XiaoZhi ESP32](https://github.com/78/xiaozhi-esp32)
- [XiaoZhi Waveshare board profiles](https://github.com/78/xiaozhi-esp32/blob/main/main/boards/waveshare/esp32-p4-wifi6-touch-lcd/config.json)
- [XiaoZhi WebSocket protocol](https://github.com/78/xiaozhi-esp32/blob/main/docs/websocket.md)
- [ESP Web Tools](https://github.com/esphome/esp-web-tools)
- [ESP Web Tools documentation](https://esphome.github.io/esp-web-tools/)
- [Pipecat](https://github.com/pipecat-ai/pipecat)
- [Pipecat Gemini Live service](https://docs.pipecat.ai/api-reference/server/services/s2s/gemini-live)
- [Pipecat OpenAI Realtime service](https://docs.pipecat.ai/api-reference/server/services/s2s/openai)
- [Pipecat ESP32 client and declared device support](https://github.com/pipecat-ai/pipecat-esp32)
- [ESP-IDF ESP32-P4 OTA documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-reference/system/ota.html)
- [Waveshare 7B source and engineering references](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-7B)
- [Waveshare hardware documentation](https://www.waveshare.com/wiki/ESP32-P4-WIFI6-Touch-LCD-7B)

The hardware observations summarized in section 4 came from the owner's local audit on 2026-08-27. The original audit and private flash backup are not published here. Reconfirm hardware state before using them as the basis for a write operation.


Validation update (2026-09-13): Lucas reports successful OpenAI API-key setup and a real browser voice conversation. Gemini and physical hardware remain unvalidated. The revised Companion instructions discourage prompt disclosure; this is behavioral guidance, not a security guarantee. Provider keys remain outside model context and the model has no device-management tools.


Device-shell update (2026-09-13): Lucas reports a successful physical ROM inspection: ESP32-P4 v1.3 via USB 0x1a86:0x55d3. This validates chip inspection only. The runtime/UI/recovery design is recorded in [ADR 0003](decisions/0003-device-runtime-and-recovery.md). A browser interface concept and bounded capability-report storage are implemented; native firmware now exists as a stock-preserving candidate; physical peripheral tests remain pending.


Stock-preserving installation update (2026-09-13): [ADR 0004](decisions/0004-stock-preserving-browser-installation.md) supersedes the initial 7B layout-migration proposal. The browser audit/private backup and gated writer are implemented, but first installation remains unapproved pending exact local bootloader/C6/recovery review. See [BROWSER_INSTALLATION.md](runbooks/BROWSER_INSTALLATION.md).
