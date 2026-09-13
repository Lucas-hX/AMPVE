# Native OTA implementation and remaining gates

The native candidate `0.1.3-ota-verify-dev` adds the read-only foundations of the OTA client. It does **not** poll deployments, download an update, write an inactive slot or select a new boot partition. Those execution steps and physical recovery validation remain open in #26–#27. The backend lifecycle is documented in [FIRMWARE_DEPLOYMENTS.md](FIRMWARE_DEPLOYMENTS.md).

## Implemented foundations

- `ota_policy.cc` validates the same schema-2 signed release contract as the platform. It uses independently supplied public trust, Ed25519 signature verification, an exact payload/release hash, canonical JSON, strict fields, bounded nesting/metadata, expiry, channel/purpose, sequence floor, confirmed predecessor, hardware/profile/layout, reviewed bootloader/table fingerprints and inactive-slot capacity. It clears its output on rejection. The caller must supply measurements and trusted configuration, never values taken from the untrusted envelope. No production publisher key or default accepting key is embedded.
- The verifier is compiled as an integration module and exercised directly by native host tests. It is not yet called by a deployment worker; link-time garbage collection may omit unused policy code from this intermediate candidate. Trust provisioning and verified policy consumption must be connected before enabling downloads.
- `image_identity.cc` uses ESP-IDF image verification to determine the running image extent, then hashes the complete file in 4 KiB reads, including the appended image digest. `esp_partition_get_sha256()` returns a different embedded-image hash and cannot be substituted for the release artifact's file hash. Unused slot space is excluded. Invalid image metadata, encrypted partitions and read failures yield no identity.
- Startup confirmation requires healthy UI/touch/storage/management and verified image identity. A failed `esp_ota_mark_app_valid_cancel_rollback()` or boot-counter commit no longer produces a confirmed startup. Recovery remains bounded and does not erase NVS.
- After a successful heartbeat and confirmed startup, the native management task reports the running file hash to the backend's authenticated initial identity endpoint. Unreviewed candidates are refused by the server; this does not manufacture a release or trust a client-supplied version. Re-pairing resets the acknowledgement. Changed images under future deployments must use their deployment outcome path.

## Pinned cryptography and tests

The integration pins [Espressif libsodium 1.0.22~1](https://components.espressif.com/components/espressif/libsodium/versions/1.0.22~1/readme), component hash `d4066b373fc6d4c5196db42aeea7faef4ac7f3080af96c2b74e2476c08b78dc1`, in the dependency lock. Its upstream ISC license and notices remain in the external managed component; review bundles include the libsodium ISC and ESP-IDF Apache-2.0 license texts. No upstream source is copied into AMPVE. cJSON remains at the existing pinned version. Set `CONFIG_LIBSODIUM_USE_MBEDTLS_SHA=n` to use libsodium's own SHA implementations; native host tests use those same pinned sources. The pinned ESP-IDF source defines image length and boot-confirmation behavior; see its [OTA documentation](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32p4/api-reference/system/ota.html).

Run the ordinary isolated build from [NATIVE_FIRMWARE.md](NATIVE_FIRMWARE.md) using a new external work directory. For the host sanitizer checks, build the resolved libsodium source separately, without modifying managed components:

```bash
# Set these to the external directories used by the native build.
AMPVE_OTA_WORK="$HOME/.cache/ampve-firmware/xiaozhi-ota"
AMPVE_SODIUM_HOST="$HOME/.cache/ampve-firmware/sodium-host"
mkdir -p "$AMPVE_SODIUM_HOST"
(cd "$AMPVE_SODIUM_HOST" && bash "$AMPVE_OTA_WORK/managed_components/espressif__libsodium/libsodium/configure" --disable-shared --enable-static --enable-minimal)
make -C "$AMPVE_SODIUM_HOST" -j2
"$HOME/.cache/ampve-firmware/tooling/bin/python" firmware/tests/native/run.py \
  --work "$AMPVE_OTA_WORK" --sodium-host "$AMPVE_SODIUM_HOST"
```

The runner checks the resolved dependency lock, compiles actual AMPVE verifier/identity code with AddressSanitizer and UndefinedBehaviorSanitizer, and uses temporary Ed25519 fixture keys. Policy tests cover valid signed metadata, signature/hash corruption, absent/revoked/wrong trust, replay/downgrade, wrong resources/layout, invalid fields, duplicate keys, ambiguous/noncanonical JSON, nesting, metadata bounds and Unicode. Streaming identity tests stub ESP-IDF partition/image metadata calls; they prove exact byte-range hashing, bounded reads and cleared failures, not physical flash reads or ESP-IDF parser operation on a board.

## Required next integration

1. Bind independent publisher trust and a trusted initial sequence to reviewed build inputs, preserving key rotation and provenance. Do not learn publisher keys from the update response.
2. Add bounded authenticated deployment polling, persistent job/report retry state and inactive-slot download using ESP-IDF primitives. Validate image headers and full stream/hash before boot selection; reauthorize the backend boundary. Keep UI/local mute responsive and restart interrupted downloads with explicit integrity semantics.
3. Persist enough predecessor/target identity to report the true confirmed boot or rollback after reset, even if approval has expired. Advance the local sequence only after successful confirmation; do not confuse a lost network response with a failed image.
4. Complete the owner's exact stock/C6/recovery review and approved physical test plan. Exercise power loss, malformed/truncated images, failed startup, Wi-Fi loss and fallback on the actual P4. First USB installation still has no guaranteed previous AMPVE app.

## Verified software evidence — 2026-09-13

The final candidate compiled for ESP32-P4 revision 1.x using the pinned ESP-IDF 6.1 toolchain, with no compiler warnings reported. App size: **2,768,208 bytes**; SHA-256: `4af935c10210ea1dac5aa21b2e2172117a5856773fc2945857d4ac37cd7fb85e`. The IDF partition-size check passed. This is one final build; the earlier two-build reproducibility result does not prove reproduction of this changed candidate.

All **61 native policy cases**, **nine streaming identity cases** and **26 firmware-tool tests** passed. The private non-installable review package is `firmware-review-native-ota-verification` under the existing external private state directory, traced to source commit `0046077`. No production trust or release was created, no USB/OTA write occurred, and the public browser review selection was not changed by this firmware-only work. Board startup, image reads, identity reporting over the physical Wi-Fi stack and recovery remain unvalidated.
