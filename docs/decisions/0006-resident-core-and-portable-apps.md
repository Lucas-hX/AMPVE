# ADR 0006: Resident AMPVE Core and portable application packages

Date: 2026-09-14
Status: Architecture boundary accepted; portable execution engine pending measurement in #89.

## Context

AMPVE's first Waveshare 7B now runs a single ESP-IDF application with board drivers, local LVGL navigation, enrollment, management, signed OTA and the visual-console channel. The profile has two `0x3F0000` OTA application slots, a 9 MiB `assets` SPIFFS partition and a 5 MiB `storage` SPIFFS partition. An ESP32 application is not a desktop process, container or Android package. Booting an arbitrary native image replaces the AMPVE application selected by the bootloader and can remove ownership, recovery and remote management.

Companion requires native codec, audio pipeline, display and realtime-session integration. It cannot be treated as an untrusted downloadable script for its first implementation. At the same time, requiring a complete firmware build for every future clock, dashboard, sensor view or notification app would make the catalog slow to grow and couple user content to hardware release signing.

## Decision

Maintain one **AMPVE Core** firmware per supported hardware profile. Core owns startup/recovery, board drivers, local permissions, enrollment and credentials, management, firmware OTA, package verification, the semantic UI host and Companion's native device integration. Firmware OTA continues to replace only an inactive Core application slot and confirm startup before becoming current.

Support three application delivery classes:

1. **Built-in native application.** Companion is compiled into Core and activated through a versioned device assignment/configuration. Updating its native implementation may require a compatible signed Core OTA; changing provider or personality does not.
2. **Portable AMPVE package.** A signed, bounded bundle targets a versioned Core runtime. It may contain a manifest, compact assets, semantic screens/state and, only after #89's measurements and decision, code for a constrained interpreter. It downloads into namespaced application storage without changing the boot application or removing Companion.
3. **Native hardware extension.** An application that needs a new peripheral driver, unrestricted ESP-IDF API or timing-critical native code is delivered as a reviewed Core release. It is not accepted as an ordinary marketplace upload.

The first portable slice should prefer a declarative state machine using the existing semantic screen/event model. #89 will compare that with sandboxed bytecode or WebAssembly on actual P4 heap, latency and package size before adding an interpreter dependency. Portable packages never receive direct flash, raw memory, device bearer credentials, provider keys, a shell or unrestricted sockets. Core exposes named, versioned capabilities with per-app permissions and quotas, such as semantic UI, timers, assigned configuration, namespaced storage and explicitly mediated hardware/service actions.

Package identity is separate from firmware identity. A canonical manifest binds app ID/version, runtime range, compatible profiles/capabilities, permissions, entry point, sizes and content hashes to a trusted publisher signature. The owner assigns a compatible published version to a device. The device authenticates outbound, downloads exact immutable bytes, verifies them locally, stages completely before activation and acknowledges the resulting version. Withdrawal blocks new activation while preserving history and recovery evidence.

The shared `assets` and `storage` partitions are not protected by ESP-IDF application rollback. Package installation therefore needs its own transactional staging, active-version pointer, quotas and last-known-good package metadata. No package writer is enabled until interrupted download, full storage, corrupted metadata and Core rollback interactions are specified and tested. The current partition table is not changed merely to introduce the catalog.

## Marketplace and creator submissions

Start with AMPVE-administered catalog entries and one curated portable fixture. Marketplace records distinguish application definition, portable release, Core requirement, compatibility, permissions, publisher review and device assignment.

A future creator upload enters as a private draft. AMPVE validates bounded archive structure, manifest, assets, API/runtime compatibility and resource budgets in an isolated packaging or build process. Explicit publisher or administrator review creates the immutable signed release shown in the marketplace. Uploading source or a raw ESP32 binary never grants immediate execution on a device. A creator feature that needs native access follows the Core contribution/release process.

Provider keys remain on the VPS. If a portable application needs an external AI or cloud service, it requests a named AMPVE service/grant associated with the owner and assignment; Core receives only the short-lived application protocol it needs.

## Consequences

- Installing or removing a portable package can preserve Companion, enrollment, management and firmware recovery.
- A Core OTA can update resident capabilities without erasing compatible packages, but it must reject or disable packages outside its declared runtime range.
- The 5 MiB storage area bounds the first portable catalog. Large media packs may use reviewed asset handling later; capacity is never inferred from total 32 MiB flash.
- Arbitrary Arduino/ESP-IDF binaries cannot be advertised as marketplace apps. Native flexibility remains possible through the slower signed Core release path.
- Headless devices can use the same semantic application state through the authenticated virtual display when the profile implements the required capabilities.
- Public submissions, billing, third-party publisher trust and revenue sharing follow only after the curated package lifecycle is proven.

## Delivery sequence

1. Complete the XiaoZhi/Pipecat adapter and native Companion lifecycle in #35 and #36, with audio diagnostics in #23 and resource baselines in #31.
2. Define and prototype the portable runtime/package contract in #89.
3. Deliver curated catalog assignment and package deployment, then private reviewed creator submissions, in #90.

This decision does not make the current `Application` database row a deployable package. It remains a preview catalog entry until versioned releases, assignments and device acknowledgements are implemented.
