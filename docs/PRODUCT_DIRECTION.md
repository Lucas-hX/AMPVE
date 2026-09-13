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

The accepted implementation uses Django with templates for the platform, future FastAPI/Pipecat for audio, and PostgreSQL. Reuse the existing server with a dedicated database/role and the ampve.com Cloudflare Tunnel. See [ADR 0001](decisions/0001-platform-architecture.md) for deployment and tradeoffs. Keep them simple; do not add enterprise IoT stacks solely to prepare for hypothetical scale.

## Product rules for the first release

1. **Tell the truth about state.** A button click is not a completed installation. Report device acknowledgement, verified startup, actual connectivity, and demonstrated capabilities.
2. **Make ownership explicit.** Browser login, pairing, and device authentication are distinct. Another user must not gain access by guessing a device identifier.
3. **Keep provider choice server-side.** The user supplies API keys in AMPVE. Store them securely and never send them to the board. Changing provider should not require reflashing.
4. **Keep the device responsive.** Face animation, session stop, mute, bounded volume, and offline UI behavior run locally.
5. **Keep setup understandable.** Explain USB installation and Wi-Fi/pairing as concrete steps. After setup, a networked board should operate without the computer.
6. **Design recovery alongside updates.** Publish only compatible, verified releases and preserve a practical recovery path.
7. **Make future features distinguishable.** “Coming later” is appropriate for proposed applications; do not populate the real catalog with fake working integrations.

## First-release boundaries

On the ESP32, the management client and companion share firmware. An initial onboarding image may already contain the companion; application activation then assigns configuration rather than reflashing identical code. Arbitrary replacement firmware can remove manageability.

Cloud speech sessions initially use Gemini Live or OpenAI Realtime with API credentials. Consumer subscription login is not the planned authentication method. Local large-model inference is outside scope.

The camera candidate is the Razer Kiyo RZ19-0232. Its USB integration is unverified. Start with voice and face, then validate still-image capture and provider vision support. Do not promise live remote video in this MVP.

Raspberry Pi, additional ESP32 boards, a permanent PC bridge, more applications, and public commercial operations remain extension opportunities. Preserve clean interfaces for them without implementing their infrastructure now.

## What completion means

The first milestone is a functional private product, not a landing page or a set of attractive screenshots. A normal test user must complete setup, activate the companion, converse, change a provider, and observe truthful device state. Later MVP milestones demonstrate update recovery and experimental vision separately.

Follow the [implementation brief](MVP_IMPLEMENTATION.md) for the concrete architecture and acceptance criteria. The Django platform foundation is implemented; the full provider and hardware criteria are not yet satisfied. See [the platform runbook](runbooks/PLATFORM.md).
