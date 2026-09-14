# AMPVE — Product Direction

Date: 2026-09-12

Scope: Current product direction for the first implementation

## Product promise

**Your devices. New possibilities.**

**Bring apps and AI into your world.**

AMPVE helps people give supported hardware a new purpose through useful applications and AI. The experience should feel approachable to a curious owner of a development board or small computer, while leaving room for many future types of devices and applications.

Present AMPVE as a product for creating possibilities with the hardware around you. Remote device management is an enabling capability. It should not define the public brand as an industrial fleet console or narrowly limit the product to installing AI agents.

Broad compatibility is the long-term ambition. Be precise about the hardware and capabilities that actually work in each release.

## First user and first useful outcome

The initial user is the project owner, operating a private instance on a Debian VPS at OVH. A separate regular test account exercises the product journey, while an administrator prepares the instance and publishes supported releases.

The first successful outcome is a complete journey:

1. The test user signs in and saves an API connection.
2. The user connects the Waveshare P4 Touch LCD 7B to a computer.
3. Browser-guided installation, local Wi-Fi provisioning, and pairing associate the device with that account.
4. The user activates AMPVE Companion and customizes its personality and provider.
5. The device listens, speaks, and animates a face, while AMPVE reports its real state.
6. The user can change settings and apply a verified update without repeating initial USB setup.

This should be a genuinely usable personal product before becoming a public service. No billing, public signup, or universal device catalog is required for the first release.

## Brand and application relationship

**AMPVE** is the parent product. **Companion** is its first application.

The arch-and-square brand mark represents an application finding a place to become useful. The orange-eyed face belongs to Companion and related illustrations. Preserve this separation so future applications do not need to be robots or conversational characters.

Use warm ivory, graphite, orange, and sage as the visual starting point. The interface should be clear and welcoming, with technical detail available when it helps someone finish setup or resolve a problem.

Primary navigation can use **Home, My devices, Explore apps, Connections, and Settings**. “Connections” is the friendly presentation of saved provider credentials. Use concrete actions such as “Add a device,” “Activate Companion,” and “Open Companion.” A provider name, hardware model, or firmware warning is appropriate when it informs a real choice.

The [visual guide](../images/ampve-brand-kit-v1/README.md) explains how to interpret the mockups and correct their conceptual shortcuts during implementation.

## What we reuse and what we own

- Reuse **XiaoZhi ESP32** for the embedded voice/display foundation and the Waveshare board integration.
- Reuse **ESP Web Tools** for browser USB flashing.
- Reuse **Pipecat** for the backend AI session machinery and provider integrations.
- Reuse **ESP-IDF OTA** for device-side update primitives.
- Build the AMPVE account, ownership, pairing, configuration, application assignment, release/deployment tracking, and diagnostic experience.
- Implement and test the **XiaoZhi–Pipecat protocol adapter**. Both using WebSockets does not make them directly compatible.

The accepted implementation uses Django with templates for the platform, FastAPI/Pipecat for audio, and PostgreSQL. Reuse the existing server with a dedicated database/role and the ampve.com Cloudflare Tunnel. See [ADR 0001](decisions/0001-platform-architecture.md) for deployment and tradeoffs. Keep them simple; do not add enterprise IoT stacks solely to prepare for hypothetical scale.

## Product rules for the first release

1. **Tell the truth about state.** A button click is not a completed installation. Report device acknowledgement, verified startup, actual connectivity, and demonstrated capabilities.
2. **Make ownership explicit.** Browser login, pairing, and device authentication are distinct. Another user must not gain access by guessing a device identifier.
3. **Keep provider choice server-side.** The user supplies API keys in AMPVE. Store them securely and never send them to the board. Changing provider should not require reflashing.
4. **Keep the device responsive.** Face animation, session stop, mute, bounded volume, and offline UI behavior run locally.
5. **Keep setup understandable.** Explain USB installation and Wi-Fi/pairing as concrete steps. After setup, a networked board should operate without the computer.
6. **Design recovery alongside updates.** Publish only compatible, verified releases and preserve a practical recovery path.
7. **Make future features distinguishable.** “Coming later” is appropriate for proposed applications; do not populate the real catalog with fake working integrations.

## First-release boundaries

On the ESP32, a resident AMPVE Core contains management, recovery and Companion's native hardware integration. Companion activation assigns configuration rather than reflashing identical code. Future signed portable packages can use a bounded Core runtime and shared semantic UI without replacing Companion; applications that need new native drivers still require a reviewed Core OTA. Arbitrary replacement firmware can remove manageability and is not an ordinary marketplace package. See [ADR 0006](decisions/0006-resident-core-and-portable-apps.md).

Cloud speech sessions initially use Gemini Live or OpenAI Realtime with API credentials. Consumer subscription login is not the planned authentication method. Local large-model inference is outside scope.

The camera candidate is the Razer Kiyo RZ19-0232. Its USB integration is unverified. Start with voice and face, then validate still-image capture and provider vision support. Do not promise live remote video in this MVP.

Raspberry Pi, additional ESP32 boards, a permanent PC bridge, more applications, and public commercial operations remain extension opportunities. Preserve clean interfaces for them without implementing their infrastructure now.

## What completion means

The first milestone is a functional private product, not a landing page or a set of attractive screenshots. A normal test user must complete setup, activate the companion, converse, change a provider, and observe truthful device state. Later MVP milestones demonstrate update recovery and experimental vision separately.

Follow the [implementation brief](MVP_IMPLEMENTATION.md) for the concrete architecture and acceptance criteria. The Django platform foundation is implemented; the full provider and hardware criteria are not yet satisfied. See [the platform runbook](runbooks/PLATFORM.md).

## Browser onboarding interaction — owner direction, 2026-09-13

The ordinary user journey is connect/check, confirm the displayed board name, save a private copy or select an existing one, choose a supported installation, then configure Wi-Fi and pair into the dashboard. Users must not interpret partitions, bootloaders, hashes or engineering summaries. Keep engineering evidence in optional support details; it is not an ordinary onboarding deliverable.

Explain what each supported installation preserves or replaces before consent. If a profile supports only replacement, explain the loss of the previous software; never offer a replacement path merely as a fallback for failed compatibility checks. The current 7B installer supports only the reviewed preservation path. Reusing an existing verified backup skips new capture, not compatibility/current-unit checks. Detecting a chip suggests a supported board but does not establish its printed model; obtain that confirmation explicitly. Installation progress, physical startup and authenticated dashboard connection are distinct outcomes.

The installer must perform compatibility selection and planning itself for supported profiles. Ordinary users should never wait for or conduct an engineering review, export JSON or select raw flash offsets. AMPVE maintains the tested profile/release catalog and machine checks. Broader ESP32 coverage requires actual compatible firmware and evidence per board; an unknown chip/peripheral combination remains unavailable. The first development board still needs engineering validation before it becomes an installable catalog entry. Browser USB permission, model confirmation when identity is ambiguous and consent to the displayed installation remain explicit user actions.
