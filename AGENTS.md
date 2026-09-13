# Working on AMPVE

USB commissioning update: ADR 0005 separates initial USB core confirmation from later C6/network/peripheral acceptance. Only explicitly signed matching initial-install builds may defer the C6 precheck; physical acceptance remains pending.

Current device milestone: the native stock-preserving candidate and browser audit/backup/gated installer are implemented. A signed USB-assisted development first-install release is prepared for the exact 7B stock profile (ADR 0005); the browser must perform the current-unit comparison and obtain install consent. Physical startup/recovery and C6/Wi-Fi acceptance remain pending. See docs/runbooks/BROWSER_INSTALLATION.md. The 7B RAM-only C6 diagnostic and bounded recovery comparison/executor are described in docs/runbooks/C6_DIAGNOSTIC_RECOVERY.md; physical diagnostic/restore evidence is still pending. Current validation scope is the 7B profile only; other profiles are deferred. Pairing/heartbeat/settings are implemented; board audio/OTA remain pending. See docs/runbooks/NATIVE_FIRMWARE.md. See [docs/runbooks/DEVICES.md](docs/runbooks/DEVICES.md).
Task tracking: use [the ESP32 Project](https://github.com/users/Lucas-hX/projects/10), [tracking issue #6](https://github.com/Lucas-hX/AMPVE/issues/6) and [docs/PROJECT_TRACKING.md](docs/PROJECT_TRACKING.md) for scope, dependencies and evidence-based status updates. The active roadmap is ESP32-only; Raspberry Pi remains future work.

## Read this first

This repository starts as a product/implementation handoff with graphic assets. The Django platform foundation is implemented; consult docs/runbooks/PLATFORM.md for verified delivery status. Encrypted provider connections and an experimental FastAPI/Pipecat browser preview are implemented; Gemini validation, the XiaoZhi audio adapter and physical firmware validation remain future work. Lucas reports successful OpenAI browser voice. Inspect the current checkout before making claims; later sessions may have added implementation.

Read in this order, then load more detail only as needed:

1. `README.md` — product introduction and repository contents.
2. `docs/PRODUCT_DIRECTION.md` — positioning, user outcome, and scope.
3. `docs/MVP_IMPLEMENTATION.md` — architecture, complete workflow, hardware limits, milestones.
4. `images/ampve-brand-kit-v1/README.md` — identity and interpretation of the design references.

The latest explicit user instruction takes priority. These documents define the current direction; old AMPVE experiments outside this repository are not requirements or prerequisites. Keep agreed changes reflected in the relevant documents instead of leaving conflicting plans.

## Objective

**AMPVE: Your devices. New possibilities. Bring apps and AI into your world.**

Build an approachable product that lets people connect supported hardware, choose useful applications, and make them their own. Device management is the technical foundation, not the public-facing product category.

The first application is AMPVE Companion on a Waveshare ESP32-P4-WIFI6-Touch-LCD-7B. A private administrator prepares the instance; a regular test user supplies API keys, onboards the board, activates the companion, and manages it. The first server is a Debian VPS at OVH. The first real AI integrations are Gemini Live and OpenAI Realtime.

## Reuse decisions

- XiaoZhi ESP32: embedded firmware, audio/display behavior, and Waveshare integration. Maintain a small pinned fork or clearly tracked integration rather than an unexplained copy.
- ESP Web Tools: browser-based USB installer, curated manifests, and release artifacts. It does not implement AMPVE ownership or automatic Wi-Fi provisioning by itself.
- Pipecat: backend AI sessions and provider integrations. The XiaoZhi protocol adapter is work we must implement and validate.
- ESP-IDF: embedded build and OTA primitives, including explicitly configured rollback.
- Accepted stack: Django/templates for the platform, FastAPI/Pipecat for audio, PostgreSQL, and the existing Cloudflare HTTPS/WSS tunnel. See docs/decisions/0001-platform-architecture.md for deployment decisions. Confirm the environment and keep the design appropriate for a single VPS.

Do not add ThingsBoard, ElatoAI, Supabase, MeshCentral, openBalena, Kubernetes, or a message broker as an assumed dependency. Reconsider only for a concrete requirement or explicit change of direction. Preserve upstream license notices when source is incorporated; the third-party links here do not mean their code is already vendored.

## How to begin implementation

When asked to build, inspect repository state and the host's available runtimes, resources, ports, and existing services without exposing secrets. Progress through the MVP milestones. Start with accounts, provider settings, a small catalog, and a working provider session before coupling the entire flow to physical hardware.

Keep web UI, management logic, protocol adaptation, and firmware responsibilities identifiable. Record chosen dependency/toolchain versions. A release artifact must be reproducible and traceable to its source. Do not create fake production devices or report mocked sessions as working integrations; test fixtures should be clearly identified.

Use maintained authentication and cryptographic libraries. Avoid custom protocols or frameworks where the chosen foundations already solve the problem. Keep changes scoped to the requested milestone, update affected docs, and run checks appropriate to the implementation that actually exists. Use the application commands documented in docs/runbooks/PLATFORM.md.

Work autonomously on authorized code, documentation, read-only investigation, and reversible local preparation. Ask only for genuinely missing information or actions outside the authorization already provided. Finish reviewable artifacts before requesting any required final approval.

## Hardware and lifecycle constraints

- First board observations: ESP32-P4 revision 1.3, 32 MiB flash/PSRAM, 1024 × 600 display, GT911 touch, ES7210 input, ES8311 output, ESP32-C6 connectivity via ESP-Hosted/SDIO. These came from a local audit; reconfirm the connected unit.
- Do not assume a current XiaoZhi binary is compatible merely because the board name matches. Check chip revision, toolchain, peripherals, and partition layout.
- A physical device is not automatically reachable from the VPS. Its private backup and original audit remain with the owner on the local development computer.
- The first 7B installation now targets an empty original OTA slot and preserves the stock bootloader/table/factory image when the exact local comparison passes (ADR 0004). Only the selected application runs. Management and Companion share firmware; arbitrary app replacement does not preserve a resident AMPVE agent.
- Prepare the exact artifacts, write regions, and recovery route before asking for approval to flash the development board or change its bootloader/partition layout. Do not infer hardware-write authorization from a request to build the web platform.
- Do not perform generic full-chip erase or change eFuses, Secure Boot, or flash encryption as part of the development MVP.
- Razer Kiyo RZ19-0232 USB capture is unverified. A configured OV5647 MIPI camera is not proof of Kiyo compatibility. Keep voice/face completion separate from camera validation.
- A permanent USB bridge and Raspberry Pi runtime are future work. Never describe ESP Web Tools as a persistent remote-management agent.

## Credentials and ownership

Provider keys belong to the user and are encrypted on the server. Keep the encryption key outside the database and repository. Never embed provider keys in firmware, logs, examples, browser storage, prompts, or assets. Use placeholders in `.env.example` and never print real `.env` contents.

Browser sessions, enrollment proofs, and revocable device credentials are distinct. Authenticate ownership on every credential/device/deployment operation; MAC addresses are not proof of identity. Test normal-user isolation separately from administrator access.

Raw audio/video retention is off by default. Show microphone/session state and preserve local stop/mute controls. Validate provider connectivity honestly; API tests can consume provider quota. Never imply a consumer subscription grants API access.

## Design and content

Use the supplied identity as the starting direction: warm ivory, graphite, orange, sage, and clear typography. AMPVE uses the arch-and-square mark; Companion uses the friendly face. Broader applications must fit the brand without becoming robots.

Mockups are composition references, not executable UI or exact hardware photography. Build semantic, responsive, accessible components with real text, states, and controls. Read the visual guide's corrections for the setup/active-device state, placeholder avatar, provider-key copy, and app icon. CSS tokens are proposed values, not extracted pixel specifications. Verify contrast and keyboard/touch behavior in the implementation.

Lead user-facing copy with useful outcomes. State supported hardware precisely. Label future applications; do not advertise “any device” as proven compatibility. Technical terms are appropriate where they help setup, selection, or recovery.

Write repository documentation and code comments in English. Match the user's language in conversation. When reporting work, distinguish implemented behavior, mocked behavior, tested evidence, and remaining limits.

## Repository hygiene

Keep private backups, firmware dumps, credentials, generated build output, dependencies, local state, and logs out of Git. Preserve original selected assets; use versioned siblings for revisions. Do not commit unrelated local experiments or entire upstream repositories accidentally.

The repository now includes the Django platform foundation alongside documentation and eight original PNG images, a gallery, prompts, and CSS tokens. No project-wide software license has been selected here; do not invent one without the owner's decision. Third-party source retains its own licensing obligations when incorporated.

## Windows GitHub authentication (host-specific)

On Lucas's Windows development machine, the elevated Codex sandbox may run as `codexsandboxoffline`, which can see GitHub CLI configuration but cannot unlock the owner's Windows keyring credentials. If sandboxed `gh` returns an invalid token or HTTP 401, do not run `gh auth login` or start device authorization. Retry the required GitHub operation outside the sandbox with the narrowest appropriate approval so it reuses the existing Lucas login. When needed, verify identity with `whoami`, `gh auth status`, and `gh api user --jq .login`.

Never print, persist, or work around this with plaintext `GH_TOKEN`/`GITHUB_TOKEN`. Keep ordinary work in the sandbox. This Windows behavior does not establish authentication on the Debian VPS; inspect that environment separately and follow its authorization.


Validation update (2026-09-13): Lucas reports successful OpenAI API-key setup and a real browser voice conversation. Gemini and physical hardware remain unvalidated. The revised Companion instructions discourage prompt disclosure; this is behavioral guidance, not a security guarantee. Provider keys remain outside model context and the model has no device-management tools.


Device-shell update (2026-09-13): Lucas reports a successful physical ROM inspection: ESP32-P4 v1.3 via USB 0x1a86:0x55d3. This validates chip inspection only. The runtime/UI/recovery design is recorded in [ADR 0003](docs/decisions/0003-device-runtime-and-recovery.md). A browser interface concept and bounded capability-report storage are implemented; native firmware now exists as a stock-preserving candidate; physical peripheral tests remain pending.
