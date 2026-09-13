# Versioned ESP32 hardware compatibility

The canonical first profile is [`firmware/profiles/waveshare-7b-stock-v1.json`](../../firmware/profiles/waveshare-7b-stock-v1.json). It describes **Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, P4 revision 1.3, 32 MiB flash and at least 32 MiB initialized PSRAM**. It is a development compatibility contract, not installation approval. No other ESP32 board is currently supported by this profile.

## One contract across the lifecycle

The stable hardware ID remains `waveshare-esp32-p4-wifi6-touch-lcd-7b`, preserving existing ownership records. The explicit compatibility tuple adds `profile_version: 1`, `layout_id: waveshare-7b-stock-v1`, and `firmware_lineage: ampve-xiaozhi-stock-v1`. The installation ID remains `waveshare-7b-stock-v1`. A board with the same P4 chip and different screen/pins is a different profile; neither a MAC nor USB VID/PID establishes model identity or ownership.

- The browser imports the JSON into its local bundle. ROM readers select the exact chip revision and capacity; backup layout checks and installation offsets use the canonical partition map. Preparation requires the owner's printed-board confirmation and a signed matching compatibility tuple. Unknown/wrong contract, unsupported security and capacity/revision failures prevent writes. Machine-readable error codes accompany friendly messages.
- Offline audit/build/review/publication tools use the platform's Django-independent profile reader through `firmware/tools/profile_contract.py`. Packaging verifies all generated table entries, the generated header, the compiled app version and source provenance. Publication rejects old candidates without the tuple. The signed metadata binds the tuple; the browser and server independently reject a mismatch.
- `prepare.py` generates `main/ampve/profile.h` outside Git. Native startup checks flash, revision, initialized PSRAM and every expected partition before opening NVS. Compile-time assertions check display, audio, BOOT and SDIO pins against the pinned adapter/configuration. This does not probe arbitrary buses or certify functioning peripherals.
- Native hardware reports use schema 2 and include the tuple. The server bounds all fields, persists reports only after device authentication and displays named compatibility blockers in the owner's device page. Schema 1 clients remain supported but cannot establish the versioned contract. A client report is never independent attestation or an OTA permission grant.

## Evidence and remaining gates

The JSON separates owner-reported ROM/audit facts from configured peripherals and unknown validation. The browser cannot measure PSRAM or identify the installed C6 firmware from P4 flash. Native startup checks PSRAM; the current host is ESP-Hosted **2.12.13** with pinned dependencies and SDIO configuration. Compatibility with the unit's installed C6 firmware remains **unverified**. Stock bootloader rollback and physical USB recovery also remain unverified. Matching the profile never bypasses signed release reviews, fresh backups, exact recovery preparation or physical approval.

The `0.1.2-profile-dev` candidate supersedes `0.1.1-stock-dev` for new reviews. Existing private backups remain useful; old candidate manifests require a fresh build/review bundle rather than manually adding compatibility fields. No approved production release exists to migrate.

Treat a released profile version as immutable. Pin a new version/layout/lineage for incompatible changes, preserve archived releases and their original profile, and review migration/recovery before enabling them. Do not expand a revision range or reuse an ID merely to pass validation. A second precisely identified ESP32 board needs its own pins, resource requirements, lineage/layout, recovery evidence and physical tests (#29/#30).

## Checks

Run firmware unittest discovery using the pinned firmware-tools Python, the Django workspace tests, and `npm test && npm run build` in `tools/browser`, then the documented native build and package commands. Fixtures cover a different P4 board, wrong contract version/layout/lineage, altered table entries, bounded reports and insufficient resources. They do not claim physical detection, installation, C6 compatibility or rollback success. See [browser installation](BROWSER_INSTALLATION.md) for those gates.

## Build evidence — 2026-09-13

Two independently compiled external project directories with the shared pinned IDF/compiler/registry cache produced byte-identical app, bootloader, table and initial otadata. The `0.1.2-profile-dev` app is **2,653,600 bytes**, SHA-256 `13e015e52ebe4b75fb83967208423623bbf32e8d0d1021f8dc518574d2222db9`; it leaves **1,475,168 bytes** in each stock OTA slot. The generated table remains SHA-256 `008749f42b6edc628c8dce6719ebb9d9a1d2938205ca58c5ccbcf766e2b42f2e`. This is same-host build reproducibility, not cross-machine or physical-device evidence.

The updated workspace suite passed 50 tests, offline firmware suite 19 tests, and browser logic 15 tests. The existing rendered-template onboarding fixture passed local backup import, no-upload checks and three viewport widths. No publisher key, approved release or hardware-write operation was used.

The private review bundle was packaged from source `bef3eaa`, with verified reproduction against the second directory. Actual app bytes passed the browser image checksum/digest/version parser; the actual candidate plus explicitly synthetic stock passed offline plan/recovery extraction. The deployed instance now selects `/home/ampve/.local/state/ampve/firmware-review-profile-v1` through private configuration. Authenticated public ZIP/app downloads were rehashed, anonymous access was refused, and `installable: false` remained enforced. The live software fixture passed schema-2 heartbeat, compatibility messages, ownership/pairing, pending settings, revocation and responsive layouts; temporary records were removed. Physical hardware was not accessed.

Release publication now follows the [schema-2 trust and ordering contract](FIRMWARE_RELEASES.md). The profile tuple alone never grants initial-install or OTA eligibility.
