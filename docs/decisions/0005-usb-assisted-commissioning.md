# ADR 0005 — Initial installation followed by USB commissioning

Date: 2026-09-13. Status: accepted implementation direction; physical acceptance remains separate.

## Decision

The owner explicitly requested that AMPVE perform compatibility checks in the web onboarding, and allow initial core installation before every peripheral works. A failed C6 version query must not itself prevent a specifically reviewed USB-assisted first installation. This refines ADR 0004; it does not authorize arbitrary board profiles, bootloader changes or full-chip erase.

For the exact Waveshare 7B stock profile, support a signed `initial-install` policy with `commissioning: usb-assisted-v1` and a bounded `usb_review` evidence reference. Bind this choice to the archived, hashed `CONFIG_AMPVE_USB_COMMISSIONING=y` build configuration. Reject partial/unknown policy extensions, claiming USB mode for a different build, and publishing this build for OTA. Existing network-first releases keep their C6 gate.

Keep the original app, bootloader and partition table. The browser performs the same fresh chip/security/layout/full-backup comparison, prepares exact local recovery files, verifies the signature and app bytes, and writes/readbacks the empty application span before changing one selection sector. The user chooses to install and acknowledges power and recovery requirements; engineering reviews belong to the release publisher, not the end user.

## Startup and observations

The native UART owner starts before board/peripheral/network initialization. Its existing Improv worker multiplexes a bounded, read-only `AMPVE_STATUS <32-lowercase-hex-nonce>` request outside Improv frames. It returns only schema, nonce, phase, app version/hash and core/network-initialization/display/touch flags. No credentials, SSID, MAC, raw logs, arbitrary commands or memory access are exposed. Improv remains the Wi-Fi provisioning protocol.

This initial-install build confirms its core after 60 seconds only when storage/state, management startup, running-image identity and USB service creation passed. Peripherals and network initialization are distinct observations. Full-health builds retain their stricter startup conditions. Core confirmation does not prove UART exchange, network association, backend reachability, display quality, touch operation or recovery. The browser additionally requires a live nonce-matched exchange with the exact installed version/hash. Its single Web Serial reader is closed before Improv provisioning or ROM recovery.

Network startup runs in a separate task. A blocked or failed network driver can remain pending without blocking the USB task; fatal driver/system failures can still prevent startup and require recovery. Missing hardware drivers cannot be generated dynamically by the browser. Observations guide a later reviewed profile/build correction when necessary. Online dashboard status still requires real pairing/authenticated heartbeats.

## Recovery and acceptance

The browser offers an explicit return-to-original action from its in-memory recovery plan. Before restoration it compares the entire flash and rejects differences outside the exact original NVS, installed app span and otadata. It restores verified original NVS and app-span bytes, then original selection last, verifies the whole backup hash and resets. No automatic restore occurs on a failed diagnostic. After reload, the owner must reselect original files and prepare the matching installation plan again; mismatched/expanded app spans or other changes stop restoration for engineering review.

Software tests are not a physical recovery trial. Keep first native startup, original-app startup after restore, real Wi-Fi provisioning, pairing and peripheral tests open until observed on the device. USB installation success and core confirmation must never be presented as full device acceptance. Only this validated layout has an implementation; other installation methods and ESP32 profiles need their own evidence.
